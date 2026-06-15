# MNEMA

**A portable, provider-agnostic memory engine for AI agents.**

> Store cheaply, curate offline, forget deliberately, recall within a token budget — on any provider.

[![CI](https://github.com/adexdsamson/memory-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/adexdsamson/memory-agent/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)

MNEMA is a tiered, dual-phase memory layer that an AI agent can use as a **library/SDK** or an **MCP server**. The LLM, embedding model, storage backends, and scheduler all sit behind swappable adapters, so the same engine runs on a laptop (SQLite + local files) or in the cloud (Postgres + pgvector + object storage) with a one-config change.

## The core guarantee

> An agent **never forgets a protected fact** (e.g. an allergy) and **never acts on a superseded one** (e.g. an outdated dietary preference) — while recalling the right context within a fixed token budget, regardless of which model provider or storage backend is configured.

This isn't a tagline — it's enforced structurally and proven by tests:

- **Protected facts can't be forgotten.** The decay/eviction pass skips `protected` records *before* any score math. A Hypothesis **property test** proves that for *any* generated set of records, no protected record is ever evicted.
- **Superseded facts can't resurface.** A contradicting claim atomically retires the old record (`valid_until` + `superseded_by` + a `supersedes` edge); recall only ever returns live records.
- **Critical facts survive a token budget.** A two-pass packer reserves protected/critical slots *first*, so a large off-topic history can't push an allergy out of the context window.

## Why it exists

The default way agents "remember" is to stuff the whole transcript into the context window. That's expensive, it drowns the signal, and — worse — it happily feeds the model **stale, contradicted facts** alongside the current ones. MNEMA's reference evaluation makes the difference concrete:

| Probe | Naive transcript-stuffing | MNEMA |
|-------|---------------------------|-------|
| Protected-fact retention (allergy) | ✅ | ✅ |
| **Superseded-fact avoidance** (old diet) | ❌ (serves both old + new) | ✅ |
| Cross-session recall | ✅ | ✅ |
| Avg context tokens | 21.0 | **13.0** |

**MNEMA 3/3 probes vs naive 2/3, at ~38% fewer context tokens** — deterministic, reproducible (`EVAL.md`). The naive baseline *acts on a superseded fact*; that's the exact failure MNEMA is built to prevent.

## How it works

```
remember ─► T0 (raw turn, append-only) + recent-session buffer + provisional T1 (one embedding, no LLM)
                                   │
              (offline)            ▼
consolidate ─► extract typed records ─► entity-resolve ─► supersede contradictions / merge refinements
                                   │                    ─► pin safety facts `protected`
                                   ▼
              promote stable records ─► T2 vault   then   decay pass (keep_score) ─► evict to cold storage (recoverable)
                                   │
recall(budget) ─► dense + buffer ─► re-rank (relevance × salience × recency) ─► two-pass pack under token budget
expand(id) ─► verbatim T0 turn on demand
```

Six swappable **adapter axes** (each a small async `Protocol`): **LLM**, **embedding** (independent from the LLM), **object store / T0**, **vector store / T1**, **vault / T2**, **scheduler**. Every adapter is gated by a shared conformance suite that asserts the safety invariants on *every* backend.

| Axis | Local (default) | Cloud |
|------|-----------------|-------|
| LLM | `StubLLM` (hermetic) | Qwen (DashScope), Anthropic (Claude) |
| Embedding | `StubEmbedder` | Qwen `text-embedding-v4`, Voyage `voyage-3.5` |
| Object store (T0) | `LocalFS` | Alibaba OSS / S3 / MinIO (one boto3 client) |
| Vector store (T1) | SQLite + `sqlite-vec` | Postgres + `pgvector` (HNSW) |
| Vault (T2) | git-versioned markdown | (same) |
| Scheduler | in-process | generic cron |

## Install

MNEMA is managed with [uv](https://docs.astral.sh/uv/). The base install is dependency-light and fully local (no cloud SDKs, no credentials):

```bash
uv pip install -e .            # core (SQLite + local FS, hermetic)
uv pip install -e ".[cloud]"   # + Qwen/Anthropic/Voyage/Postgres/OSS adapters
```

> Python 3.12+ (the project targets 3.12–3.13).

## Quickstart (SDK)

`build_engine(LocalConfig())` wires all six axes into one engine. The five verbs — `remember`, `recall`, `forget`, `consolidate`, `expand` — are async; `engine.scope(user_id)` binds a user so you don't repeat it.

```python
import asyncio
from mnema.config import LocalConfig, build_engine


async def main() -> None:
    engine = await build_engine(LocalConfig())   # SQLite + LocalFS + vault + scheduler + stubs
    user = engine.scope(user_id="alice")

    # store
    await user.remember("I am allergic to peanuts", session_id="s1")
    await user.remember("I'm doing keto right now", session_id="s1")

    # curate offline (extract typed records, supersede contradictions, promote/decay)
    await engine.consolidate(user_id="alice")

    # recall within a token budget — critical facts reserved first
    results = await user.recall("what should I avoid for dinner?", budget=300)
    for r in results:
        print(r.record_type, "-", r.content)

    # change of mind: a contradicting claim retires the old record on next consolidate
    await user.remember("Actually I stopped keto, I eat balanced now", session_id="s2")
    await engine.consolidate(user_id="alice")
    # recall now surfaces the *current* diet, never the superseded one


asyncio.run(main())
```

Switch to the documented cloud default (Qwen + Alibaba) by swapping the config — the engine code is unchanged:

```python
from mnema.config import QwenAlibabaConfig, build_engine

engine = await build_engine(QwenAlibabaConfig(
    qwen_api_key="...", postgres_dsn="postgresql://...",
    oss_bucket="...", oss_access_key_id="...", oss_secret_access_key="...",
    oss_endpoint_url="https://oss-...aliyuncs.com",
))
```

Claude + Voyage (the independent-embedding-axis combo) is a first-class configuration too — see `src/mnema/config.py`.

## Try the reference demo

A CLI nutrition coach that runs entirely on the engine via the SDK:

```bash
uv run python -m mnema.demo.coach --data-dir ./coach-data --session-id s1
# state an allergy + a diet, exit, then re-run with --session-id s2 to see cross-session recall + supersession
```

## MCP server

The same five verbs are exposed as MCP tools (stdio transport) — a thin wrapper over the same engine:

```bash
uv run python -m mnema.mcp.server
```

Every tool takes a required `user_id` (hard isolation boundary).

## Reproduce the evaluation

```bash
MNEMA_WRITE_EVAL_REPORT=1 uv run --extra dev python -c \
  "import asyncio,tempfile; from pathlib import Path; from mnema.eval.baseline import run_eval; \
   print(asyncio.run(run_eval(Path(tempfile.mkdtemp()))))"
```

Deterministic (StubLLM + StubEmbedder, no network). See [`EVAL.md`](EVAL.md) for the methodology.

## Documentation

- [`docs/blog/why-mnema-and-how-to-use-it.md`](docs/blog/why-mnema-and-how-to-use-it.md) — the inspiration + a guided tour
- [`EVAL.md`](EVAL.md) — before/after baseline + methodology
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — dev setup, the test gate, and how to add an adapter
- `.planning/milestones/v1.0-*` — the full v1.0 roadmap, requirements, and audit

## Status

**v1.0 shipped** (5 phases, 124-test hermetic suite + pyright-strict + a parametrized conformance suite). Roadmap for v1.1: hybrid retrieval (BM25 + graph + RRF), OpenAI/Ollama adapters.

## License

[Apache-2.0](LICENSE).
