"""QwenLLM — Alibaba DashScope Qwen LLM adapter.

Satisfies LLMProvider Protocol by structural typing. Direct dashscope SDK (D4-05) — no
LiteLLM. Sync SDK wrapped in asyncio.to_thread (D-13).

Warning: dashscope uses module-level global state for api_key — use a single QwenLLM
instance per engine config to avoid key-clobbering when multiple adapters share the
dashscope module (Pitfall 4).
"""

from __future__ import annotations

import asyncio
from typing import Any


class QwenLLM:
    """Alibaba DashScope Qwen LLM adapter.

    Satisfies LLMProvider Protocol via structural subtyping:
      - async complete(prompt: str, *, model: str | None = None) -> str

    The sync dashscope.Generation.call() is wrapped in asyncio.to_thread (D-13)
    so the event loop is never blocked.

    Pitfall 4 — DashScope global state: dashscope.api_key is module-level state.
    Setting it in __init__ is safe for single-instance engine configs; do not
    instantiate multiple QwenLLM objects with different API keys in one process.

    Security: api_key is assigned to dashscope.api_key (SDK internal state) and
    stored in self._api_key only for per-call api_key= passthrough.
    It does not appear in __repr__ or error messages.
    """

    def __init__(self, api_key: str, default_model: str = "qwen-flash") -> None:
        import dashscope  # type: ignore[import-untyped]  # noqa: PLC0415 — lazy: cloud extra required only when instantiated

        dashscope.api_key = api_key
        self._api_key = api_key  # kept for per-call api_key= passthrough
        self._default_model = default_model
        self._dashscope: Any = dashscope  # Any: dashscope ships no type stubs

    @property
    def model(self) -> str:
        """Return the configured default model name."""
        return self._default_model

    async def complete(self, prompt: str, *, model: str | None = None) -> str:
        """Send prompt to DashScope Qwen API and return the response text.

        Uses result_format="message" so the response arrives as a structured
        choices list (same shape as the Anthropic adapter's output path).

        Args:
            prompt: The full prompt string to send.
            model: Override the default model for this call. None uses default.

        Returns:
            The text content of the first message choice.

        Raises:
            ValueError: If the API returns a null/error response.
        """
        m = model or self._default_model
        dashscope: Any = self._dashscope
        api_key = self._api_key

        def _call() -> str:
            resp: Any = dashscope.Generation.call(
                model=m,
                messages=[{"role": "user", "content": prompt}],
                result_format="message",
                api_key=api_key,
            )
            if resp is None or resp.output is None:
                code: Any = getattr(resp, "code", "unknown") if resp is not None else "null"
                raise ValueError(
                    f"QwenLLM: null response from DashScope (model={m!r}, code={code!r})"
                )
            choices: Any = resp.output.choices
            if not choices:
                raise ValueError(
                    f"QwenLLM: empty choices in DashScope response (model={m!r})"
                )
            content: Any = choices[0].message.content
            if content is None:
                raise ValueError(
                    f"QwenLLM: null message content in DashScope response (model={m!r})"
                )
            return str(content)

        return await asyncio.to_thread(_call)

    def __repr__(self) -> str:
        return f"QwenLLM(model={self._default_model!r})"
