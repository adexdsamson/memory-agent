# Why MNEMA — and how to use it

*Store cheaply, curate offline, forget deliberately, recall within a token budget — on any provider.*

This is the long version of the README: the problem MNEMA exists to solve, the ideas it borrows
(and the flaws it drops), and a guided, runnable tour of the engine from a cold `pip install` to a
contradiction being retired before your eyes.

---

## The problem: agents don't have a memory, they have a transcript

Ask most "memory-enabled" agents how they remember things and the honest answer is: they paste the
whole conversation back into the prompt. That works for a demo and falls apart in production for
three separate reasons:

1. **It's expensive and noisy.** Every turn re-sends every prior turn. The signal you care about —
   "allergic to peanuts" — is one line drowned in a thousand lines of small talk, and you pay for all
   of it on every request.
2. **It has no notion of *stale*.** If a user said "I'm vegetarian" in March and "I eat fish now" in
   May, transcript-stuffing feeds the model **both**. The model now has to guess which one is current,
   and it will sometimes guess wrong.
3. **It can't protect anything.** There's no concept of a fact that *must* survive. When you finally
   add summarization to control cost, the summarizer is free to drop the allergy to save tokens.

The third one is not a cost bug — it's a safety bug. Recommend a peanut dish to someone allergic and
the failure is concrete and dangerous. MNEMA is built so that **cannot happen by construction**.

The reference evaluation makes the gap concrete (deterministic, reproducible — see [`EVAL.md`](../../EVAL.md)):

| Probe | Naive transcript-stuffing | MNEMA |
|-------|---------------------------|-------|
| Protected-fact retention (allergy) | ✅ | ✅ |
| **Superseded-fact avoidance** (old diet) | ❌ serves both old + new | ✅ |
| Cross-session recall | ✅ | ✅ |
| Avg context tokens | 21.0 | **13.0** |

MNEMA gets **3/3** probes at **~38% fewer context tokens**. The naive baseline gets 2/3 — and the one
it misses is the one where it *acts on a fact the user already retracted*.

---

## The core guarantee

> An agent **never forgets a protected fact** (e.g. an allergy) and **never acts on a superseded one**
> (e.g. an outdated dietary preference) — while recalling the right context within a fixed token
> budget, regardless of which model provider or storage backend is configured.

That last clause matters as much as the first two. The guarantee is not "true on our cloud." It's
true on a laptop with SQLite and local files, and true on Postgres + pgvector + object storage, and
true whether the LLM is Claude or Qwen and the embedder is Voyage, Qwen, or a local model — because
every backend is gated by the **same conformance suite** that asserts these invariants.

---

## The ideas it borrows (and the flaws it drops)

MNEMA is deliberately unoriginal in its parts and opinionated in its assembly. Each design choice
takes the strongest idea from an existing system and leaves its main flaw behind:

| Borrowed from | The good idea | The flaw dropped |
|---------------|---------------|------------------|
| **MemPalace** | Never destroy data — keep everything | "Keep everything" *in context*; MNEMA keeps it in a **cold safety net** (T0), not the prompt |
| **Zep** | Fact-validity supersession (`valid_until`) | The Neo4j tax — MNEMA does 1-hop expansion over a tiny adjacency table, no graph DB |
| **Obsidian / GSD** | A portable, human-readable knowledge layer | It being the *only* layer; MNEMA makes the markdown vault the **canonical** tier (T2), not the working one |
| **Mem0** | Compact, typed extraction | Extraction on the hot path; MNEMA defers it to **offline consolidation** on a cheap model |
| **Letta / MemGPT** | Explicit paging under a context limit | Paging *logic in the agent*; MNEMA makes the **token budget a first-class recall argument** |

The result is three tiers plus a buffer, two phases, and one small set of swappable adapters.

---

## How it works, in one screen

```
remember ─► T0 (raw turn, append-only) + recent-session buffer + provisional T1 (one embedding, no LLM)
                                   │
              (offline)            ▼
consolidate ─► extract typed records ─► entity-resolve ─► supersede contradictions / merge refinements
                                   │                    ─► pin safety facts `protected`
                                   ▼
              promote stable records ─► T2 vault   then   decay pass (keep_score) ─► evict to cold (recoverable)
                                   │
recall(budget) ─► dense + buffer ─► re-rank (relevance × salience × recency) ─► two-pass pack under budget
expand(id) ─► verbatim T0 turn on demand
```

**Three tiers.** T0 is the verbatim, append-only episodic log (cold; never injected into context). T1
is typed working memory — the only retrievable tier, indexed for vector + keyword search. T2 is the
canonical, git-versioned markdown user model.

**Two phases.** The *fast online write* costs at most one embedding call (no reasoning LLM) and makes a
claim recallable immediately. The *slow offline consolidation* runs on a cheap "flash" model to extract
typed records, resolve entities, retire contradictions, pin safety facts, and run decay. **Cheap model
curates; expensive model only reasons.** That's what keeps the agent both fast and cheap.

**The freshness fix.** A naive consolidate-only design has a read-after-write hole: state a preference,
ask about it a second later, and consolidation hasn't run yet — recall misses it, which reads as broken.
MNEMA closes it cheapest-first: the **recent-session buffer** covers the within-session case at zero
added cost, and the **provisional T1 write** (one embedding) covers the cross-session-but-pre-consolidation
window. Consolidation later reconciles the provisional record and clears its flag.

---

## The guarantee isn't a tagline — it's three mechanisms

- **Protected facts can't be forgotten.** The decay/eviction pass skips `protected` records *before* any
  score math runs. There is no "did we score it low enough to drop?" branch for them to fall through —
  they never reach the comparison. A Hypothesis **property test** proves that for *any* generated set of
  records, no protected record is ever evicted. And `protected` is set by a **content rule**
  (`_is_safety_claim` in `write_path.py`), never by trusting the LLM to self-report importance.
- **Superseded facts can't resurface.** When consolidation sees a contradicting claim, it atomically
  retires the old record: sets `valid_until`, points `superseded_by` at the new record, and removes the
  old vector from the index. Recall only ever queries live records (`valid_until IS NULL`), so a retired
  fact can't come back.
- **Critical facts survive the budget.** Recall's two-pass packer reserves slots for protected/critical
  records *first*, then fills the remaining budget with the best of the rest. A long off-topic history
  physically cannot push an allergy out of the context window.

Nothing is ever hard-deleted. Eviction moves a record to recoverable cold storage and writes an audit
entry — `forget` and the decay pass both follow the same four-step recoverable sequence.

---

## A guided tour

The base install is dependency-light and fully local — no cloud SDKs, no credentials, no services.

```bash
uv pip install -e .            # core: SQLite + sqlite-vec + local FS, hermetic
# uv pip install -e ".[cloud]" # later, when you want Qwen/Anthropic/Voyage/Postgres/OSS adapters
```

### 1. Wire an engine and bind a user

`build_engine(LocalConfig())` constructs all six adapter axes — SQLite + local FS + a markdown vault +
an in-process scheduler + stub LLM/embedder — and returns a *started* engine (the consolidation job is
already registered). `engine.scope(user_id)` hands you an ergonomic handle so you don't repeat the user
on every call. `user_id` is the hard isolation boundary: it's non-defaulted on every verb, so you
cannot accidentally read or write across users.

```python
import asyncio
from mnema.config import LocalConfig, build_engine


async def main() -> None:
    engine = await build_engine(LocalConfig())
    alice = engine.scope(user_id="alice")
    ...

asyncio.run(main())
```

### 2. Remember — the fast path

`remember` appends the verbatim turn to T0, pushes it into the recent-session buffer, and — for claims
that look durable — writes one provisional T1 record (a single embedding call, no reasoning LLM). It
returns the `t0://...` reference of the stored turn.

```python
    await alice.remember("I am allergic to peanuts", session_id="s1")
    await alice.remember("I'm doing keto right now", session_id="s1", type_hint="preference")
```

`type_hint` ("fact" / "preference" / "event" / "procedure") nudges a known-durable claim to write a T1
record immediately; `durable=True` forces one explicitly. Neither is required — the write-path
heuristic handles the common cases.

### 3. Consolidate — the offline curator

Consolidation is what turns raw turns into clean, typed, de-contradicted memory. It normally runs on a
schedule (or a cron trigger in the cloud), but you can call it directly — which is exactly what the demo
does to make the mechanism legible:

```python
    await engine.consolidate(user_id="alice")
```

In this pass MNEMA extracts typed records, **pins the peanut allergy `protected` by the content rule**
(salience 1.0 — not because the LLM said so), entity-resolves against nearby records, merges refinements,
retires contradictions, promotes stable records to the T2 vault, and runs a decay pass. (`consolidate`
lives on the engine, not the scoped handle, because a scheduler calls it for *all* users.)

### 4. Recall — within a token budget

`recall` runs dense KNN, unions it with the recent buffer, re-ranks by *relevance × salience × recency*,
and — when you pass a `budget` — packs the results under that token limit with the two-pass packer that
reserves critical slots first. It returns `MemoryRecord` objects.

```python
    results = await alice.recall("what should I avoid for dinner?", budget=300)
    for r in results:
        print(r.record_type, "—", r.summary, f"(protected={r.protected})")
```

Each record carries `record_type`, `content`, a short `summary` (what the packer injects by default),
`salience`, `protected`, and `valid_until`. The allergy comes back with `protected=True` and is reserved
into the budget before anything else — even if Alice has months of unrelated history.

### 5. Supersession — a change of mind, made visible

This is the demo that lands in five seconds. Alice changes her diet:

```python
    await alice.remember("Actually I stopped keto, I eat balanced now", session_id="s2")
    await engine.consolidate(user_id="alice")

    diet = await alice.recall("what's my current diet?", budget=200)
    # → surfaces the *balanced* preference; the keto record is retired and never returned.
```

The old keto record still exists — but with `valid_until` set and `superseded_by` pointing at the new
record. Recall filters to live records, so it's gone from results without being destroyed. You can prove
the mechanism (not just the outcome) by inspecting the retired record directly through the T1 adapter.

### 6. Expand and forget

`expand(record_id)` fetches the verbatim T0 turn behind a record — the agent pulls detail only when it
needs it, instead of carrying full text in context. `forget(record_id, reason=...)` explicitly retires a
record through the same recoverable, audited eviction path (and **refuses** to forget a `protected`
record — that's a `ValueError`, by design).

```python
    turn = await alice.expand(results[0].id)   # verbatim original utterance, or None
```

---

## The same engine, on the cloud

Switching to the documented default cloud stack (Qwen for both the LLM and embedding axes + Alibaba OSS
+ Postgres/pgvector) is a **config swap** — the engine code above is unchanged:

```python
from mnema.config import QwenAlibabaConfig, build_engine

engine = await build_engine(QwenAlibabaConfig(
    qwen_api_key="...", postgres_dsn="postgresql://...",
    oss_bucket="...", oss_access_key_id="...", oss_secret_access_key="...",
    oss_endpoint_url="https://oss-...aliyuncs.com",
))
```

And because the embedding axis is **independent** of the LLM axis, Claude-for-reasoning +
Voyage-for-embeddings is a first-class combination too (both adapters ship and pass conformance) — that
independence is the whole point of the design, not an afterthought. The six axes:

| Axis | Local (default) | Cloud |
|------|-----------------|-------|
| LLM | `StubLLM` (hermetic) | Qwen (DashScope), Anthropic (Claude) |
| Embedding | `StubEmbedder` | Qwen `text-embedding-v4`, Voyage `voyage-3.5` |
| Object store (T0) | `LocalFS` | Alibaba OSS / S3 / MinIO (one boto3 client) |
| Vector store (T1) | SQLite + `sqlite-vec` | Postgres + `pgvector` (HNSW) |
| Vault (T2) | git-versioned markdown | (same) |
| Scheduler | in-process | generic cron |

---

## Where to go next

- **Run the reference demo** — a CLI nutrition coach built entirely on the SDK:
  `uv run python -m mnema.demo.coach --data-dir ./coach-data --session-id s1`
- **Reproduce the numbers** — see [`EVAL.md`](../../EVAL.md) for the before/after methodology.
- **Add a backend** — adapters are the common contribution; the [`CONTRIBUTING.md`](../../CONTRIBUTING.md)
  "Adding a new adapter" section walks the Protocol + conformance contract. A new backend that breaks
  "never forget a protected fact" *fails conformance by construction* — which is the design working.

The thesis, once more: *store cheaply, curate offline, forget deliberately, recall within a token
budget — on any provider.*
