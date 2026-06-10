"""LLM provider port — PROV-01.

Stub in Phase 1; wired to real adapters in Phase 4.
No @runtime_checkable — static checking only (D-10).
"""

from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    """Contract for a language model backend."""

    async def complete(self, prompt: str, *, model: str | None = None) -> str: ...
