---
phase: 3
slug: forgetting-salience-floor-budget-packer-mcp
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-14
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (`asyncio_mode = "auto"`) + Hypothesis (property tests) |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] (from Phase 1) |
| **Quick run command** | `uv run --extra dev pytest -q` |
| **Full suite command** | `uv run --extra dev pytest -q && uv run --extra dev pyright` |
| **Estimated runtime** | ~8 seconds (Hypothesis property test adds a few hundred ms; FastMCP in-process client is fast) |

---

## Sampling Rate

- **After every task commit:** `uv run --extra dev pytest -q`
- **After every plan wave:** `uv run --extra dev pytest -q && uv run --extra dev pyright`
- **Before `/gsd-verify-work`:** Full suite green (eviction + property test + packer + adversarial test + vault + MCP)
- **Max feedback latency:** 12 seconds

---

## Per-Task Verification Map

| Requirement | Success Criterion | Test Focus | Automated Command | Status |
|-------------|-------------------|------------|-------------------|--------|
| FORG-02 | below-threshold non-protected records evicted to cold storage | eviction pass moves record (valid_until set, vector deleted, cold record written) | `uv run --extra dev pytest tests/test_forgetting.py -q` | ⬜ pending |
| FORG-03 | protected skipped before score math, survives EVERY pass | **Hypothesis property test** over arbitrary record sets: no protected record ever evicted | `uv run --extra dev pytest tests/test_forgetting.py -q` | ⬜ pending |
| FORG-04 | eviction recoverable + auditable, never hard-delete | cold-store record readable; JSONL audit entry present; no DELETE-from-t1 path | `uv run --extra dev pytest -q` | ⬜ pending |
| RECALL-03 | re-rank by relevance × salience × recency | re-rank order assertion on seeded records | `uv run --extra dev pytest tests/test_packer.py -q` | ⬜ pending |
| RECALL-04 | pack summaries under caller token budget | packed token cost ≤ budget | `uv run --extra dev pytest tests/test_packer.py -q` | ⬜ pending |
| RECALL-05 | two-pass reserves protected/active-constraint first | **adversarial test**: flood off-topic history, protected fact still in packed output | `uv run --extra dev pytest tests/test_packer.py -q` | ⬜ pending |
| CONS-09 | stable records promoted into T2 vault | confirmed high-salience record appears in vault after consolidate | `uv run --extra dev pytest tests/test_vault.py -q` | ⬜ pending |
| TIER-03 | T2 vault: merged, deduped, human-readable, git-versioned | vault markdown file written + dedup assertion | `uv run --extra dev pytest tests/test_vault.py -q` | ⬜ pending |
| IFACE-02 | MCP server exposes the 5 verbs as thin tools | FastMCP in-process client lists 5 tools + a remember→recall round-trip delegates to engine | `uv run --extra dev pytest tests/test_mcp.py -q` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_forgetting.py` — eviction + FORG-03 Hypothesis property test stubs
- [ ] `tests/test_packer.py` — re-rank + budget + RECALL-05 adversarial test stubs
- [ ] `tests/test_vault.py` — promotion + vault format stubs
- [ ] `tests/test_mcp.py` — FastMCP in-process client tool-surface stubs
- [ ] `pyproject.toml` — add `fastmcp>=3.4.2,<4`, `tiktoken>=0.13` (runtime), `hypothesis>=6.155` (dev)
- [ ] `src/mnema/ports/vault.py` — VaultStore Protocol (Wave 0 dependency for vault tests)

*Framework installed (Phase 1); Wave 0 adds 3 new deps + the Phase 3 test files + the VaultStore Protocol.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| tiktoken wheel installs on the Windows dev machine | RECALL-04 | Binary wheel; verified available in research but confirm at lock time | `uv run --extra dev python -c "import tiktoken; print(tiktoken.get_encoding('cl100k_base').encode('hello')[:3])"` — expect token ints (ByteLengthCounter fallback covers failure) |
| MCP server starts over stdio | IFACE-02 | Transport-level; in-process client covers the tool surface automatically | `uv run python -m mnema.mcp.server` (smoke; Ctrl-C) — optional |

*Core behaviors all have automated verification (in-process client covers the MCP tool surface without a transport).*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (deps, test files, VaultStore Protocol)
- [ ] No watch-mode flags
- [ ] Feedback latency < 12s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
