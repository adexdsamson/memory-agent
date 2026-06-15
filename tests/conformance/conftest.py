"""Conformance suite backend fixture registry.

Parametrized fixtures for every adapter axis. Each fixture yields an adapter
instance for one backend variant. Local-always backends run unconditionally;
cloud/gated backends are skipped when the corresponding MNEMA_TEST_* env var
is absent (D4-04).

Fixture names MUST NOT collide with tests/conftest.py fixtures:
  - t1_backend        (not 'engine')
  - embedder_backend  (not 'stub_embedder')
  - llm_backend       (not 'stub_llm')
  - object_store_backend
  - vault_backend
  - scheduler_backend

All adapter imports are deferred into fixture bodies (per 04-PATTERNS.md shared
patterns) so that pyright and --collect-only work without the cloud extra installed.
"""

from __future__ import annotations

import os

import pytest


# ---------------------------------------------------------------------------
# Skip helpers
# ---------------------------------------------------------------------------


def _skip_if_no_env(var_name: str) -> pytest.MarkDecorator:
    """Return a pytest.mark.skipif decorator that skips when env var is absent.

    Usage::
        pytest.param("backend", marks=_skip_if_no_env("MNEMA_TEST_PG"))
    """
    return pytest.mark.skipif(
        not os.environ.get(var_name),
        reason=f"Set {var_name}=1 to enable (cloud/gated backend)",
    )


# ---------------------------------------------------------------------------
# T1 backend fixture (RecordStore + VectorIndex)
# ---------------------------------------------------------------------------


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgres",
            marks=_skip_if_no_env("MNEMA_TEST_PG"),
        ),
    ]
)
async def t1_backend(request: pytest.FixtureRequest, tmp_path):  # type: ignore[return]
    """Parametrized T1 backend fixture.

    sqlite — always-on; in-memory SqliteT1
    postgres — gated by MNEMA_TEST_PG=1; PostgresT1 (plan 05)
    """
    if request.param == "sqlite":
        from mnema.adapters.vector_store.sqlite_t1 import SqliteT1  # noqa: PLC0415

        yield await SqliteT1.open(":memory:", dim=128)

    elif request.param == "postgres":
        # PostgresT1 adapter ships in plan 05. Skip until then.
        pytest.skip("PostgresT1 not yet implemented — will ship in plan 04-05")


# ---------------------------------------------------------------------------
# Embedder backend fixture (EmbeddingProvider)
# ---------------------------------------------------------------------------


@pytest.fixture(
    params=[
        "stub",
        pytest.param("voyage", marks=_skip_if_no_env("MNEMA_TEST_VOYAGE")),
        pytest.param("qwen_embed", marks=_skip_if_no_env("MNEMA_TEST_DASHSCOPE")),
    ]
)
async def embedder_backend(request: pytest.FixtureRequest):  # type: ignore[return]
    """Parametrized embedding backend fixture.

    stub       — always-on; deterministic StubEmbedder(dim=128)
    voyage     — gated by MNEMA_TEST_VOYAGE=1; VoyageEmbedder (plan 04-03)
    qwen_embed — gated by MNEMA_TEST_DASHSCOPE=1; QwenEmbedder (plan 04-03)
    """
    if request.param == "stub":
        from mnema.adapters.embedding.stub import StubEmbedder  # noqa: PLC0415

        return StubEmbedder(dim=128)

    elif request.param == "voyage":
        import os  # noqa: PLC0415

        from mnema.adapters.embedding.voyage import VoyageEmbedder  # noqa: PLC0415

        api_key = os.environ.get("VOYAGE_API_KEY", "")
        return VoyageEmbedder(api_key=api_key, output_dimension=1024)

    elif request.param == "qwen_embed":
        import os  # noqa: PLC0415

        from mnema.adapters.embedding.qwen import QwenEmbedder  # noqa: PLC0415

        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        return QwenEmbedder(api_key=api_key, output_dimension=1024)


# ---------------------------------------------------------------------------
# LLM backend fixture (LLMProvider)
# ---------------------------------------------------------------------------


@pytest.fixture(
    params=[
        "stub",
        pytest.param("anthropic", marks=_skip_if_no_env("MNEMA_TEST_ANTHROPIC")),
        pytest.param("qwen", marks=_skip_if_no_env("MNEMA_TEST_DASHSCOPE")),
    ]
)
async def llm_backend(request: pytest.FixtureRequest):  # type: ignore[return]
    """Parametrized LLM backend fixture.

    stub      — always-on; deterministic StubLLM
    anthropic — gated by MNEMA_TEST_ANTHROPIC=1; AnthropicLLM (plan 04-02)
    qwen      — gated by MNEMA_TEST_DASHSCOPE=1; QwenLLM (plan 04-02)
    """
    if request.param == "stub":
        from mnema.adapters.llm.stub import StubLLM  # noqa: PLC0415

        return StubLLM()

    elif request.param == "anthropic":
        import os  # noqa: PLC0415

        from mnema.adapters.llm.anthropic import AnthropicLLM  # noqa: PLC0415

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            pytest.skip("Set ANTHROPIC_API_KEY to run anthropic backend")
        return AnthropicLLM(api_key=api_key)

    elif request.param == "qwen":
        import os  # noqa: PLC0415

        from mnema.adapters.llm.qwen import QwenLLM  # noqa: PLC0415

        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not api_key:
            pytest.skip("Set DASHSCOPE_API_KEY to run qwen backend")
        return QwenLLM(api_key=api_key)


# ---------------------------------------------------------------------------
# Object store backend fixture (ObjectStorePort)
# ---------------------------------------------------------------------------


@pytest.fixture(
    params=[
        "local_fs",
        "moto_s3",
        pytest.param("oss", marks=_skip_if_no_env("MNEMA_TEST_OSS")),
    ]
)
async def object_store_backend(request: pytest.FixtureRequest, tmp_path):  # type: ignore[return]
    """Parametrized object store backend fixture.

    local_fs — always-on; LocalFS backed by tmp_path
    moto_s3  — always-on; hermetic moto-mocked S3 bucket (satisfies STORE-01 ≥2-backends)
    oss      — gated by MNEMA_TEST_OSS=1; OSSS3Store (plan 04-06)

    The moto_s3 backend uses moto.mock_aws() to intercept all boto3 S3 calls
    without any network traffic. It creates a bucket named "mnema-test" and
    stubs OSSS3Store until plan 04-06 ships the real adapter.
    """
    if request.param == "local_fs":
        from mnema.adapters.object_store.local_fs import LocalFS  # noqa: PLC0415

        # yield (not return): this fixture is an async generator (moto_s3/oss branches
        # use yield), and `return <value>` is a SyntaxError in an async generator.
        yield LocalFS(str(tmp_path / "t0"))
        return

    elif request.param == "moto_s3":
        # moto provides a hermetic in-process S3 mock (no network, no credentials).
        # moto[s3] is a dev dependency and pulls in boto3 transitively, so this branch
        # always runs in the hermetic test suite (satisfies STORE-01 >=2 backends).
        try:
            import boto3 as _boto3  # noqa: PLC0415
            from moto import mock_aws  # noqa: PLC0415
            from mnema.adapters.object_store.oss_s3 import OSSS3Store  # noqa: PLC0415
        except ImportError as exc:
            pytest.skip(f"moto[s3] or OSSS3Store not available: {exc}")

        mock = mock_aws()
        mock.start()
        try:
            s3 = _boto3.client(
                "s3",
                region_name="us-east-1",
                aws_access_key_id="testing",
                aws_secret_access_key="testing",
            )
            s3.create_bucket(Bucket="mnema-test")
            store = OSSS3Store(
                "mnema-test",
                aws_access_key_id="testing",
                aws_secret_access_key="testing",
                endpoint_url=None,
                region_name="us-east-1",
            )
            yield store
        finally:
            mock.stop()

    elif request.param == "oss":
        # Real OSS backend -- gated by MNEMA_TEST_OSS env var (already handled by
        # _skip_if_no_env("MNEMA_TEST_OSS") mark on the param).
        import os  # noqa: PLC0415

        from mnema.adapters.object_store.oss_s3 import OSSS3Store  # noqa: PLC0415

        bucket = os.environ.get("MNEMA_OSS_BUCKET", "mnema-test")
        endpoint_url = os.environ.get("MNEMA_OSS_ENDPOINT_URL")
        region_name = os.environ.get("MNEMA_OSS_REGION", "us-east-1")
        aws_access_key_id = os.environ.get("ALIBABA_ACCESS_KEY_ID", "")
        aws_secret_access_key = os.environ.get("ALIBABA_ACCESS_KEY_SECRET", "")
        if not aws_access_key_id or not aws_secret_access_key:
            pytest.skip("Set ALIBABA_ACCESS_KEY_ID and ALIBABA_ACCESS_KEY_SECRET for OSS backend")
        yield OSSS3Store(
            bucket,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            endpoint_url=endpoint_url,
            region_name=region_name,
        )


# ---------------------------------------------------------------------------
# Vault backend fixture (VaultStore)
# ---------------------------------------------------------------------------


@pytest.fixture(
    params=[
        "local_fs_vault",
    ]
)
async def vault_backend(request: pytest.FixtureRequest, tmp_path):  # type: ignore[return]
    """Parametrized vault backend fixture.

    local_fs_vault — always-on; LocalFSVault backed by tmp_path (satisfies STORE-03)
    """
    if request.param == "local_fs_vault":
        from mnema.adapters.vault.local_fs_vault import LocalFSVault  # noqa: PLC0415

        return LocalFSVault(str(tmp_path / "vault"))


# ---------------------------------------------------------------------------
# Scheduler backend fixture (Scheduler)
# ---------------------------------------------------------------------------


@pytest.fixture(
    params=[
        "in_process",
        "cron",
    ]
)
async def scheduler_backend(request: pytest.FixtureRequest):  # type: ignore[return]
    """Parametrized scheduler backend fixture.

    in_process — always-on; InProcessScheduler (started + shutdown on teardown)
    cron       — skipped until CronScheduler ships in plan 04-04
    """
    if request.param == "in_process":
        from mnema.adapters.scheduler.in_process import InProcessScheduler  # noqa: PLC0415

        scheduler = InProcessScheduler()
        await scheduler.start()
        yield scheduler
        await scheduler.shutdown()

    elif request.param == "cron":
        from mnema.adapters.scheduler.cron import CronScheduler  # noqa: PLC0415

        scheduler = CronScheduler("*/5 * * * *")
        await scheduler.start()
        yield scheduler
        await scheduler.shutdown()
