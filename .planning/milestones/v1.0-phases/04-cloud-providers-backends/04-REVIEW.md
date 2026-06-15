---
phase: 04-cloud-providers-backends
reviewed: 2026-06-15T06:59:50Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - src/mnema/adapters/vector_store/postgres_t1.py
  - src/mnema/adapters/object_store/oss_s3.py
  - src/mnema/adapters/llm/anthropic.py
  - src/mnema/adapters/llm/qwen.py
  - src/mnema/adapters/embedding/voyage.py
  - src/mnema/adapters/embedding/qwen.py
  - src/mnema/adapters/scheduler/cron.py
  - src/mnema/config.py
  - src/mnema/migrate.py
  - tests/conformance/conftest.py
findings:
  critical: 3
  warning: 5
  info: 1
  total: 9
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-06-15T06:59:50Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Phase 4 adds the cloud adapter layer: `PostgresT1`, `OSSS3Store`, `AnthropicLLM`, `QwenLLM`, `VoyageEmbedder`, `QwenEmbedder`, `CronScheduler`, `config.py` factory, `migrate.py`, and conformance fixtures. The credential-safety fundamentals are largely sound — `SecretStr` in config, no keys in `__repr__` or error strings, API keys extracted via `.get_secret_value()` at construction only. Scope isolation (D-02/D-03) is correctly applied on the hot-path queries in `PostgresT1`.

Three blockers were found:

1. **`migrate_embedder` wipes all users' vectors but only re-indexes one** — multi-user data loss on any embedder migration.
2. **`list_objects_v2` is not paginated** — sessions with more than 1000 turns silently overwrite each other.
3. **`build_engine` starts the scheduler but never calls `schedule()`** — the consolidation cron job is never registered; automatic consolidation never fires.

Five warnings cover a plain-string API key on `QwenLLM`, a persistently open read transaction after `vector_search`, inconsistent per-call `api_key` passthrough between `QwenLLM` and `QwenEmbedder`, a misleading class name on `QwenAlibabaConfig`, and a redundant module import in conftest.

---

## Critical Issues

### CR-01: `migrate_embedder` deletes all users' vectors but re-embeds only one user

**File:** `src/mnema/migrate.py:49-50`

**Issue:** `recreate_vector_store(new_dim)` operates at the table level — it drops and recreates the `embedding` column across the entire `t1_vectors` table (all users, all agents). The subsequent `reindex_all(t1, new_embedder, user_id)` call re-embeds only the records belonging to the single `user_id` argument. Every other user's vectors are permanently deleted with no path to recovery (they cannot be re-indexed because their record content is still in `t1_records`, but the embedder is now at a new dimension and only called for one user). In a multi-user deployment this is silent, permanent data loss for all non-migrated users.

**Fix:** Either require callers to pass all active `user_id` values and loop `reindex_all` over each, or document that `migrate_embedder` is a single-user operation and add an assertion/guard:

```python
async def migrate_embedder(t1: Any, new_embedder: Any, *, user_id: str) -> int:
    """Full embedder/dim-switch migration (D4-14 / PROV-07).

    WARNING: recreate_vector_store() clears ALL users' vectors. This function
    only re-indexes records for `user_id`. In a multi-user deployment call
    reindex_all() for every active user_id after recreate_vector_store().
    """
    await t1.recreate_vector_store(new_embedder.dim)
    return await reindex_all(t1, new_embedder, user_id)
```

Or provide a multi-user variant:

```python
async def migrate_embedder_all_users(
    t1: Any,
    new_embedder: Any,
    *,
    user_ids: list[str],
) -> int:
    await t1.recreate_vector_store(new_embedder.dim)
    total = 0
    for uid in user_ids:
        total += await reindex_all(t1, new_embedder, uid)
    return total
```

---

### CR-02: `OSSS3Store.append()` uses unpaginated `list_objects_v2` — sessions with more than 1000 turns silently overwrite data

**File:** `src/mnema/adapters/object_store/oss_s3.py:123-127`

**Issue:** `list_objects_v2` returns at most 1000 objects per call. When a session has more than 1000 turns, `resp.get("KeyCount", 0)` returns 1000 (truncated), and the next turn is written to key `{session_id}/1000.json` — overwriting the 1001st turn that was already stored. Subsequent appends collide at the same offset, silently destroying prior turn data. The docstring correctly notes that list+put is not atomic, but omits this separate correctness boundary.

**Fix:** Paginate until `IsTruncated` is false, or switch to a numeric counter stored in a separate sentinel object:

```python
def _call() -> str:
    offset = 0
    continuation_token = None
    while True:
        kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Prefix": f"{session_id}/",
        }
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        resp = self._client.list_objects_v2(**kwargs)
        offset += resp.get("KeyCount", 0)
        if not resp.get("IsTruncated"):
            break
        continuation_token = resp.get("NextContinuationToken")
    key = f"{session_id}/{offset}.json"
    self._client.put_object(
        Bucket=self._bucket,
        Key=key,
        Body=turn.model_dump_json().encode(),
    )
    return f"t0://{session_id}/{offset}"
```

---

### CR-03: `build_engine` starts the scheduler but never calls `scheduler.schedule()` — automatic consolidation never fires

**File:** `src/mnema/config.py:120-129`

**Issue:** For both `LocalConfig` and `QwenAlibabaConfig`, `build_engine` calls `await scheduler.start()` which starts the underlying APScheduler, but `scheduler.schedule(fn)` is never called. No job is registered with the scheduler. `CronScheduler.trigger_now()` and `InProcessScheduler.trigger_now()` both guard with `get_job(JOB_ID)`, which returns `None` when no job has been added — so they silently no-op. Automatic consolidation never fires in any engine built via `build_engine`. The `finally: await self._scheduler.trigger_now()` in `engine.consolidate()` is also a no-op for the same reason.

**Fix:** Wire the consolidation function to the scheduler in `build_engine`, after the `MemoryEngine` is constructed:

```python
# After constructing engine:
engine = MemoryEngine(
    embedder=embedder, t1=t1, t0=t0, scheduler=scheduler,
    llm=QwenLLM(...), vault=vault,
)
await scheduler.schedule(engine.consolidate, every_seconds=0)
return engine
```

Or delegate wiring to `MemoryEngine.__init__` (preferred — the engine owns the consolidation verb):

```python
# In MemoryEngine.__init__, after ConsolidationPipeline is constructed:
# (requires async __init__ or a separate async start() method)
```

If the intent is that callers must call `schedule()` manually, that contract must be documented at the `build_engine` call site and in the `MemoryEngine` docstring.

---

## Warnings

### WR-01: `QwenLLM` stores the API key as a plain string attribute (`self._api_key`)

**File:** `src/mnema/adapters/llm/qwen.py:39`

**Issue:** `self._api_key = api_key` is assigned to the instance to support per-call `api_key=` passthrough to `dashscope.Generation.call()`. Unlike `AnthropicLLM` which intentionally does NOT store the key on `self`, `QwenLLM` holds the key as a plain `str` attribute. Any code path that calls `vars(instance)`, `instance.__dict__`, or captures locals in a traceback (e.g., Sentry, logging middleware) will expose the raw key. The `__repr__` guard is insufficient on its own.

**Fix:** Wrap in a local closure rather than assigning to `self`, mirroring the Anthropic adapter pattern:

```python
def __init__(self, api_key: str, default_model: str = "qwen-flash") -> None:
    import dashscope
    dashscope.api_key = api_key
    self._default_model = default_model
    self._dashscope: Any = dashscope
    self._api_key = api_key  # <-- REMOVE this line
```

And capture `api_key` in the closure inside `complete()`:

```python
async def complete(self, prompt: str, *, model: str | None = None) -> str:
    m = model or self._default_model
    dashscope = self._dashscope

    def _call() -> str:
        # api_key captured from the enclosing __init__ scope via dashscope module
        resp = dashscope.Generation.call(
            model=m,
            messages=[{"role": "user", "content": prompt}],
            result_format="message",
            # Rely on dashscope.api_key set at init time (single-instance contract)
        )
        ...
```

If per-call passthrough is genuinely required (e.g., multi-tenant without global state), store the key in a `SecretStr` wrapper from pydantic: `self._api_key: SecretStr = SecretStr(api_key)` and call `.get_secret_value()` inside `_call()`.

---

### WR-02: `vector_search` leaves an implicit psycopg3 transaction open after every search

**File:** `src/mnema/adapters/vector_store/postgres_t1.py:379-397`

**Issue:** The connection is opened with `autocommit=False`. The `SET hnsw.iterative_scan = 'strict_order'` at line 379 implicitly starts a new transaction (if none is active). After `cursor.fetchall()` the transaction is never committed or rolled back. The connection remains in "idle in transaction" state until the next `commit()` (e.g., from `upsert`). In practice this means: (a) Postgres cannot VACUUM dead tuples while any old snapshot is held; (b) `idle in transaction` connections count against `max_connections` and can trigger the Postgres `idle_in_transaction_session_timeout`; (c) every subsequent write gets an implicit read transaction bundled with it.

**Fix:** Add a `commit()` after the `fetchall()`, or restructure to use `SET LOCAL` inside an explicit transaction that is committed:

```python
async def vector_search(self, ...) -> list[tuple[str, float]]:
    await self._conn.execute("SET hnsw.iterative_scan = 'strict_order'")
    await self._conn.execute("SET hnsw.ef_search = 100")
    # ... build sql, params ...
    cursor = await self._conn.execute(sql, params)
    rows = await cursor.fetchall()
    await self._conn.commit()   # <-- close the implicit read transaction
    return [(str(row[0]), float(row[1])) for row in rows]
```

Alternatively, use `SET LOCAL` inside an explicit `async with self._conn.transaction():` block, which commits automatically on exit.

---

### WR-03: `QwenEmbedder.embed()` does not pass `api_key` per-call, unlike `QwenLLM`

**File:** `src/mnema/adapters/embedding/qwen.py:65-67`

**Issue:** `TextEmbedding.call(model=model, input=texts, dimension=dim)` omits `api_key=`. `QwenLLM.complete()` explicitly passes `api_key=api_key` to each `dashscope.Generation.call()` to ensure the correct key is used regardless of global state. `QwenEmbedder` relies entirely on the `dashscope.api_key` module global set in `__init__`. If any other component (e.g., a future second adapter, test setup, or monkey-patch) overwrites `dashscope.api_key` between `__init__` and a subsequent `embed()` call, the embedder silently uses the wrong key without raising an error. The inconsistency between the two adapters is a maintenance trap.

**Fix:** Store `api_key` in `__init__` (or capture it) and pass it per-call:

```python
def __init__(self, api_key: str, output_dimension: int = 1024) -> None:
    import dashscope
    from dashscope import TextEmbedding
    dashscope.api_key = api_key
    self._dim = output_dimension
    self._api_key = api_key          # needed for per-call passthrough
    self._TextEmbedding = TextEmbedding

# Inside _call():
resp = TextEmbedding.call(
    model=model, input=texts, dimension=dim, api_key=self._api_key
)
```

Note: this re-introduces the plain-string key attribute concern from WR-01. Use `SecretStr` if that pattern is adopted consistently.

---

### WR-04: `QwenAlibabaConfig` name and docstring claim "Qwen + Alibaba" but the config wires `VoyageEmbedder`, not `QwenEmbedder`

**File:** `src/mnema/config.py:48-67`

**Issue:** The class is named `QwenAlibabaConfig` and documented as "the documented default cloud stack (Qwen + Alibaba)", but `build_engine` wires `VoyageEmbedder` for the embedding axis (line 108). The `embedder` literal is `"voyage"` and `voyage_api_key` is a required field. There is no `QwenEmbedder` in this config path. A reader of the class name or docstring will expect Qwen embeddings and may not set a Voyage API key. A user who passes `embedder="qwen"` gets `VoyageEmbedder` anyway because `build_engine` ignores the `embedder` literal field.

**Fix:** Rename the class to `CloudConfig` or `QwenVoyageAlibabaConfig`, or update the docstring to accurately describe the embedding axis:

```python
class QwenAlibabaConfig(BaseModel):
    """Cloud stack: Qwen LLM + Voyage embeddings + Alibaba OSS/Postgres.
    
    LLM: QwenLLM (qwen-flash/qwen-plus via DashScope)
    Embedder: VoyageEmbedder (voyage-3.5 — independent embedding axis, PROV-05)
    Vector store: PostgresT1 + pgvector
    Object store: OSSS3Store (Alibaba OSS via S3-compatible API)
    Vault: LocalFSVault
    Scheduler: CronScheduler
    """
```

---

### WR-05: `conftest.py` postgres branch redundantly re-imports `os` that is already at module scope

**File:** `tests/conformance/conftest.py:69`

**Issue:** `import os  # noqa: PLC0415` is inside the `elif request.param == "postgres":` branch (line 69) but `os` is already imported at the module level (line 7). The `# noqa: PLC0415` suppress tag is correct for the `shutil` import on the next line (which is a deferred import), but `os` does not need to be re-imported. It's a minor error in copy-paste style that could mislead a reader into thinking `os` is not available at module scope.

**Fix:** Remove line 69 (`import os  # noqa: PLC0415`) from the postgres branch. `os` is already in scope.

---

## Info

### IN-01: `AnthropicLLM.complete()` hard-codes `max_tokens=1024`

**File:** `src/mnema/adapters/llm/anthropic.py:62`

**Issue:** `max_tokens=1024` is a magic number with no named constant or config option. For consolidation use-cases that produce long structured JSON extractions, this may cause truncated responses. The Qwen adapter has no equivalent cap (DashScope chooses a default). The value is neither documented as intentional nor exposed as a constructor parameter.

**Fix:** Either expose `max_tokens` as a constructor parameter with a documented default, or promote it to a named constant at the module level:

```python
_DEFAULT_MAX_TOKENS: int = 1024
"""Maximum token output for a single LLM completion call.

1024 is sufficient for consolidation extraction prompts. Increase for
use-cases that produce longer structured JSON (e.g. >5 concurrent extractions).
"""
```

---

_Reviewed: 2026-06-15T06:59:50Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
