---
phase: "04-cloud-providers-backends"
plan: "02"
subsystem: "adapters/llm"
tags: ["llm", "anthropic", "qwen", "dashscope", "cloud-adapter", "structural-typing", "asyncio"]

dependency_graph:
  requires:
    - "04-01"  # conformance suite skeleton + cloud optional extra in pyproject.toml
  provides:
    - "AnthropicLLM — src/mnema/adapters/llm/anthropic.py"
    - "QwenLLM — src/mnema/adapters/llm/qwen.py"
    - "llm_backend conformance fixture wired for anthropic + qwen params"
  affects:
    - "tests/conformance/conftest.py — llm_backend fixture"

tech_stack:
  added:
    - "anthropic>=0.109.1 (cloud extra) — sync Anthropic client; lazy import in __init__"
    - "dashscope>=1.25.21 (cloud extra) — sync Generation.call; lazy import in __init__; untyped SDK"
  patterns:
    - "asyncio.to_thread wrapping sync SDK calls (D-13)"
    - "Lazy __init__ import so cloud extra required only at instantiation"
    - "Structural typing (no Protocol inheritance, D-08)"
    - "type: ignore[import-untyped] + Any for untyped dashscope SDK"
    - "isinstance(TextBlock) guard for Anthropic strict pyright compliance"

key_files:
  created:
    - "src/mnema/adapters/llm/anthropic.py"
    - "src/mnema/adapters/llm/qwen.py"
  modified:
    - "tests/conformance/conftest.py — llm_backend fixture wires real adapters"

decisions:
  - "AnthropicLLM uses isinstance(TextBlock) guard on resp.content[0] to satisfy pyright strict mode — the messages API returns a union of content block types"
  - "QwenLLM annotates dashscope module ref as Any and uses type: ignore[import-untyped] — dashscope ships no type stubs, and strict pyright would otherwise fail on unknown member access"
  - "QwenLLM passes api_key= per-call in addition to the global dashscope.api_key assignment — avoids key confusion if the global is changed between requests"
  - "Null-check chain in QwenLLM: resp is None -> resp.output is None -> choices empty -> content is None — each guard raises a descriptive ValueError"

metrics:
  duration: "~35 minutes"
  completed: "2026-06-15"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 1
---

# Phase 04 Plan 02: AnthropicLLM + QwenLLM Adapters Summary

AnthropicLLM (PROV-04) and QwenLLM (PROV-03) wrap their sync SDKs in `asyncio.to_thread`, satisfy `LLMProvider` by structural typing, guard API keys from leaking to repr/logs, and skip cleanly in CI without credentials.

## Tasks

| # | Name | Commit | Status |
|---|------|--------|--------|
| 1 | AnthropicLLM adapter (PROV-04) | c15bdb0 | Done |
| 2 | QwenLLM adapter + conftest wiring (PROV-03) | 1376681 | Done |

## Verification Results

| Check | Result |
|-------|--------|
| `pyright` (strict, no cloud extra) | 0 errors |
| `uv run --extra dev pytest tests/conformance/test_llm_contract.py` | 2 passed, 4 skipped |
| Core hermetic suite (51 tests) | 51 passed, 0 failed |
| `AnthropicLLM(api_key='test')` with cloud extra | OK |
| `QwenLLM(api_key='test')` with cloud extra | OK |
| Import without cloud extra (module-level) | OK — no ImportError |
| Instantiation without cloud extra | ImportError raised (correct guard) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Anthropic response block type guard for pyright strict mode**
- **Found during:** Task 1 verification (pyright run)
- **Issue:** `resp.content[0].text` causes 13 pyright errors because `content[0]` is a union of ~10 block types (TextBlock, ToolUseBlock, etc.) and only `TextBlock` has `.text`. Pyright strict mode flags all non-TextBlock paths.
- **Fix:** Added `isinstance(block, TextBlock)` guard from `anthropic.types`; raises `ValueError` for unexpected block types
- **Files modified:** `src/mnema/adapters/llm/anthropic.py`
- **Commit:** c15bdb0

**2. [Rule 1 - Bug] DashScope SDK actual response structure differs from RESEARCH.md assumption**
- **Found during:** Task 2 implementation — verified at install time (per RESEARCH.md A1 annotation)
- **Issue:** RESEARCH.md marked DashScope call shape as ASSUMED (A1). Verified: `resp.output` IS a `GenerationOutput` object (not a raw dict) when `status_code == HTTPStatus.OK`, so `resp.output.choices[0].message.content` works correctly. However, the `dashscope` SDK ships with no type stubs (`reportMissingTypeStubs`), causing 15 pyright errors with strict mode.
- **Fix:** Used `type: ignore[import-untyped]` at the import and annotated all dashscope-returned variables as `Any` to satisfy pyright without fighting an untyped third-party library
- **Files modified:** `src/mnema/adapters/llm/qwen.py`
- **Commit:** 1376681

**3. [Rule 2 - Missing Critical Functionality] Per-call api_key passthrough in QwenLLM**
- **Found during:** Task 2 — reviewing dashscope's `Generation.call` signature
- **Issue:** `dashscope.api_key` is module-level global state (Pitfall 4). The `Generation.call` method also accepts an `api_key=` per-call parameter. Passing it explicitly prevents a race condition if the global is mutated between calls in tests.
- **Fix:** Added `api_key=api_key` to the `Generation.call` call
- **Files modified:** `src/mnema/adapters/llm/qwen.py`
- **Commit:** 1376681

## Known Stubs

None — both adapters are fully wired to their cloud SDKs. The conformance fixture parameters skip at test-collection time when env vars are absent; they are not stubs.

## Pre-existing Test Failures (Out of Scope)

The following 8 test failures existed before this plan and are owned by other parallel-wave plans:
- `tests/test_cron.py` (2 failures) — `CronScheduler` not yet implemented (plan 04-04)
- `tests/test_factory.py` (3 failures) — `mnema.config` not yet implemented (plan 04-05/06)
- `tests/test_reindex.py` (3 failures) — `mnema.migrate` not yet implemented (plan 04-05/06)

These are logged per scope-boundary rule; not fixed here.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. The two adapter files are leaf-level I/O implementations behind the existing `LLMProvider` port. All `T-04-02-*` mitigations from the plan's threat register are implemented:

| Threat ID | Mitigation Status |
|-----------|-------------------|
| T-04-02-01 | api_key stored in SDK client only; __repr__ returns `AnthropicLLM(model=...)` |
| T-04-02-02 | dashscope global-state risk documented in class docstring; per-call api_key= added |
| T-04-02-03 | Accepted per D-13; asyncio.to_thread blocks thread pool, not event loop |
| T-04-02-04 | Accepted; prompt validation is ConsolidationPipeline's responsibility |
| T-04-02-05 | Accepted; audit logging is a v2 concern |

## Self-Check: PASSED

Files exist:
- `src/mnema/adapters/llm/anthropic.py` — FOUND
- `src/mnema/adapters/llm/qwen.py` — FOUND
- `tests/conformance/conftest.py` — modified (FOUND)

Commits exist:
- `c15bdb0` — FOUND (feat(04-02): implement AnthropicLLM adapter)
- `1376681` — FOUND (feat(04-02): implement QwenLLM adapter + wire conformance fixture)
