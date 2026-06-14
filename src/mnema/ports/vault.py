"""VaultStore port — TIER-03 / CONS-09.

The 6th adapter axis: T2 canonical vault for merged, deduped, human-readable,
git-versioned user model. Per D3-09/D3-10: no @runtime_checkable — static
checking only.

Async methods (D-11 async-first). The vault adapter may do file I/O or git
operations — both are naturally async at the engine's call sites.

No @runtime_checkable — static checking only (D-10).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from mnema.core.schema import MemoryRecord


class VaultStore(Protocol):
    """Contract for T2 canonical vault — the 6th adapter axis (D3-09).

    T2 holds the merged, deduped, human-readable, git-versioned user model.
    Completes the adapter axis set: LLM / Embedding / Object-T0 / T1 / Vault-T2 / Scheduler.
    """

    async def promote(self, record: "MemoryRecord") -> None:
        """Promote a confirmed, stable record into the T2 canonical vault.

        Implementations must:
        - Dedup by content/summary before writing (D3-12).
        - Write in a human-readable, git-versioned format (TIER-03).
        - Be idempotent — re-promoting the same record is safe.
        """
        ...

    async def get_user_model(self, user_id: str) -> str:
        """Return the current T2 user model as a string (for recall/expand)."""
        ...
