# Contributing to MNEMA

Thanks for your interest in MNEMA! This guide covers the dev setup, the quality gate your PR must pass, and the patterns the codebase holds itself to.

## Ground rules

- **Be kind.** See the [Code of Conduct](CODE_OF_CONDUCT.md).
- **Discuss big changes first.** Open an issue before a large PR so we can agree on direction.
- **Never weaken a safety guarantee to make a test pass.** The protected-fact and supersession guarantees (below) are the product. If a strengthened assertion fails, fix the code, not the test.

## Dev setup

MNEMA uses [uv](https://docs.astral.sh/uv/). Python **3.12–3.13** (some C-extension wheels lag on 3.14).

```bash
git clone https://github.com/adexdsamson/memory-agent.git
cd memory-agent
uv sync --extra dev            # core + dev tools (hermetic; no cloud SDKs)
uv sync --extra dev --extra cloud   # add when touching cloud adapters / type-checking them
```

## The quality gate (run before every PR)

CI runs exactly this; a green local run means a green PR:

```bash
uv run --extra dev pytest -q                 # hermetic suite — must be green
uv run --extra dev --extra cloud pyright     # 0 errors (cloud SDKs MUST be installed for type-checking)
uv run --extra dev ruff check src/ tests/    # lint — clean
```

Two things worth internalizing:

1. **Test gate ≠ type gate.** Cloud adapters live behind the optional `cloud` extra with lazy imports. The **test** gate runs with `--extra dev` only — cloud/Postgres backends `skip` cleanly without credentials, so CI stays hermetic. The **type** gate runs with `--extra dev --extra cloud` so pyright can resolve the SDK types. A dev-only pyright run reports false "missing import" errors — that's expected; use `--extra cloud` for type-checking.
2. **Gated cloud/Postgres tests.** Live cloud and Postgres conformance tests are opt-in via env vars and never required for the gate:
   - `MNEMA_TEST_DASHSCOPE=1`, `MNEMA_TEST_ANTHROPIC=1`, `MNEMA_TEST_VOYAGE=1`, `MNEMA_TEST_OSS=1` (+ the relevant API keys)
   - `MNEMA_TEST_PG=1` (uses `testcontainers` with `pgvector/pgvector:pg16` if Docker is available, or `MNEMA_TEST_PG_DSN`)

## Code conventions

- **Async-first.** The five verbs and every adapter `Protocol` method are `async def`. Keep pure logic (scoring, packing, decay math) synchronous and event-loop-free so it's unit-testable without an event loop. Wrap sync SDKs in `asyncio.to_thread` at the leaf of the adapter.
- **Structural typing, no inheritance.** Adapters satisfy a `Protocol` by shape — never `class Foo(SomeProtocol)`. Static checking (pyright strict) is the contract.
- **pyright strict + ruff** (line length 100). No new public symbol without types.
- **Never hard-delete.** Eviction sets `valid_until`, removes the vector, and archives to recoverable cold storage with an audit entry. There is no `DELETE FROM t1_records` anywhere — keep it that way.
- **Credentials are `SecretStr`** in config and never logged / never in `__repr__` / never in exceptions.
- **Safety is content-driven.** Safety/medical facts are pinned `protected` by the content rule in `write_path.py` (`_is_safety_claim`) — never by trusting the LLM. Consolidation must never clear `protected`.

## Adding a new adapter (the common contribution)

The whole point of MNEMA is swappable backends. To add one (say a new vector store or LLM provider):

1. **Implement the existing Protocol** (defined in `src/mnema/ports/<axis>.py`) as a new adapter under `src/mnema/adapters/<axis>/` — satisfy it by structure, no inheritance. Mirror the closest existing adapter (e.g. `adapters/vector_store/sqlite_t1.py` for a vector store, `adapters/llm/stub.py` or `adapters/embedding/stub.py` for an LLM/embedder).
2. **Put heavy/cloud deps behind the `cloud` extra** in `pyproject.toml` and import them lazily inside the adapter.
3. **Register it in the conformance suite** (`tests/conformance/conftest.py`) as a new fixture param. Local/hermetic backends run always; credentialed/Docker backends use a `skipif` env gate. The shared contract already asserts the safety invariants (scope isolation, protected-record survival, non-destructive eviction) — your adapter must pass them.
4. **Wire it into the factory** (`src/mnema/config.py`) if it should be selectable by config.
5. Run the full gate. A new backend that breaks "never forget a protected fact" *fails conformance by construction* — that's the design working.

## Commits & PRs

- Conventional-commit style: `feat(...)`, `fix(...)`, `docs(...)`, `test(...)`, `chore(...)`, `refactor(...)`.
- Keep PRs focused; include the gate output in the description.
- Fill in the PR template; link the issue it closes.
- Don't bypass hooks (`--no-verify`) or commit secrets.

## Project layout

```
src/mnema/
  core/        engine, schema, write_path, recall, consolidation, packer, decay, classifier, buffer
  ports/       the six async Protocols (the contracts)
  adapters/    llm/ embedding/ object_store/ vector_store/ vault/ scheduler/
  mcp/         FastMCP server (thin wrapper over the engine)
  demo/        nutrition-coach CLI
  eval/        before/after baseline harness
  config.py    Pydantic config models + build_engine() factory
  migrate.py   reindex / embedder-dim migration (PROV-07)
tests/         unit + tests/conformance/ (parametrized per-backend contract)
.planning/     GSD planning artifacts; milestones/v1.0-* is the shipped record
```

Questions? Open a [discussion or issue](https://github.com/adexdsamson/memory-agent/issues).
