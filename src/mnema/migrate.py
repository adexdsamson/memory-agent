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
"""

from __future__ import annotations

from typing import Any


async def reindex_all(t1: Any, embedder: Any, user_id: str) -> int:
    """Re-embed all live records for user_id using the given embedder.

    Returns the count of records re-embedded. Preserves all record fields including the
    protected flag — only the vector embeddings are updated (upsert_vector, never upsert/
    update). The caller must call ``t1.recreate_vector_store(new_dim)`` first when the
    dimension is changing (migrate_embedder does this).
    """
    count = 0
    async for record in t1.live_records(user_id):
        text = record.summary if record.summary else record.content
        vecs = await embedder.embed([text])
        await t1.upsert_vector(record.id, vecs[0])
        count += 1
    return count


async def migrate_embedder(t1: Any, new_embedder: Any, *, user_id: str) -> int:
    """Full embedder/dim-switch migration (D4-14 / PROV-07).

    Sequence:
      1. ``t1.recreate_vector_store(new_embedder.dim)`` — clears all existing vectors and
         recreates the vector store at the new dimension.
      2. ``reindex_all(t1, new_embedder, user_id)`` — re-embeds all live records.

    Record rows (protected flag, valid_until, …) are never modified. Returns the count of
    re-embedded records. Call BEFORE constructing MemoryEngine with the new config.
    """
    await t1.recreate_vector_store(new_embedder.dim)
    return await reindex_all(t1, new_embedder, user_id)
