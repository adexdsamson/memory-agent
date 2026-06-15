# MNEMA Eval Report — Phase 5

**Date:** 2026-06-15
**Method:** Containment-based deterministic scoring (no LLM grading)
**Suite:** 3 scripted probes
**Summary:** MNEMA passed 3/3 probes; Naive passed 2/3 probes

## Results

| Probe | Naive Passes | MNEMA Passes | MNEMA Tokens | Naive Tokens |
|-------|-------------|-------------|--------------|--------------|
| Protected-fact retention | PASS | PASS | 13 | 21 |
| Superseded-fact avoidance | FAIL | PASS | 13 | 21 |
| Cross-session recall | PASS | PASS | 13 | 21 |

## Token Efficiency

- MNEMA recall budget: 300 tokens
- Average MNEMA tokens used: 13.0
- Average naive tokens: 21.0
- Token reduction: 38.1% fewer tokens with MNEMA vs naive full-transcript stuffing

## Methodology

All data is seeded deterministically using StubLLM and StubEmbedder — no network calls, no API credentials, and no randomness. Three scripted probes cover protected-fact retention (peanut allergy), superseded-fact avoidance (diet-preference update triggering a contradict verdict), and cross-session recall accuracy (allergy stated in session 1, recalled in session 2). Scoring is containment-based: a probe passes if and only if all required phrases are present (case-insensitive) and all excluded phrases are absent. For the supersession probe, the naive baseline fails because it includes both the original and the superseded copy of the preference (the same content appears more than once in the full transcript), while MNEMA's live-record filter ensures only the current record appears. Token counts use tiktoken cl100k_base, consistent with the recall(budget=) packer used internally by MNEMA. Re-running this eval on fresh seeded data produces identical numbers (deterministic).
