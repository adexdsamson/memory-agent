"""MNEMA configuration models and engine factory (STORE-04/05).

`build_engine(config)` wires all six adapter axes from a Pydantic config model:
  LocalConfig        — fully-local, always-on stack (SqliteT1 + LocalFS + LocalFSVault +
                       InProcessScheduler + StubEmbedder + StubLLM). Runs the conformance
                       suite end-to-end with zero credentials.
  QwenAlibabaConfig  — the canonical default cloud stack (QwenLLM + QwenEmbedder +
                       PostgresT1 + OSSS3Store + LocalFSVault + CronScheduler). Credential-gated.
                       Per CLAUDE.md: Qwen DashScope for BOTH LLM and embeddings is the
                       default stack. Claude+Voyage is a valid independent-axis combo but
                       wired separately (VoyageEmbedder adapter exists for PROV-05).

API keys are stored as Pydantic `SecretStr` — `str(config)`/`model_dump()` never reveal the
value; the factory extracts them via `.get_secret_value()` only at construction time
(T-04-07-01).

STORE-03: `LocalFSVault` (shipped in Phase 3) satisfies the git-versioned markdown vault
requirement; no additional vault adapter is needed — both configs wire it.
"""

from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, SecretStr

if TYPE_CHECKING:
    from mnema.core.engine import MemoryEngine


def _tmpdir() -> str:
    return tempfile.mkdtemp(prefix="mnema_")


class LocalConfig(BaseModel):
    """Fully-local, always-on config. Constructs with zero arguments (hermetic default)."""

    llm: Literal["stub"] = "stub"
    embedder: Literal["stub"] = "stub"
    vector_store: Literal["sqlite"] = "sqlite"
    object_store: Literal["local_fs"] = "local_fs"
    vault: Literal["local_fs"] = "local_fs"
    scheduler: Literal["in_process"] = "in_process"
    sqlite_path: str = ":memory:"
    local_fs_path: str = Field(default_factory=_tmpdir)
    vault_path: str = Field(default_factory=_tmpdir)
    embedder_dim: int = 128


class QwenAlibabaConfig(BaseModel):
    """Canonical default cloud stack: Qwen LLM + Qwen embeddings + Alibaba. Credential-gated.

    Per CLAUDE.md, the default stack uses Qwen DashScope for BOTH the LLM axis
    (qwen-flash for consolidation, qwen-plus for reasoning) and the embedding axis
    (text-embedding-v4 @ 1024d). A single qwen_api_key covers both.

    LLM:         QwenLLM   (DashScope qwen-flash / qwen-plus)
    Embedder:    QwenEmbedder (DashScope text-embedding-v4, Matryoshka 64–2048d)
    Vector store: PostgresT1 + pgvector HNSW
    Object store: OSSS3Store (Alibaba OSS via S3-compatible API)
    Vault:        LocalFSVault
    Scheduler:    CronScheduler

    For Claude LLM + Voyage embeddings (independent-axis demo), construct
    MemoryEngine directly with AnthropicLLM + VoyageEmbedder — PROV-05 is
    satisfied by those adapters existing and passing conformance.
    """

    llm: Literal["qwen"] = "qwen"
    embedder: Literal["qwen"] = "qwen"
    vector_store: Literal["postgres"] = "postgres"
    object_store: Literal["oss_s3"] = "oss_s3"
    vault: Literal["local_fs"] = "local_fs"
    scheduler: Literal["cron"] = "cron"

    qwen_api_key: SecretStr
    postgres_dsn: str
    oss_bucket: str
    oss_access_key_id: SecretStr
    oss_secret_access_key: SecretStr
    oss_endpoint_url: str
    cron_expression: str = "*/30 * * * *"
    embedder_dim: int = 1024
    vault_path: str = Field(default_factory=_tmpdir)


MnemaConfig = LocalConfig | QwenAlibabaConfig


async def build_engine(config: MnemaConfig) -> "MemoryEngine":
    """Wire all six adapter axes from a config model and return a started MemoryEngine.

    The same `embedder_dim` is passed to both the embedder and the T1 store so the
    MemoryEngine startup dim assertion (PROV-06) is satisfied. `scheduler.start()` is
    awaited and `scheduler.schedule(engine.consolidate, ...)` is called before returning,
    so automatic consolidation is immediately active (CR-03).
    """
    if isinstance(config, LocalConfig):
        from mnema.adapters.embedding.stub import StubEmbedder  # noqa: PLC0415
        from mnema.adapters.llm.stub import StubLLM  # noqa: PLC0415
        from mnema.adapters.object_store.local_fs import LocalFS  # noqa: PLC0415
        from mnema.adapters.scheduler.in_process import InProcessScheduler  # noqa: PLC0415
        from mnema.adapters.vault.local_fs_vault import LocalFSVault  # noqa: PLC0415
        from mnema.adapters.vector_store.sqlite_t1 import SqliteT1  # noqa: PLC0415
        from mnema.core.engine import MemoryEngine  # noqa: PLC0415

        embedder = StubEmbedder(dim=config.embedder_dim)
        t1 = await SqliteT1.open(config.sqlite_path, dim=config.embedder_dim)
        t0 = LocalFS(config.local_fs_path)
        vault = LocalFSVault(config.vault_path)
        scheduler = InProcessScheduler()
        await scheduler.start()
        engine = MemoryEngine(
            embedder=embedder, t1=t1, t0=t0, scheduler=scheduler, llm=StubLLM(), vault=vault
        )
        # CR-03: register the consolidation job AFTER the engine exists so
        # trigger_now() and the scheduled interval can actually dispatch engine.consolidate.
        await scheduler.schedule(engine.consolidate, every_seconds=3600)
        return engine

    if isinstance(config, QwenAlibabaConfig):  # pyright: ignore[reportUnnecessaryIsInstance]
        from mnema.adapters.embedding.qwen import QwenEmbedder  # noqa: PLC0415
        from mnema.adapters.llm.qwen import QwenLLM  # noqa: PLC0415
        from mnema.adapters.object_store.oss_s3 import OSSS3Store  # noqa: PLC0415
        from mnema.adapters.scheduler.cron import CronScheduler  # noqa: PLC0415
        from mnema.adapters.vault.local_fs_vault import LocalFSVault  # noqa: PLC0415
        from mnema.adapters.vector_store.postgres_t1 import PostgresT1  # noqa: PLC0415
        from mnema.core.engine import MemoryEngine  # noqa: PLC0415

        # WR-04: canonical default stack uses Qwen for BOTH LLM and embeddings
        # (qwen_api_key covers both axes — no separate voyage_api_key required).
        embedder = QwenEmbedder(  # type: ignore[assignment]
            api_key=config.qwen_api_key.get_secret_value(),
            output_dimension=config.embedder_dim,
        )
        t1 = await PostgresT1.open(config.postgres_dsn, dim=config.embedder_dim)  # type: ignore[assignment]
        t0 = OSSS3Store(  # type: ignore[assignment]
            config.oss_bucket,
            aws_access_key_id=config.oss_access_key_id.get_secret_value(),
            aws_secret_access_key=config.oss_secret_access_key.get_secret_value(),
            endpoint_url=config.oss_endpoint_url,
        )
        vault = LocalFSVault(config.vault_path)
        scheduler = CronScheduler(config.cron_expression)  # type: ignore[assignment]
        await scheduler.start()
        engine = MemoryEngine(
            embedder=embedder,  # type: ignore[arg-type]
            t1=t1,
            t0=t0,  # type: ignore[arg-type]
            scheduler=scheduler,
            llm=QwenLLM(api_key=config.qwen_api_key.get_secret_value()),  # type: ignore[arg-type]
            vault=vault,
        )
        # CR-03: register the consolidation job AFTER the engine exists so
        # trigger_now() and the cron tick can actually dispatch engine.consolidate.
        # CronScheduler ignores every_seconds and uses its cron_expression instead.
        await scheduler.schedule(engine.consolidate, every_seconds=0)  # type: ignore[arg-type]
        return engine

    raise ValueError(f"Unsupported config type: {type(config)!r}")
