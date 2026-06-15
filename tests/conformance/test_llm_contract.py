"""LLMProvider conformance contract tests.

Parametrized over all registered llm_backend fixture backends.
Local-always backends (stub) run unconditionally.
Cloud-gated backends (anthropic, qwen) skip when MNEMA_TEST_* env vars are absent.

Does NOT test stub-specific sentinel dispatch (EXTRACT_RECORDS: / JUDGE_CONTRADICTION:) —
those are StubLLM unit tests. This contract only asserts the generic LLMProvider Protocol.
"""

from __future__ import annotations


def _make_record(user_id: str, summary: str):  # type: ignore[return]
    """Helper to construct a minimal MemoryRecord for use in contract tests."""
    from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

    return MemoryRecord(
        user_id=user_id,
        session_id="s_llm_contract",
        record_type=RecordType.FACT,
        content=summary,
        summary=summary,
    )


class TestLLMContract:
    """LLMProvider Protocol contract assertions.

    All assertions must hold for every registered llm_backend.

    Note: prompts use the EXTRACT_RECORDS: sentinel so that StubLLM always
    returns a non-empty string. Real adapters are transparent pass-throughs
    and will also return non-empty strings for any prompt.
    """

    async def test_complete_returns_nonempty_string(self, llm_backend) -> None:  # type: ignore[no-untyped-def]
        """LLMProvider.complete() must return a non-empty string."""
        result = await llm_backend.complete("EXTRACT_RECORDS: hello")
        assert isinstance(result, str), (
            f"complete() must return str, got {type(result).__name__!r}"
        )
        assert len(result) > 0, "complete() must return a non-empty string"

    async def test_complete_accepts_model_kwarg(self, llm_backend) -> None:  # type: ignore[no-untyped-def]
        """LLMProvider.complete() must accept model=None without raising."""
        # model=None means use the adapter's default model — must not raise
        result = await llm_backend.complete("EXTRACT_RECORDS: hello", model=None)
        assert isinstance(result, str), (
            f"complete(model=None) must return str, got {type(result).__name__!r}"
        )
