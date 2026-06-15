"""build_engine() factory tests — STORE-04/05.

LocalConfig() -> build_engine() -> MemoryEngine -> remember() + recall() + consolidate().
The Qwen+Alibaba cloud config is gated behind MNEMA_TEST_DASHSCOPE.
"""

from __future__ import annotations

import os

import pytest


class TestBuildEngine:
    def test_build_engine_imports(self) -> None:
        """build_engine, LocalConfig, QwenAlibabaConfig importable from mnema.config."""
        from mnema.config import (  # noqa: PLC0415
            LocalConfig,
            QwenAlibabaConfig,
            build_engine,
        )

        assert build_engine is not None
        assert LocalConfig is not None
        assert QwenAlibabaConfig is not None

    async def test_local_config_builds_engine(self) -> None:
        """build_engine(LocalConfig()) returns a MemoryEngine (STORE-04)."""
        from mnema import MemoryEngine  # noqa: PLC0415
        from mnema.config import LocalConfig, build_engine  # noqa: PLC0415

        engine = await build_engine(LocalConfig())
        assert isinstance(engine, MemoryEngine)

    async def test_local_config_end_to_end(self) -> None:
        """build_engine(LocalConfig()) supports remember -> recall end-to-end (STORE-05)."""
        from mnema.config import LocalConfig, build_engine  # noqa: PLC0415

        engine = await build_engine(LocalConfig())
        await engine.remember("test memory content", user_id="u1", session_id="s1")
        results = await engine.recall("test memory content", user_id="u1")
        assert len(results) > 0

    async def test_local_config_consolidate_roundtrip(self) -> None:
        """build_engine(LocalConfig()) supports a consolidate() cycle without error."""
        from mnema.config import LocalConfig, build_engine  # noqa: PLC0415

        engine = await build_engine(LocalConfig())
        await engine.remember("I am allergic to peanuts", user_id="u1", session_id="s1")
        await engine.consolidate(user_id="u1")  # must not raise

    def test_secret_str_hides_api_keys(self) -> None:
        """QwenAlibabaConfig API keys are SecretStr — str(config) must not reveal them.

        WR-04: QwenAlibabaConfig now uses QwenEmbedder (qwen_api_key covers both LLM
        and embedding axes). voyage_api_key is no longer a required field.
        """
        from mnema.config import QwenAlibabaConfig  # noqa: PLC0415

        cfg = QwenAlibabaConfig(
            qwen_api_key="qwen-secret-123",  # type: ignore[arg-type]
            postgres_dsn="postgresql://localhost/x",
            oss_bucket="b",
            oss_access_key_id="oss-id-789",  # type: ignore[arg-type]
            oss_secret_access_key="oss-secret-abc",  # type: ignore[arg-type]
            oss_endpoint_url="https://oss.example.com",
        )
        dumped = str(cfg) + repr(cfg) + str(cfg.model_dump())
        for secret in ("qwen-secret-123", "oss-id-789", "oss-secret-abc"):
            assert secret not in dumped
        # but the real value is retrievable via get_secret_value()
        assert cfg.qwen_api_key.get_secret_value() == "qwen-secret-123"

    @pytest.mark.skipif(
        not os.environ.get("MNEMA_TEST_DASHSCOPE"),
        reason="Set MNEMA_TEST_DASHSCOPE=1 (+ cloud creds) to build the Qwen+Alibaba config",
    )
    async def test_qwen_alibaba_config_builds_when_gated(self) -> None:
        """build_engine(QwenAlibabaConfig(...)) constructs when credentials are present."""
        from mnema import MemoryEngine  # noqa: PLC0415
        from mnema.config import QwenAlibabaConfig, build_engine  # noqa: PLC0415

        cfg = QwenAlibabaConfig(
            qwen_api_key=os.environ["DASHSCOPE_API_KEY"],  # type: ignore[arg-type]
            postgres_dsn=os.environ["MNEMA_TEST_PG_DSN"],
            oss_bucket=os.environ.get("MNEMA_TEST_OSS_BUCKET", "b"),
            oss_access_key_id=os.environ.get("MNEMA_TEST_OSS_KEY", "x"),  # type: ignore[arg-type]
            oss_secret_access_key=os.environ.get("MNEMA_TEST_OSS_SECRET", "x"),  # type: ignore[arg-type]
            oss_endpoint_url=os.environ.get("MNEMA_TEST_OSS_ENDPOINT", "https://oss.example.com"),
        )
        engine = await build_engine(cfg)
        assert isinstance(engine, MemoryEngine)
