"""AnthropicLLM — Anthropic Claude LLM adapter.

Satisfies LLMProvider Protocol by structural typing. Direct anthropic SDK (D4-05) — no
LiteLLM. Sync client wrapped in asyncio.to_thread (D-13). API key from config/env —
never hardcoded or logged.
"""

from __future__ import annotations

import asyncio


class AnthropicLLM:
    """Anthropic Claude LLM adapter.

    Satisfies LLMProvider Protocol via structural subtyping:
      - async complete(prompt: str, *, model: str | None = None) -> str

    The sync Anthropic client is wrapped in asyncio.to_thread (D-13) so the
    event loop is never blocked. The SDK provides built-in retry — do not
    hand-roll exponential backoff here.

    Security: api_key is stored only inside the SDK client object; it is not
    assigned to self._api_key and does not appear in __repr__ or error messages.
    """

    def __init__(self, api_key: str, default_model: str = "claude-haiku-4-5") -> None:
        from anthropic import (
            Anthropic,  # noqa: PLC0415 — lazy: cloud extra required only when instantiated
        )

        self._client = Anthropic(api_key=api_key)
        self._default_model = default_model

    @property
    def model(self) -> str:
        """Return the configured default model name."""
        return self._default_model

    async def complete(self, prompt: str, *, model: str | None = None) -> str:
        """Send prompt to Anthropic API and return the response text.

        Args:
            prompt: The full prompt string to send.
            model: Override the default model for this call. None uses default.

        Returns:
            The text content of the first message in the API response.

        Raises:
            anthropic.APIError: Propagated from the SDK on API failure.
        """
        m = model or self._default_model
        client = self._client

        def _call() -> str:
            from anthropic.types import TextBlock  # noqa: PLC0415

            resp = client.messages.create(
                model=m,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            block = resp.content[0]
            if not isinstance(block, TextBlock):
                raise ValueError(
                    f"AnthropicLLM: unexpected content block type {type(block).__name__!r}"
                )
            return block.text

        return await asyncio.to_thread(_call)

    def __repr__(self) -> str:
        return f"AnthropicLLM(model={self._default_model!r})"
