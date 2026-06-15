"""MNEMA migration utilities (PROV-07).

`reindex_all()` re-embeds all live T1 records when the embedder or vector dimension
changes. `migrate_embedder()` is the full D4-14 migration sequence — clear vectors via
`recreate_vector_store()`, then `reindex_all()`.

Call `migrate_embedder()` BEFORE constructing a MemoryEngine with the new config. The
startup dim assertion in `MemoryEngine.__init__` is the backstop that refuses a silent
flip if migration is skipped — switching `embedder_dim` without migrating is an explicit
error, not a silent reindex.

Record rows (including the `protected` flag and `valid_until`) are NEVER modified by
either function — only the vector store is recreated and the embeddings re-written.

Multi-user semantics (CR-01):
  `recreate_vector_store(new_dim)` operates at the table/column level — it wipes ALL
  users' vectors. Passing user_id=None (the default) to `reindex_all()` and
  `migrate_embedder()` re-indexes ALL live records across every user, which is the
  correct safe default after a store-wide recreate. A single-user reindex can be
  requested by passing an explicit user_id.
"""

from __future__ import annotations

from typing import Any


async def reindex_all(
    t1: Any,
    embedder: Any,
    user_id: str | None = None,
) -> int:
    """Re-embed live records using the given embedder.

    When user_id is None (default), iterates ALL live records across every user
    via t1.all_live_records() — the correct behavior after a store-wide
    recreate_vector_store() call (CR-01: prevents multi-user data loss).

    When user_id is provided, iterates only that user's live records via
    t1.live_records(user_id) — safe for single-user targeted reindex operations.

    Returns the count of records re-embedded. Preserves all record fields including
    the protected flag — only the vector embeddings are updated (upsert_vector,
    never upsert/update).
    """
    count = 0
    if user_id is None:
        async for record in t1.all_live_records():
            text = record.summary if record.summary else record.content
            vecs = await embedder.embed([text])
            await t1.upsert_vector(record.id, vecs[0])
            count += 1
    else:
        async for record in t1.live_records(user_id):
            text = record.summary if record.summary else record.content
            vecs = await embedder.embed([text])
            await t1.upsert_vector(record.id, vecs[0])
            count += 1
    return count


async def migrate_embedder(
    t1: Any,
    new_embedder: Any,
    *,
    user_id: str | None = None,
) -> int:
    """Full embedder/dim-switch migration (D4-14 / PROV-07).

    Sequence:
      1. ``t1.recreate_vector_store(new_embedder.dim)`` — clears ALL existing vectors
         (table-level operation; affects every user in a multi-user store).
      2. ``reindex_all(t1, new_embedder, user_id)`` — re-embeds live records.
         When user_id is None (default), re-embeds ALL users' live records so no
         user suffers silent vector loss (CR-01). When user_id is provided, only
         that user's records are re-indexed (single-user targeted migration).

    Record rows (protected flag, valid_until, …) are never modified. Returns the count
    of re-embedded records. Call BEFORE constructing MemoryEngine with the new config.
    """
    await t1.recreate_vector_store(new_embedder.dim)
    return await reindex_all(t1, new_embedder, user_id)
