"""MNEMA durable-claim classifier — pure heuristic logic (D-04/D-05).

D-04: The classifier is the "write-too-much" seam. It errs toward recall on
ambiguous input — a spurious provisional record is cheaper than a missed allergy.
This is intentional per the architecture: false positives are acceptable,
false negatives are dangerous (could miss a safety claim like a food allergy).

D-05: Safety-relevant claims (allergies, intolerances, medical facts) produce a
provisional T1 write immediately on the fast path — before any consolidation LLM
runs. The classifier pattern _FIRST_PERSON_STATIVE is intentionally broad so
"I am allergic to peanuts" is always captured.

This module has NO imports except `re` and `typing`. It is pure logic — no I/O,
no Protocol imports, no `async`. Zero outward dependencies. This is the "classifier
seam" per the Architectural Responsibility Map.
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Module-level compiled regex patterns (from RESEARCH.md Pattern 5 — exact strings)
# ---------------------------------------------------------------------------

# First-person stative verbs: "I am/was/have/hate/love/like/..." — durable claims
_FIRST_PERSON_STATIVE: re.Pattern[str] = re.compile(
    r"(?i)\bi\s+(?:am|was|have|hate|love|like|prefer|enjoy|need|want|eat|drink|"
    r"avoid|dislike|am\s+allergic|am\s+intolerant|follow|practice|believe|think|"
    r"know|own|always|never|usually|often|batch[-\s]cook)\b"
)

# A question mark indicates a transient, interrogative turn — suppress T1 write
_QUESTION: re.Pattern[str] = re.compile(r"\?")

# Modal or hypothetical framing — suppress T1 write
_MODAL_HYPOTHETICAL: re.Pattern[str] = re.compile(
    r"(?i)\b(?:would|could|might|may|should\s+i|can\s+i|do\s+you|what\s+if|if\s+i)\b"
)


def looks_like_durable_claim(
    text: str,
    type_hint: Optional[str] = None,
    durable: bool = False,
) -> bool:
    """Heuristic test: is this text a durable, person-scoped claim worth T1-indexing?

    Decision order (from RESEARCH.md Pattern 5):
      1. Caller override: if `durable` is True, always return True.
      2. Type override: if `type_hint` is in ("fact", "preference", "procedure"),
         always return True — the caller has already classified it.
      3. Question suppression: if text contains "?", return False.
      4. Modal/hypothetical suppression: if text matches _MODAL_HYPOTHETICAL, return False.
      5. First-person stative pattern: return True if matched.
      6. Default: return False (conservative — unlabelled text without a first-person
         stative verb is treated as ephemeral).

    Args:
        text: The utterance text to classify.
        type_hint: Caller-supplied type string (e.g. "fact", "preference", "event",
                   "procedure"). "event" is NOT a forced-True override because events
                   are often transient; the regex governs.
        durable: Explicit override — if True, skip all pattern checks and return True.

    Returns:
        True if the text should trigger a provisional T1 write on the fast path.
    """
    # 1. Explicit caller override
    if durable:
        return True

    # 2. Type-hint override for named durable types
    if type_hint in ("fact", "preference", "procedure"):
        return True

    # 3. Question suppression
    if _QUESTION.search(text):
        return False

    # 4. Modal/hypothetical suppression
    if _MODAL_HYPOTHETICAL.search(text):
        return False

    # 5. First-person stative pattern match
    return bool(_FIRST_PERSON_STATIVE.search(text))
