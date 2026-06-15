---
phase: 04-cloud-providers-backends
plan: "03"
subsystem: embedding-adapters
tags: [embedding, voyage, qwen, l2-normalization, prov-03, prov-05, tdd]
dependency_graph:
  requires:
    - 04-01  # EmbeddingProvider Protocol + StubEmbedder baseline
  provides:
    - VoyageEmbedder  # src/mnema/adapters/embedding/voyage.py
    - QwenEmbedder    # src/mnema/adapters/embedding/qwen.py
  affects:
    - tests/conformance/conftest.py  # voyage/qwen_embed params now wired (not skip)
    - tests/test_embedding_adapters.py  # hermetic mocked tests for both adapters
tech_stack:
  added:
    - voyageai>=0.4.0  # cloud extra; Voyage AI embedding SDK
    - dashscope>=1.25.21  # cloud extra; DashScope Qwen embedding SDK
  patterns:
    - asyncio.to_thread wrapping for sync SDK calls (D-13)
    - L2-normalization at adapter boundary (D4-07)
    - Lazy import inside __init__ (no top-level vendor import)
    - Structural typing — no Protocol inheritance (D-08)
    - type: ignore[import-untyped] for dashscope (no stubs)
    - type: ignore[attr-defined] for voyageai.Client (pyright false positive)
key_files:
  created:
    - src/mnema/adapters/embedding/voyage.py
    - src/mnema/adapters/embedding/qwen.py
    - tests/test_embedding_adapters.py
  modified:
    - tests/conformance/conftest.py
decisions:
  - "Used asyncio.to_thread for both adapters rather than AsyncClient — voyageai.AsyncClient exists but output_dimension parity with sync Client was not confirmed at implementation time; to_thread is equivalent and safer per D-13"
  - "QwenEmbedder uses AttributeError fallback for TextEmbedding.Models.text_embedding_v4 per RESEARCH.md Assumption A7 — the dashscope SDK ships typed stubs that show the Models attribute exists, but the fallback is kept as a safety net"
  - "api_key stored only inside voyageai.Client instance (not on self) per T-04-03-01 — __repr__ verified to exclude key"
  - "voyageai type: ignore[attr-defined] on voyageai.Client() — pyright incorrectly reports Client not exported but runtime confirms it is (verified dir(voyageai) includes Client)"
metrics:
  duration: "~15 minutes"
  completed: "2026-06-15"
  tasks_completed: 2
  files_changed: 4
---

# Phase 04 Plan 03: VoyageEmbedder + QwenEmbedder Summary

**One-liner:** Voyage voyage-3.5 and Qwen text-embedding-v4 embedding adapters with L2-normalization, asyncio.to_thread, lazy SDK import, and structural EmbeddingProvider compliance.

## What Was Built

Two real embedding adapters satisfying the EmbeddingProvider Protocol via structural typing:

- **VoyageEmbedder** (`src/mnema/adapters/embedding/voyage.py`): Wraps `voyageai.Client.embed()` in `asyncio.to_thread`. Supports configurable `output_dimension` (default 1024, supporting 256/512/1024/2048). Enables the Claude+Voyage independent-axis config (PROV-05, D4-06).

- **QwenEmbedder** (`src/mnema/adapters/embedding/qwen.py`): Wraps `dashscope.TextEmbedding.call()` in `asyncio.to_thread`. Uses Matryoshka dimension 1024 (default). Handles the `TextEmbedding.Models.text_embedding_v4` vs string literal fallback (A7).

Both adapters:
- Expose `dim: int` property returning the configured output dimension
- L2-normalize all output vectors at the adapter boundary (D4-07)
- Store api_key only inside the SDK client, never on `self` (T-04-03-01/02)
- Import SDK lazily inside `__init__` — no top-level vendor import
- Pass pyright strict with 0 errors (cloud extra provides stubs; `type: ignore` where stubs are absent)

## TDD Gate Compliance

- **RED commit:** `d54c17e` — 8 failing tests (ImportError as expected; modules not yet created)
- **GREEN commit:** `09979f0` — 8 passing tests (mocked SDK; all assertions hold)
- No REFACTOR commit needed — code was clean on first pass

## Verification Results

| Check | Result |
|-------|--------|
| `uv run --extra dev pytest tests/test_embedding_adapters.py` | 8 skipped (cloud SDK absent — correct) |
| `uv run --extra dev --extra cloud pytest tests/test_embedding_adapters.py` | 8 passed |
| `uv run --extra dev pytest tests/conformance/test_embedding_contract.py` | 4 passed, 8 skipped |
| `uv run --extra dev pyright` | 0 errors |
| `uv run --extra dev pytest tests/ -q` | 97 passed, 80 skipped, 8 failed* |

*The 8 pre-existing failures are RED stubs for `cron`, `config`, `migrate` — owned by plans 04-04/04-07/04-08. Not caused by this plan.

## Deviations from Plan

None — plan executed exactly as written.

The `type: ignore` annotations on voyageai/dashscope are consistent with the pattern used throughout the project for cloud-gated SDK imports that lack complete type stubs. This is not a deviation but a known pattern (CLAUDE.md: pyright strict compliance required).

## Known Stubs

None. Both adapters make real SDK calls when api_key is valid. The mock in tests is test infrastructure, not a stub in the production path.

## Threat Flags

No new security surface introduced beyond what is documented in the plan's threat model (T-04-03-01 through T-04-03-04). All mitigations applied:
- api_key not on self (T-04-03-01: VoyageEmbedder; T-04-03-02: QwenEmbedder)
- dim property exposes `self._dim` for startup assertion (T-04-03-03)
- asyncio.to_thread accepted for v1 per D-13 (T-04-03-04)

## Self-Check: PASSED

Files exist:
- `src/mnema/adapters/embedding/voyage.py` — FOUND
- `src/mnema/adapters/embedding/qwen.py` — FOUND
- `tests/test_embedding_adapters.py` — FOUND

Commits exist:
- `d54c17e` (RED) — FOUND
- `09979f0` (GREEN) — FOUND
