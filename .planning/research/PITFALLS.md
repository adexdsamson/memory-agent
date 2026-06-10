# Pitfalls Research

**Domain:** Provider-agnostic AI agent memory engine (tiered + dual-phase memory, supersession, decay, hybrid retrieval) — project MNEMA
**Researched:** 2026-06-10
**Confidence:** HIGH on provider-abstraction and retrieval traps (verified against current docs/papers); MEDIUM on memory-correctness race conditions (corroborated by multiple agent-memory writeups, but MNEMA's exact provisional-record design is novel); HIGH on evaluation/demo traps (taken directly from the build plan's own hard-won guidance).

Phase labels below map to the build plan's milestones: **W1** (T0/buffer/T1 + dense recall + 5-test harness), **W2** (consolidation + provisional reconciliation + BM25/graph/RRF), **W3** (forgetting + salience floor + budget packer + MCP), **W4** (demo + baseline + stretch benchmark). "Foundational" means it must be designed into the schema/interfaces before W1 code, not retrofitted.

---

## Critical Pitfalls

### Pitfall 1: The vector index silently couples to one embedder (dimension + normalization lock-in)

**What goes wrong:**
You build the pgvector column as `vector(1024)` for Qwen, populate the HNSW index, and ship. Later someone configures OpenAI `text-embedding-3-large` (3072-dim) or a local `mxbai-embed-large` (1024-dim but **unnormalized**). The column rejects the wrong-dimension vectors outright, or — worse — accepts same-dimension vectors from a different model and returns silently wrong rankings because the new model's vectors live in a different geometric space and (for unnormalized models) have different magnitudes. Cosine/IP distance math assumes one consistent space; mixing two embedders in one index produces drift that no error message flags.

**Why it happens:**
The embedding axis is treated as an implementation detail of "search" rather than a first-class provider axis with its own contract. Dimensionality and normalization are model properties, not engine properties, and they leak into the storage schema. OpenAI vectors are L2-normalized to length 1 (dot product == cosine); many local models (e.g. `mxbai-embed-large`) are **not** normalized — so the same distance operator gives different effective rankings. MNEMA's whole premise is independent LLM/embedding axes, which makes this the single highest-probability failure.

**How to avoid:**
- Store embeddings with their provenance: `embedding_model`, `embedding_dim`, `embedding_version` columns alongside the vector. The hot-path partial index must filter to the *currently configured* embedder, never blend models.
- Normalize on write at the adapter boundary: every embedding adapter returns L2-normalized vectors regardless of the underlying model, so the core only ever sees unit vectors and one distance operator. This makes Qwen, OpenAI, and local interchangeable for the distance math.
- Treat an embedder swap as a **reindex migration**, not a config flip. Provide a documented `reindex(new_embedder)` path that re-embeds T1 content from `source_refs`/`content`. Do not let a swap go live against a stale index.
- Pin `embedding_dim` per configuration and assert it at startup; refuse to start if the index dimension disagrees with the configured embedder.

**Warning signs:**
Recall quality drops sharply after a config change with no error; the same query returns different neighbors on two machines with "the same" data; an `INSERT` into the vector column throws a dimension error in a code path that "worked yesterday"; distance scores cluster near 0 or are oddly large (unnormalized vectors).

**Phase to address:** Foundational (schema design before W1). The `embedding_model`/`embedding_dim` columns and the normalize-at-adapter rule must exist before any vector is written. The `reindex` migration can land in W2 alongside the embedding adapter abstraction.

---

### Pitfall 2: Leaky storage/provider abstraction — backend quirks bleed into the core

**What goes wrong:**
The "swappable adapter" promise quietly breaks because backend-specific behavior leaks through the interface: pgvector's HNSW `ef_search` tuning, OSS-vs-S3 eventual-consistency semantics, DashScope's vs Anthropic's error shapes and rate-limit headers, or a vector backend that returns scores while another returns only ranks. Code in the core starts branching on `if backend == "pgvector"`, and the second backend never actually works because nobody exercised it.

**Why it happens:**
Adapters are written against exactly one concrete backend (the default Qwen+Alibaba stack) and the interface is reverse-engineered from that one implementation. Differences that "don't matter for the default" become baked-in assumptions. Object stores differ on read-after-write consistency; vector DBs differ on whether they expose raw scores, support metadata filtering during search (the `WHERE valid_until IS NULL` predicate), or return cosine vs L2.

**How to avoid:**
- Define each adapter interface in terms of **capabilities and guarantees**, not the default backend's behavior. Example guarantees: "vector adapter MUST support a metadata pre-filter equivalent to `valid_until IS NULL`"; "object adapter MUST provide read-after-write for a just-written key, or declare it doesn't and the engine degrades gracefully."
- Write a **conformance test suite** that every adapter must pass (same tests, different backend). Run it against at least two backends per axis from W2 onward — pgvector + one alternative, OSS + local FS. An adapter that hasn't passed conformance is not a supported backend.
- Normalize error/retry handling at the adapter boundary (see Pitfall 3) so the core sees one error taxonomy.
- Keep the RRF/ranking math backend-agnostic by consuming **ranks**, not scores, from vector/keyword adapters (this also helps Pitfall 5).

**Warning signs:**
`grep` finds backend names inside core logic; only one backend is ever tested in CI; the metadata filter is applied *after* retrieval in one backend and *during* retrieval in another (changes which records survive the k-cap); swapping backends needs code changes, not just config.

**Phase to address:** Foundational interface design (before W1), conformance suite in W2 when the second adapter per axis lands.

---

### Pitfall 3: Per-provider rate-limit / retry handling done once, for one provider

**What goes wrong:**
Retry/backoff is written against DashScope's behavior and 429 shape. Anthropic returns different rate-limit headers, different error bodies, and has separate token-bucket limits for input vs output tokens; a local model has no rate limit but can OOM or time out. The single retry path either hammers a provider into a longer ban, silently drops consolidation batches, or stalls the per-turn fast path waiting on a reasoning model that should never have been on the hot path.

**Why it happens:**
Rate limiting feels like a cross-cutting concern that can be "added later," but each provider's limits, headers, and idempotency semantics differ. Consolidation (batch, can wait/retry) and the per-turn write (latency-sensitive) have opposite retry needs but get one shared policy.

**How to avoid:**
- Each LLM/embedding adapter owns its own retry/backoff with provider-correct parsing of rate-limit headers and `Retry-After`. The core requests "do this call"; the adapter handles transient failures and surfaces a normalized `RateLimited`/`Transient`/`Fatal` taxonomy.
- Separate retry budgets for fast-path (fail fast, fall back to buffer+T0 only — never block the turn on the reasoning model) vs consolidation (patient retry, idempotent re-drain of staging).
- Make consolidation idempotent so a retried/duplicated batch can't double-write records (ties directly into Pitfall 4).
- Cheap model curates, expensive model only reasons — enforce this so the latency-sensitive path never depends on a rate-limited reasoning call.

**Warning signs:**
Backoff constants reference one provider's numbers; the fast write path makes a reasoning-model call; staging items vanish under load; switching the LLM provider produces a flood of un-retried 429s.

**Phase to address:** W1 for the fast-path failure boundary (never block the turn); W2 for consolidation idempotency and the per-adapter retry taxonomy.

---

### Pitfall 4: Consolidation race conditions corrupt provisional records (double-write, lost supersession, stale reconciliation)

**What goes wrong:**
A turn writes a provisional T1 record (one embedding, `provisional=true`). Before consolidation reconciles it, another turn states a contradiction, or consolidation runs concurrently with a new write, or a retried consolidation batch (Pitfall 3) re-extracts the same turn. Results: two live records for the same fact (provisional + consolidated duplicate), a supersession that points at a record that consolidation just merged away (dangling `superseded_by`), or the provisional flag never clears so a draft record stays in recall forever.

**Why it happens:**
The provisional write is the read-after-write fix, but it introduces a record that exists in two write paths (fast + slow) that can interleave. Multi-agent / concurrent-turn setups make simultaneous read+write on shared state common, and that is exactly where memory-conflict and duplicate-record bugs concentrate. Entity resolution during consolidation mutates the same rows the fast path may be touching.

**How to avoid:**
- Give every provisional record a durable link back to its `t0_id`/staging item so consolidation reconciles **by identity**, not by fuzzy re-extraction. Consolidation should find "the provisional record for this turn" and upgrade it in place, not create a parallel consolidated record.
- Make consolidation idempotent and single-writer per subject: process a staging batch in a transaction, and either use a per-subject lock/advisory lock or an `ON CONFLICT` upsert keyed on a stable extraction key so a re-drain can't duplicate.
- Reconcile provisional → confirmed as an atomic update (set `provisional=false`, write final embedding/salience) rather than insert-new + delete-old.
- Order operations so supersession sets `valid_until`/`superseded_by` in the same transaction that confirms the new record; never leave a dangling `superseded_by`.
- Add a sweeper/invariant: no record may stay `provisional=true` past N consolidation cycles (alarms if reconciliation is silently failing).

**Warning signs:**
Two live records (`valid_until IS NULL`) with the same subject+predicate; `superseded_by` pointing at a non-existent or merged-away id; recall returns a fact twice; `provisional=true` records older than the consolidation interval; duplicate counts climb under concurrent sessions.

**Phase to address:** W2 (consolidation + provisional reconciliation is exactly this milestone). Invariant tests belong in the W2 harness expansion.

---

### Pitfall 5: False supersession and entity-resolution errors retire the wrong (or a still-valid) fact

**What goes wrong:**
Entity resolution decides two records are "the same subject + same predicate" when they aren't, and active supersession sets `valid_until` on a record that is still true — or it treats a *refinement* ("vegetarian" → "pescatarian") as a contradiction when it might be an *addition*, or treats genuinely contradictory facts as mergeable. The agent then acts on a wrong model: drops a still-valid constraint, or keeps two contradictory live records because resolution missed the match. In a nutrition coach, false supersession of a dietary constraint is a correctness/safety event.

**Why it happens:**
LLM-based extraction and entity resolution are precision problems, and the dominant LLM-NER error is **wrong type / misclassification** (~38% of errors in studies), not boundary detection. "Same predicate" is fuzzy: `prefers spicy` vs `avoids spicy` share a predicate but contradict; `pescatarian` vs `vegetarian` overlap but one supersedes. A naive cosine-threshold match (e.g. 0.92) plus an LLM contradiction judge will both over- and under-fire.

**How to avoid:**
- Separate the two decisions explicitly: (a) *is this the same subject+predicate?* (entity resolution / linking) and (b) *does the new value contradict the old?* (supersession). Don't let one similarity score answer both.
- Require structured agreement, not just embedding similarity: match on `subject` + a normalized predicate/attribute key before invoking the contradiction judge. Use the graph adjacency table as the source of truth for entity links, not ad-hoc cosine.
- Make supersession reversible and auditable (it already evicts to recoverable cold storage; ensure `superseded_by` + `valid_until` are append-only/auditable so a wrong supersession can be undone and inspected).
- **Never auto-supersede a `fact`-type / high-salience record on an LLM contradiction alone** — protected facts (allergies) must require explicit `forget`/confirmation, never a probabilistic contradiction call. This protects the safety guarantee (see Pitfall 6).
- Tune precision over recall for supersession on safety-relevant types: prefer leaving two records than retiring a real constraint; surface unresolved contradictions for the next consolidation pass.

**Warning signs:**
A still-true constraint shows `valid_until` set; two contradictory facts both live; the agent "forgets" something the user never changed; supersession fires on refinements/additions; allergy or medical records ever get `valid_until` from consolidation rather than explicit `forget`.

**Phase to address:** W2 (supersession + entity resolution land here). The protected-fact carve-out from auto-supersession is a hard rule designed in W2 and verified by the W3 protected-fact test.

---

### Pitfall 6: The salience floor fails *silently* — the safety guarantee is asserted, not proven

**What goes wrong:**
The design says the peanut-allergy record (salience 1.0) "provably cannot be forgotten," but the actual decay condition is `keep_score(r) < FLOOR and r.salience < SALIENCE_FLOOR`. The guarantee depends on (a) the allergy actually getting salience 1.0 from an LLM judge, (b) `SALIENCE_FLOOR` being `<= 1.0` and the comparison being strict in the right direction, (c) nothing else (a buggy migration, a re-judge during consolidation, a merge that recomputes salience) ever lowering it, and (d) eviction being the *only* removal path. If the LLM salience judge ever scores an allergy at 0.8, or a merge averages salience, or a future "hard cleanup" path exists, the "provable" guarantee silently evaporates — and nothing alerts you because the record just quietly leaves the live set.

**Why it happens:**
"Provable" is being claimed for a property that is currently enforced by a runtime LLM judgment plus a floating-point comparison — i.e. it is *probabilistic and conditional*, not structural. The guarantee leans on the LLM correctly judging salience every time, which is the opposite of "by construction." This is the gap the quality gate flags.

**How to avoid (make it actually provable):**
- Make protected status a **structural property, not a learned score.** Add an explicit boolean `protected` (or a `type == 'fact'` + medical/safety tag) that pins salience to 1.0 and is set by deterministic classification (allergy/medical keywords, explicit user designation), not by the LLM salience judge alone. The decay pass excludes `protected` records *before* any score math: `if r.protected: continue` as the first line of the loop.
- The salience floor then becomes a secondary defense, not the primary one — two independent guards (structural `protected` skip + salience-floor comparison).
- **Prove it with an exhaustive/invariant test, not an example.** A test that runs the decay pass over a population including a protected record across extreme aged timestamps and asserts the protected record is never archived. Add a property test: for all records with `protected=true`, `archive_to_cold` is never called. This is the "PROVABLY protects" requirement — it must be a passing invariant in the harness, run on every change.
- Guard the salience field: consolidation/merge must never lower a `protected` record's salience; assert `salience == 1.0` post-merge for protected records.
- Audit every removal path: confirm `archive_to_cold` is the *only* way a live record leaves the live set, and that it is gated by the protected check. No hard-delete path may exist (already an Out-of-Scope guarantee — enforce it in code review and a test that asserts no DELETE on T1).

**Warning signs:**
The only thing protecting the allergy is an LLM-assigned 0.95–1.0 score; `SALIENCE_FLOOR` and `salience` are compared with the same constant used elsewhere; merge logic recomputes/averages salience; there exists any code path that removes a T1 record other than `archive_to_cold`; the protected-fact test is an example ("allergy survives one pass") rather than an invariant ("no protected record is ever archived under any decay input").

**Phase to address:** W3 (forgetting + salience floor + allergy pinning). The structural `protected` flag should be in the schema from the start (foundational), so the floor is a backstop and not the sole mechanism. The invariant test is a W3 gate.

---

### Pitfall 7: Read-after-write freshness hole reopens at the seams (buffer eviction, provisional gaps, cross-session pre-consolidation)

**What goes wrong:**
The buffer fixes within-session and the provisional write fixes cross-session-pre-consolidation — but the hole reopens at the boundaries: the buffer evicts turn K+1 just before recall, the `looks_like_durable_claim` heuristic misclassifies a real preference so no provisional write happens, or recall's `valid_until IS NULL` + dedupe logic drops the provisional record in favor of a stale consolidated one. The user states a preference, asks seconds later, and recall misses it — the exact "reads as broken" failure the design exists to prevent.

**Why it happens:**
Freshness is handled by three cooperating mechanisms (buffer, provisional write, consolidation) with handoff windows between them. The heuristic classifier is a precision/recall tradeoff; a missed durable claim falls into a gap where neither buffer (evicted) nor T1 (never written) has it. Dedupe between buffer candidates and T1 can prefer the wrong copy.

**How to avoid:**
- Make the buffer union in recall authoritative for recency: when a buffer candidate and a T1 record conflict, the **buffer/most-recent wins** in dedupe, never the older consolidated record.
- Size the buffer to comfortably exceed a single session's turn count for the demo/use case, and back it with T0 so an evicted turn is still recoverable.
- Bias `looks_like_durable_claim` toward recall (over-write provisional records rather than miss real ones); the cost of a spurious provisional record is one embedding call and a later merge — cheap. The cost of a missed durable claim is the freshness hole.
- Add a freshness test as a first-class harness case: state preference this turn → recall it next turn (buffer); state it → simulate new session before consolidation → recall it (provisional). Both must pass before claiming the hole is closed.

**Warning signs:**
Recall misses a just-stated preference; the durable-claim heuristic skips obvious preferences; dedupe surfaces a stale consolidated record over a fresher provisional/buffer one; freshness only tested same-turn, not across the session boundary.

**Phase to address:** W1 (buffer + the within-session freshness test); W2 (provisional write + cross-session-pre-consolidation freshness test). Dedupe-prefers-fresher rule lands in W2/W3 with the recall packer.

---

### Pitfall 8: RRF fusion pitfalls — parameter sensitivity, score-vs-rank mixing, and the critical constraint lost under budget

**What goes wrong:**
Three related failures: (1) RRF is used because "it avoids score normalization," but it is **sensitive to its `k` constant** and to the rank cutoffs of each list — a poorly chosen `k` or uneven list lengths (dense k=30, sparse k=30, graph variable) skews fusion. (2) Someone "improves" RRF by mixing in raw scores, reintroducing the BM25 (unbounded) vs cosine ([0,1]) incompatibility RRF was meant to dodge — a single BM25 outlier then dominates. (3) After fusion, the salience/recency re-rank and the token-budget cut drop the one safety-critical constraint (the allergy) below the budget line, so recall is plausible but missing the fact that matters most.

**Why it happens:**
RRF's reputation as "tuning-free" is overstated — research shows it is parameter-sensitive and that convex score combination can beat it in/out of domain. Heterogeneous backends return scores in different spaces (Pitfall 2), tempting score-mixing. The budget packer is greedy by `rrf_score * salience * recency`; a high-recall query can fill the budget with merely-relevant items before the critical-but-not-top-ranked constraint is reached.

**How to avoid:**
- Fuse on **ranks only** (true RRF); do not mix raw heterogeneous scores. Keep `k` as a tuned, documented constant and test fusion quality when list lengths change.
- Use balanced per-list cutoffs and document them; if graph expansion returns variable counts, cap it so it can't dominate or starve fusion.
- **Reserve budget for protected/critical constraints.** The packer must guarantee that `protected`/high-salience constraints (allergies, hard dietary limits) are packed *first* and *always*, before the greedy relevance fill — a two-pass packer: (1) pack all protected/active-constraint records, (2) fill remaining budget by RRF-relevance. This directly satisfies the "recall stays under budget and still surfaces the critical constraint" capability.
- Test the budget case adversarially: large history + a query unrelated to the allergy must still surface the allergy constraint within budget.

**Warning signs:**
Changing `k` swings result quality a lot; a single keyword-heavy doc dominates results (score leakage); recall under a tight budget omits the allergy when history is large; the packer is single-pass greedy with no reserved slot for protected facts.

**Phase to address:** W2 (RRF implementation — ranks-only rule, `k` documentation); W3 (budget packer with the protected-first two-pass reservation, and the adversarial budget test).

---

### Pitfall 9: Stale-vs-fresh ranking — recency/salience weights fight each other

**What goes wrong:**
The re-rank `rrf_score * (0.5 + 0.5*salience) * recency_weight` can let a high-salience-but-superseded-adjacent record outrank the fresh truth, or let recency bury a stable high-salience fact. A superseded record should be filtered by `valid_until IS NULL`, but if that filter is missed in any path (graph expand, buffer union, BM25), a stale record re-enters ranking and the salience multiplier keeps it near the top.

**Why it happens:**
Three retrieval sources (dense, sparse, graph) plus buffer each need the `valid_until IS NULL` filter; it's easy to apply it on the dense `WHERE` clause and forget it on BM25 or graph expansion. Weight tuning that makes the decay demo look good can over-suppress stable facts.

**How to avoid:**
- Apply the `valid_until IS NULL` live-records filter **uniformly across every retrieval path** (dense, sparse, graph expand) — ideally enforced in the adapter layer (Pitfall 2's guarantee) so no path can skip it.
- Keep supersession (hard filter) and decay (soft recency weight) as separate mechanisms: superseded facts are *filtered out*, not *down-weighted*. Down-weighting a superseded fact is a bug — it should be invisible to live recall.
- Verify the supersession filter fires as its own test (the demo "show the old vegetarian record with `valid_until` set" is really proving this filter — make it a harness assertion, not just a demo visual).

**Warning signs:**
A superseded record appears in recall results; graph expansion or BM25 returns records with `valid_until` set; tuning recency to make decay demoable suppresses a stable fact the user expects.

**Phase to address:** W2 (uniform filter across retrieval paths, supersession-filter test); W3 (recency/salience weight tuning with the budget/protected tests as guardrails).

---

### Pitfall 10: Evaluation traps — anchoring on disputed headline numbers; public benchmarks eat the timeline

**What goes wrong:**
Two failures the build plan already calls out: (1) Anchoring on MemPalace's 96.6%/100% headline numbers as a target — they are disputed as tuned on specific failing questions, so chasing them sets a false bar and a misleading comparison. (2) Treating LongMemEval/LoCoMo as a primary deliverable — they ingest ~53 sessions per question and the wiring can consume a week with nothing demoable to show, starving the actual engine work and the demo.

**Why it happens:**
Public numbers are attractive for credibility; benchmarks feel like the "rigorous" choice. But headline numbers without methodology are not comparable, and heavy benchmark harnesses are a classic time sink that produces no demo artifact.

**How to avoid:**
- Build the **custom 5→20+ test harness first**, mapped 1:1 to the four capabilities (storage/recall, freshness, forgetting/supersession, protected-fact, budget). It doubles as the demo script and the regression suite for every pitfall above.
- Report **your own numbers with stated methodology** (before/after: naive "stuff the transcript" vs MNEMA on the same suite). Do not cite or target MemPalace's disputed numbers.
- Treat LongMemEval/LoCoMo as a **W4 stretch only**, behind the custom suite and the demo. Add exactly one, only if time allows.

**Warning signs:**
A roadmap line item is "beat 96.6%"; week 1 is being spent wiring a 53-session benchmark; there's no before/after baseline on the custom suite; the harness isn't doubling as the demo script.

**Phase to address:** W1 (5-test custom harness — first deliverable); W3 (before/after baseline); W4 (benchmark as stretch, gated behind everything else).

---

### Pitfall 11: Demo traps — time-decay on a wall clock, and outcome-without-mechanism

**What goes wrong:**
(1) Trying to demo forgetting via real elapsed time — decay-by-real-time is undemoable in 3 minutes and will appear to "do nothing" on stage. (2) Showing only the *outcome* ("agent picked salmon") without the *mechanism* (the old vegetarian record with `valid_until` set and `superseded_by` pointing at the new record), so a judge can't tell whether memory worked or the model just guessed. (3) Demoing decay live and accidentally evicting the protected allergy because the decay weights weren't seeded/controlled — turning the safety story into a safety failure on camera.

**Why it happens:**
Decay is inherently slow; the visible payoff (eviction) requires aged timestamps. Outcomes are easy to show, mechanisms require surfacing internal state. Live decay over a real population is nondeterministic if not seeded.

**How to avoid:**
- **Never demo time-decay on a wall clock.** Seed records with backdated timestamps and run the decay pass on stage; show one transient evicted to cold *and then recovered*, with the allergy (salience 1.0 / `protected`) visibly untouched.
- **Lead with supersession** (instant, legible) and always show the mechanism: the retired record with `valid_until` + `superseded_by`. Surface internal state, not just the chat answer.
- Inject **summaries by default**; expand verbatim only on demand — demonstrates the budget discipline.
- Rehearse the decay pass on a fixed, seeded fixture so eviction is deterministic and the protected fact provably survives on stage (reuse the W3 invariant test's fixture).

**Warning signs:**
The demo plan waits for real time to pass; the supersession demo shows only the chat reply, not the record state; the decay demo runs on un-seeded live data; the protected fact isn't explicitly shown as surviving.

**Phase to address:** W4 (demo traces + video), but the seeded backdated-timestamp fixture and "surface `valid_until`/`superseded_by`" capability must be designed in W2–W3 so the demo can use them.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcode the default Qwen+Alibaba stack everywhere "for now" | Fast W1 end-to-end | Adapter layer becomes a fiction; second provider never works (Pitfall 2) | Never — the product *is* portability; define interfaces first even if only one impl exists |
| Single shared retry policy for all providers | Less code in W1 | Per-provider 429 storms, fast-path blocked on reasoning model (Pitfall 3) | MVP only if the fast path already fails-fast to buffer+T0 |
| Salience floor as the *only* protection for safety facts | Matches the build-plan formula | Guarantee is probabilistic, not provable; LLM mis-judge silently forgets an allergy (Pitfall 6) | Never for safety-critical types — add structural `protected` flag |
| Apply `valid_until IS NULL` only on the dense path | Faster to write recall | Superseded records leak via BM25/graph (Pitfall 9) | Never — enforce uniformly at adapter layer |
| Skip the embedding provenance columns | Simpler schema | Silent ranking drift on embedder swap; no clean reindex path (Pitfall 1) | Never — these are foundational |
| Provisional write creates a parallel record reconciled by re-extraction | Simpler fast path | Duplicate live records, dangling supersession (Pitfall 4) | Never — reconcile by `t0_id` identity, upgrade in place |
| Single-pass greedy budget packer | Simple recall | Critical constraint dropped under budget (Pitfall 8) | Never for safety — reserve protected slots first |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| pgvector / HNSW | Fixed-dim column, no provenance, blend two embedders in one index | `embedding_model`/`embedding_dim`/`embedding_version` columns; normalize-at-adapter; reindex on swap |
| OSS ↔ S3 ↔ local FS | Assume read-after-write consistency from the default | Declare the consistency guarantee in the adapter contract; T0 read after write must be safe or degrade gracefully |
| DashScope (Qwen) vs Anthropic | One retry/backoff path, one error shape, reasoning model on hot path | Per-adapter retry with provider-correct headers; normalized `Transient/RateLimited/Fatal`; reasoning model never on the per-turn path |
| Token counting | Use `tiktoken` for the budget regardless of provider | Each LLM has its own tokenizer (Claude BPE ≠ tiktoken cl100k/o200k); use the configured provider's official token counter, or budget conservatively with a margin |
| Vector vs keyword vs graph adapters | Mix raw scores across backends in RRF | Fuse on ranks only; consume ranks from each adapter (backend-agnostic) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full-table scan on decay/recall (no partial index) | Recall latency climbs as T1 grows | Partial index `WHERE valid_until IS NULL`; HNSW on embedding | Tens of thousands of records |
| Embedding/reasoning call on the per-turn hot path | Turn latency spikes, feels laggy | Fast path = T0 append + buffer + at most ONE embedding (provisional); no reasoning call | Immediately under interactive load |
| Consolidation re-embeds everything each run | Cost/time grows with history | Only embed new/changed records; reconcile provisional in place | Months of history |
| Token-count the whole transcript per recall | Slow recall, redundant work | Pre-store `tokens(summary)` per record; pack summaries, not full content | Large histories (the budget case) |
| Graph expansion unbounded hops | Latency + fusion skew | Cap hops=1 and result count (per build plan) | Dense graphs |

## Security / Safety Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Provider API keys per-axis stored insecurely / logged | Credential leak across multiple providers (Qwen, Anthropic, OSS, S3) | Secrets via env/secret manager per adapter; never log request bodies with keys |
| Protected (medical/allergy) facts subject to probabilistic forgetting | Dangerous recommendation (peanuts to allergic user) — the headline safety failure | Structural `protected` flag + decay skip + invariant test (Pitfall 6) |
| Auto-supersession can retire a safety constraint | Agent drops a still-valid allergy/restriction | Never auto-supersede `fact`/protected types on LLM contradiction; require explicit `forget` (Pitfall 5) |
| Hard-delete path exists for T1 | Irrecoverable loss of a constraint; no audit trail | Eviction is archive-to-cold only; test asserts no DELETE on T1 (Out-of-Scope guarantee enforced) |
| PII in T0 raw log with no access control | Verbatim personal/health data exposed | Treat T0 as sensitive cold store; access-control `expand(id)`; document retention |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Read-after-write hole | "I just told you that" — agent feels broken | Buffer + provisional write + buffer-wins dedupe (Pitfall 7) |
| Agent acts on superseded preference | "I told you I eat fish now" — feels like it doesn't listen | Supersession filter on all retrieval paths (Pitfall 9) |
| Recall omits the critical constraint under budget | Unsafe/irrelevant suggestion despite "having" the fact | Protected-first two-pass packer (Pitfall 8) |
| Over-injecting verbatim instead of summaries | Wastes budget, slower, less coherent | Summaries by default, `expand(id)` on demand |

## "Looks Done But Isn't" Checklist

- [ ] **Provider abstraction:** Often missing a *second* working backend per axis — verify the conformance suite passes against pgvector+alt and OSS+localFS, not just the default.
- [ ] **Embedder swap:** Often missing the reindex path and provenance columns — verify swapping embedders triggers/requires reindex and the index refuses mismatched dims at startup.
- [ ] **Salience floor:** Often "proven" by one example — verify an *invariant* test asserts no `protected` record is ever archived under any decay input, and merge can't lower protected salience.
- [ ] **Supersession:** Often shows outcome only — verify a test asserts `valid_until` + `superseded_by` are set and the superseded record is absent from *all* recall paths (dense, BM25, graph, buffer).
- [ ] **Freshness:** Often tested same-turn only — verify both within-session (buffer) and cross-session-pre-consolidation (provisional) tests pass.
- [ ] **Budget recall:** Often tested on relevant queries only — verify the adversarial case (large history, off-topic query) still surfaces the allergy within budget.
- [ ] **Consolidation:** Often missing idempotency — verify a re-drained/duplicated staging batch produces no duplicate live records and no dangling `superseded_by`.
- [ ] **Token budget:** Often using the wrong tokenizer — verify the count matches the *configured* LLM's tokenizer (or has a safety margin), not always tiktoken.
- [ ] **Demo:** Often relies on wall-clock decay — verify the decay demo runs on a seeded backdated fixture and the protected fact visibly survives.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Embedder swap with no provenance/reindex (Pitfall 1) | HIGH | Add provenance columns, re-embed all T1 from `content`/`source_refs`, rebuild HNSW; until then pin to original embedder |
| False supersession retired a real fact (Pitfall 5) | LOW–MEDIUM | `superseded_by`/`valid_until` are auditable/reversible — un-set `valid_until`, restore from cold; add the type to the never-auto-supersede list |
| Salience floor failed, protected fact archived (Pitfall 6) | LOW to recover record, HIGH to trust | Recover from cold (nothing hard-deleted); then fix root cause: add structural `protected` skip + invariant test before re-enabling decay |
| Consolidation produced duplicates (Pitfall 4) | MEDIUM | Dedup by subject+predicate, keep newest live, archive rest; add idempotency key + per-subject lock |
| Leaky abstraction, 2nd backend never worked (Pitfall 2) | MEDIUM–HIGH | Extract backend-specific branches behind capability flags; write conformance suite; fix the failing adapter to the contract |
| Superseded record leaked into recall (Pitfall 9) | LOW | Add `valid_until IS NULL` to the offending path (BM25/graph); enforce at adapter layer; add the leak as a regression test |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 — Embedder dimension/normalization lock-in | Foundational schema (W1); reindex in W2 | Startup dim-assert; swap-embedder test triggers reindex; normalized vectors at adapter |
| 2 — Leaky provider/storage abstraction | Foundational interfaces (W1); conformance W2 | Conformance suite passes on 2 backends/axis; no backend name in core |
| 3 — Per-provider rate-limit/retry | W1 (fast-path boundary); W2 (consolidation idempotency) | Fast path never calls reasoning model; provider-switch produces no 429 storm |
| 4 — Consolidation race / provisional corruption | W2 | Re-drain produces no duplicates; no dangling `superseded_by`; no stale `provisional=true` |
| 5 — False supersession / entity-resolution error | W2 | Still-valid facts never get `valid_until` from consolidation; protected types excluded from auto-supersession |
| 6 — Salience floor fails silently | Schema W1 (`protected`); enforcement + invariant W3 | Property test: no `protected` record archived under any decay input; merge can't lower protected salience |
| 7 — Read-after-write freshness hole | W1 (buffer); W2 (provisional) | Within-session and cross-session-pre-consolidation freshness tests pass; buffer wins dedupe |
| 8 — RRF fusion / critical constraint under budget | W2 (RRF ranks-only); W3 (two-pass packer) | Ranks-only fusion; adversarial budget test surfaces allergy |
| 9 — Stale vs fresh ranking | W2 (uniform filter); W3 (weight tuning) | Superseded record absent from all 4 recall paths |
| 10 — Evaluation anchoring / benchmark sink | W1 (custom harness first); W3 (baseline); W4 (benchmark stretch) | 5→20+ custom tests exist before any benchmark; own numbers + methodology; no "beat 96.6%" goal |
| 11 — Demo wall-clock decay / outcome-without-mechanism | W2–W3 (seeded fixtures + state surfacing); W4 (demo) | Decay demo on backdated fixture; supersession shows record state; protected fact survives on stage |

## Sources

- Build plan and project doc (primary, authoritative for MNEMA's own design + eval/demo discipline): `mnema-build-plan.md`, `.planning/PROJECT.md`
- RRF parameter sensitivity & score-incompatibility: [An Analysis of Fusion Functions for Hybrid Retrieval (ACM TOIS)](https://dl.acm.org/doi/full/10.1145/3596512); [Hybrid retrieval with RRF: the score normalization problem (Chauzov)](https://avchauzov.github.io/blog/2025/hybrid-retrieval-rrf-rank-fusion/); [Hybrid Search in RAG (GoPenAI)](https://blog.gopenai.com/hybrid-search-in-rag-dense-sparse-bm25-splade-reciprocal-rank-fusion-and-when-to-use-which-fafe4fd6156e)
- Embedding dimension/normalization mismatch across providers: [OpenAI Embeddings FAQ](https://help.openai.com/en/articles/6824809-embeddings-frequently-asked-questions); [Mismatch in similarity, OpenAI vs Azure (Microsoft Q&A)](https://learn.microsoft.com/en-us/answers/questions/2201216/mismatch-in-similarity-search-results-openai-vs-az); [Embedding Models Cheat Sheet 2026](https://techbytes.app/posts/embedding-models-semantic-search-2026-cheat-sheet/); [In Defense of Cosine Similarity: Normalization Eliminates Gauge Freedom (arXiv)](https://arxiv.org/pdf/2602.19393)
- Consolidation race conditions / duplicate records / entity resolution: [The Consolidation Problem in Agent Memory (Vectorize/Hindsight)](https://hindsight.vectorize.io/blog/2026/05/21/agent-memory-consolidation); [AgentCore long-term memory deep dive (AWS)](https://aws.amazon.com/blogs/machine-learning/building-smarter-ai-agents-agentcore-long-term-memory-deep-dive/); [Can LLMs be used for Entity Resolution? (Tilores)](https://medium.com/tilo-tech/can-llms-be-used-for-entity-resolution-68053e357bae); [Assessment of Generative NER in the Era of LLMs (arXiv)](https://arxiv.org/pdf/2601.17898)
- Token counting differs across providers: [Count LLM Tokens with Tiktoken: Model-Specific Limits (Markaicode)](https://markaicode.com/llm-token-counting-tiktoken-model-limits/); [gpt-tokenizer vs js-tiktoken vs transformers (PkgPulse)](https://www.pkgpulse.com/guides/gpt-tokenizer-vs-js-tiktoken-vs-xenova-transformers-llm-2026)

---
*Pitfalls research for: provider-agnostic AI agent memory engine (MNEMA)*
*Researched: 2026-06-10*
