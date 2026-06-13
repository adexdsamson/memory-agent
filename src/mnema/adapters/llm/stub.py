"""StubLLM — deterministic LLM provider for hermetic CI tests. Dispatches
on sentinel strings (EXTRACT_RECORDS:, JUDGE_CONTRADICTION:) to produce deterministic JSON
extraction results or contradiction verdicts. Satisfies LLMProvider Protocol structurally.
No external dependencies — uses only stdlib hashlib and json.
"""

from __future__ import annotations

import hashlib
import json

# ---------------------------------------------------------------------------
# Keyword tables for deterministic extraction
# ---------------------------------------------------------------------------

_SAFETY_KEYWORDS: frozenset[str] = frozenset(
    {
        "allerg",
        "anaphyl",
        "celiac",
        "seizure",
        "epilep",
        "diabeti",
        "medication",
        "intolerant",
    }
)

_PREFERENCE_KEYWORDS: frozenset[str] = frozenset(
    {
        "prefer",
        "love",
        "like",
        "enjoy",
        "hate",
        "dislike",
    }
)

_VERDICTS: list[str] = ["distinct", "refine", "contradict"]


class StubLLM:
    """Deterministic LLM provider for testing.

    Dispatches on sentinel prefixes in the prompt:
      - ``EXTRACT_RECORDS:`` -> keyword-driven JSON extraction (list of record dicts)
      - ``JUDGE_CONTRADICTION:`` -> deterministic verdict via sha256 hash mod 3

    Satisfies LLMProvider Protocol via structural subtyping:
      - async complete(prompt: str, *, model: str | None = None) -> str
    """

    version: str = "stub-v1"

    def __init__(self) -> None:
        pass

    async def complete(self, prompt: str, *, model: str | None = None) -> str:
        """Dispatch on sentinel prefix and return deterministic output.

        Args:
            prompt: Must start with ``EXTRACT_RECORDS:`` or ``JUDGE_CONTRADICTION:``.
            model: Ignored -- stub does not call any model.

        Returns:
            JSON string (list of record dicts) for EXTRACT_RECORDS,
            verdict string for JUDGE_CONTRADICTION, or "" for anything else.
        """
        if "EXTRACT_RECORDS:" in prompt:
            return self._extract(prompt)
        if "JUDGE_CONTRADICTION:" in prompt:
            return self._judge(prompt)
        return ""

    def _extract(self, prompt: str) -> str:
        """Apply keyword rules to produce a list of typed record dicts.

        Rules (evaluated in priority order):
          1. Safety/medical keywords -> record_type="fact", protected=True, salience=1.0
          2. Preference keywords     -> record_type="preference", protected=False, salience=0.7
          3. Default                 -> record_type="preference", protected=False, salience=0.5

        Returns:
            JSON-encoded list[dict] with keys: content, record_type, salience,
            protected, keywords, summary.
        """
        _, _, content = prompt.partition("EXTRACT_RECORDS:")
        content = content.strip()

        content_lower = content.lower()

        if any(kw in content_lower for kw in _SAFETY_KEYWORDS):
            record_type = "fact"
            protected = True
            salience = 1.0
        elif any(kw in content_lower for kw in _PREFERENCE_KEYWORDS):
            record_type = "preference"
            protected = False
            salience = 0.7
        else:
            record_type = "preference"
            protected = False
            salience = 0.5

        # Simple keyword heuristic: words longer than 4 chars
        keywords = [w for w in content.split() if len(w) > 4]

        record = {
            "content": content,
            "record_type": record_type,
            "salience": salience,
            "protected": protected,
            "keywords": keywords,
            "summary": content[:60].strip(),
        }
        return json.dumps([record])

    def _judge(self, prompt: str) -> str:
        """Return a deterministic contradiction verdict from the prompt body.

        Uses sha256 of the body text (after the sentinel) modulo 3 to index
        into ["distinct", "refine", "contradict"].  Deterministic for any
        fixed (existing, new) content pair.

        Returns:
            One of "distinct", "refine", or "contradict".
        """
        _, _, body = prompt.partition("JUDGE_CONTRADICTION:")
        body_bytes = body.strip().encode("utf-8")
        digest_int = int(hashlib.sha256(body_bytes).hexdigest(), 16)
        return _VERDICTS[digest_int % 3]
