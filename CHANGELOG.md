# Changelog

All notable changes to this project are documented here, organized by iteration
and phase. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the overall plan.

---

## Phase 3, Iteration 1 — Local orchestration + semantic FAQ cache

**Date:** 2026-07-02 | **Spec:** [`.build/iter-3/spec.md`](.build/iter-3/spec.md) |
**Results:** [`.build/iter-3/changes.md`](.build/iter-3/changes.md)

### New features

- **Local-first orchestration layer** (`src/rag/orchestration/`). Query framing (acronym expansion, citation/numeric hint extraction), intent classification (6 intents: definitional, numeric, procedural, cross-reference, change, citation-lookup), retrieval routing to the 3 real modes (`naive`, `hybrid`, `hybrid_rerank`), and answer verification (lexical-overlap grounding check + mandatory-element completeness for CIP/SAR/CTR topics). Gated by `ORCHESTRATION` (default **false** — deliberate safety stance pending latency-inclusive measurement; measured retrieval win of +0.04 hit@k/+0.04 term_recall, but default kept off pending generation+verification latency assessment).

- **Semantic FAQ cache (Tier-1)** (`src/rag/faq/`). Pre-verified, curated Q&A fast-path sitting in front of the exact-match Tier-2 cache. 29 committed FAQ entries with real 31 CFR citations, seeded from `data/faq_seed.yaml` and built into `data/faq.db` by `scripts/seed_faq.py`. Max-over-paraphrases cosine matching with `FAQ_SIM_THRESHOLD` (default **0.83**, tuned empirically to pass genuine paraphrases while rejecting off-topic look-alikes). Topic-key cross-check guards against false positives (matched entry's topic keys must align with extracted citation/numeric hints). Gated by `FAQ_CACHE` (default **true** — human-curated answers are safe on by default).

- **Answer verification (new SSE event)** (`src/rag/orchestration/verify.py`). Generated answers are checked against retrieved context for lexical grounding (claim-by-claim token-set overlap). Ungrounded answers are declined (not cached, `verification` event carries `declined: true`). Incomplete answers (missing required elements like DOB in CIP responses) are annotated but not declined. New SSE event `verification` emitted by `/chat_stream` only when orchestration + answer verification run, carrying `{grounded, declined, unsupported_claims, missing_elements, note}`.

- **FAQ staleness tracking (R5)** — ETL rule triggered after successful R1/R4 upserts. Flags FAQ entries stale if their citations are updated, suppressing them from Tier-1 until re-curated. Provenance row recorded. Default suppression policy; `reverify_inline` deferred as bounded tech-debt.

- **New env vars** (all optional, with sensible defaults):
  - `ORCHESTRATION` (default `false`): enable/disable the orchestration layer.
  - `FAQ_CACHE` (default `true`): enable/disable Tier-1 semantic FAQ fast-path.
  - `FAQ_SIM_THRESHOLD` (default `0.83`): cosine-similarity threshold for FAQ hits.
  - `FAQ_TOPIC_CROSSCHECK` (default `true`): require matched FAQ entry's topic keys to align with extracted hints.
  - `FAQ_STALE_POLICY` (default `suppress`): staleness handling (only `suppress` is implemented; non-suppress values are treated as suppress with a tech-debt note).
  - `VERIFY_ANSWERS` (default `true`): run answer verification (only consulted when `ORCHESTRATION=true`).
  - `ORCHESTRATION_MAX_LLM_CALLS` (default `2`): budget for optional LLM escalation in verifier (not used this iteration; plumbing in place for future expansion).

### Configuration & integration

- `src/rag/config.py` — added 8 new environment variables (documented above) with the existing `_b()` / `os.getenv()` pattern.

- `src/app/api.py` — `/chat_stream` wiring order: (1) FAQ Tier-1 semantic hit → instant replay, (2) Tier-2 exact-match cache hit → reply, (3) orchestrated or non-orchestrated retrieve, (4) generate, (5) verify + emit `verification` event, (6) cache + citations. **Byte-identical collapse:** when `ORCHESTRATION=false` and `FAQ_CACHE=false`, flow is identical to Phase 2.

- `src/etl/rules.py` and `src/etl/pipeline.py` — R5 staleness rule added. After successful R1 (FinCEN final rule) or R4 (eCFR section) upsert, checks if any FAQ entry references the updated citation; flags matching entries stale and writes provenance row (`rule_id='R5'`, `action='flag_stale'`).

- `scripts/eval.py` — added `--compare` flag for on-vs-off orchestration evaluation (AC-9). Original baseline (`RAG_MODE=naive`) unchanged; new compare mode measures on-vs-off retrieval performance on the gold eval set.

### Measured results (AC-9)

Orchestration on-vs-off comparison on the 25-item gold set:

| Config | hit@k | term_recall |
|--------|-------|-------------|
| `ORCHESTRATION=false` (naive baseline) | 0.92 | 0.96 |
| `ORCHESTRATION=true` (per-intent routing) | 0.96 | 1.00 |
| Delta | +0.04 | +0.04 |

**Recommendation:** default stays `false` this iteration. The retrieval-only win is real and strong, but D6 explicitly requires "no latency regression that breaks the demo." This comparison measures retrieval only (not end-to-end latency including generation + verification buffering on a CPU-slow stack). A latency-inclusive measurement is needed before flipping the default. **This is a live decision for Iteration 4**, not closed.

### Decision notes

- **D3 threshold delta:** `docs/FAQ_CACHE.md` proposed `FAQ_SIM_THRESHOLD=0.92`; shipped as **0.83** per empirical measurement. Real paraphrases scored 0.79–0.88 against canonical questions; 0.92 would have missed them. 0.83 sits above measured off-topic ceiling (~0.70) with margin. Documented in `changes.md` per spec requirement to record divergence.

- **D5 `change_resolver` deferred:** The `change` intent is classified and routed to `hybrid_rerank` (same fallback as cross-reference), but no temporal-diff timeline is assembled. Deferral reason: depends on a version-history ledger Phase 2 did not build. Deferred with stated reason, documented in `changes.md` and `progress.md`.

- **D12 verifier mechanism:** Lexical-only (no LLM escalation this iteration). Optional gray-band LLM-entailment path is budgeted (`ORCHESTRATION_MAX_LLM_CALLS`) but not wired; ceiling documented for future expansion.

- **D13 classifier/framer:** Pure heuristic (no LLM fallback). Keyword-based intent classification, acronym glossary (15 entries: CTR, SAR, CDD, CIP, BSA, UBO, MSB, EDD, PEP, FBAR, AML, KYC, FinCEN, OFAC, SDN), citation/numeric hint regex, chit-chat stripping. Fully tested; LLM fallback stubbed per spec's "if time-constrained" allowance.

### API & internal changes

- `src/rag/faq/` — new package containing `embed.py` (request-time query embedding via `sentence_transformers`, `@lru_cache` singleton), `store.py` (SQLite FAQ store, mirrors `cache.py` style), `matcher.py` (semantic FAQ matching with threshold + cross-check).

- `src/rag/orchestration/` — new package containing `intents.py` (framing + classification), `router.py` (intent→mode dispatch with hard assertion on real modes only), `verify.py` (grounding + completeness), `planner.py` (orchestration state machine, per-request config assembly).

- `scripts/seed_faq.py` — idempotent script that builds `data/faq.db` from `data/faq_seed.yaml` using the same embedding model as the matcher (D1 requirement for cosine consistency).

- `data/faq_seed.yaml` — 29 curated FAQ entries, each with real 31 CFR citations verified against the live corpus.

### Tests

- `tests/test_faq_embed.py`, `tests/test_faq_matcher.py`, `tests/test_orchestration_skills.py`, `tests/test_chat_stream_orchestration.py`, `tests/test_faq_staleness_r5.py` — 57 new tests covering intent classification, framing, routing, verifier grounding/completeness, FAQ matching (paraphrase + cross-check), TTL/independence, staleness flagging.

- `test_iter3_adversarial.py` (19 tests, debugger stage) — additional event-order edge cases, FAQ threshold margin verification, verifier stopword-exclusion fix verification, DB isolation audit.

- **Existing tests:** All 47 pre-iter-3 tests pass unchanged (with one required fix to `test_chat_stream_cache.py`: tempdir isolation for both `cache_path` and new `faq_db_path` to prevent real FAQ seeded entries from intercepting test questions).

- **Full suite:** 123 tests pass (104 senior-dev handoff + 19 adversarial).

### Simplifications / deferred

- **No LLM-escalation path** (gray-band verifier claims). Infrastructure in place (`Budget` class); Phi-4 entailment wiring deferred as bounded tech-debt with clear ceiling.

- **No LLM fallback for classifier/framer** (stubbed per "if time-constrained"). Pure heuristic path is complete and tested.

- **R5 `reverify_inline` policy** — only `suppress` is implemented; non-suppress values accepted but treated as suppress. Bounded tech-debt; couples ETL to generation/verification, clear upgrade path.

- **`change_resolver` skill** — deferred (D5). `change` intent routes to `hybrid_rerank` (fallback); no temporal assembly. Iteration 4's "What changed timeline" explicitly conditional on this shipping.

- **R6 (graph rebuild sync), R7 (FFIEC ingest), R4b (eCFR removed-section deletion)** — all deferred as explicitly out-of-scope this iteration.

---

## Phase 2, Iteration 1 — Trigger-based ETL: watchers, rules engine, incremental upsert

**Date:** 2026-07-02 | **Spec:** [`.build/iter-2/spec.md`](.build/iter-2/spec.md) |
**Results:** [`.build/iter-2/changes.md`](.build/iter-2/changes.md)

### New features

- **Trigger-based ETL pipeline.** `src/etl/` module orchestrates incremental corpus updates keyed off FinCEN and eCFR change detection:
  - **Watchers** (`src/etl/watchers/fedreg.py`, `ecfr.py`) poll from stored watermarks, fetching only documents/sections changed since the last recorded position.
  - **Rules engine** (`src/etl/rules.py`, R1–R4) classifies each change: R1 (FinCEN final rule touching 31 CFR X), R2 (proposed rule), R3 (notice matching AML/KYC topic filter), R4 (eCFR section amended). CFR-reference filtering gates FedReg ingestion; only docs touching watched parts (`31 CFR 1010`, `1020`) or matching topical relevance are indexed.
  - **Incremental upsert-by-citation** (`src/rag/indexing/builder.upsert_by_citation`) deletes stale chunks for a citation, then adds new ones — idempotent, no full-index rebuilds, no duplicate chunks.
  - **Provenance ledger** (`data/etl_state.db`, table `provenance`) records every ingest action: rule ID, source, citation, action type (upsert/schedule/skip), timestamp, and success/error status. Completes the audit trail.

- **New ETL entrypoint:** `python -m scripts.etl_run` runs one ETL pass over both sources, advancing watermarks only on batch success (R8 atomicity contract — a mid-batch failure holds the watermark, allowing idempotent retry). Single-pass semantics; no scheduler loop this iteration (D7).

- **Extended `/corpus_status` API.** Added `last_etl_run` (ISO-8601 timestamp of the most recent successful ETL action, or `null` if ETL never ran) and `counts_by_source` (dict mapping source tag to chunk count in the live collection). Existing keys (`indexed`, `as_of`, `rag_mode`) preserved; 200/503 behavior unchanged.

### Carried-forward tech-debt resolved

- **CFR-reference filtering of FedReg documents** (iterated once, now complete). Iteration 1 indexed all FinCEN documents since 2020-01-01 regardless of relevance. Phase 2 implements R1–R3 classification: only FinCEN docs that either touch watched CFR sections (R1/R2) or match the AML/KYC topic filter (R3) are now indexed. Non-matching docs are recorded as skipped (`action='skip'` provenance row). Live run observed 12 skipped docs out of 197 total ingested, demonstrating the filter's effect.

### Configuration changes

New environment variables (and `src/rag/config.py` fields):

- `ETL_STATE_PATH` (str, default `ROOT/data/etl_state.db`): Path to the ETL watermarks + provenance ledger.
- `ETL_SCHEDULE` (str, default `"daily"`): Read for completeness; single-pass-only this iteration (D7).
- `ETL_FEDREG_SINCE` (str, default `"2020-01-01"`): Cold-start watermark for FedReg watcher (used if no watermark row exists in DB).
- `ETL_ECFR_SINCE` (str, default `"2020-01-01"`): Cold-start watermark floor for eCFR `issue_date` (same behavior as FedReg).

### Measured results

**Live ETL runs** (real API, real numbers) on a freshly-built index (402 chunks: 353 eCFR + 49 FedReg):

| Pass | fedreg detected/upserted/skipped | ecfr detected/upserted/skipped | fedreg watermark | ecfr watermark |
|------|----------------------------------|--------------------------------|------------------|----------------|
| 1 | 50 / 44 / 6 | 36 / 261 / 0 | 2025-01-17 | 2026-01-05 |
| 2 | 49 / 45 / 4 | 0 / 0 / 0 (idempotent) | 2025-01-17 | unchanged |
| 3 | 32 / 28 / 4 | 0 / 0 / 0 (idempotent) | 2026-06-25 | unchanged |

- eCFR catch-up completed in pass 1 (36 sections changed since 2020-01-01 across parts 1010 + 1020, 261 total chunks upserted); subsequent passes found no new changes.
- FedReg required 3 passes due to `FEDREG_MAX_DOCS=50` pagination cap per pass (oldest-first from 2020-01-01). Each pass advances the watermark to the newest doc it processed within its 50-doc window; multi-pass catch-up is expected behavior for large backlogs.
- Final state: 475 indexed chunks (353 eCFR + 30 fedreg_rule + 27 fedreg_proposed + 65 fincen_advisory), `etl_state.db` with 2 watermark rows + 197 provenance rows (rule distribution: 12 skipped, 62 R1, 22 R2, 65 R3, 36 R4), all status='success'.

### API & internal changes

- `src/etl/` — new ETL package (state, rules, watchers, pipeline orchestration).
- `src/rag/indexing/builder.py` — added `collection_exists(cfg)`, `upsert_by_citation(cfg, citation, records)`.
- `src/rag/indexing/loaders/ecfr.py` — added `changed_sections(title, chapter, part, since)` (queries `/versions` endpoint per D1), `load_section(title, chapter, part, section, as_of, chunk_char_budget)` (single-section re-fetch per D2).
- `src/rag/indexing/loaders/fedreg.py` — added `fetch_documents(agency, since, max_docs)` (returns raw API result dicts, enabling rule classification on `type`/`cfr_references`/`effective_on` before shaping).
- `src/app/api.py` — `/corpus_status` extended with `last_etl_run` and `counts_by_source`; existing behavior preserved.

### Edge cases and design notes

- **eCFR removed sections.** The `/versions` endpoint returns entries with `"removed": true` (e.g., `31 CFR 1010.655`, repealed 2020). These are filtered out in `changed_sections` — a removed section has no fetchable content, so R4 cannot re-embed it. This is a minimal scope addition to D1 (spec didn't anticipate the `removed` flag). Full deletion of stale corpus chunks for repealed sections is a follow-up (R4b).
- **R1 scheduling (no timer).** When a final rule is detected (R1), two provenance rows are written: one `action='upsert'` for the corpus write, one `action='schedule'` with `as_of=effective_on` to mark the eCFR re-pull due date. No timer/queue is built (D7); the actual re-pull happens when the eCFR watcher's `/versions` query next surfaces the amended section after the effective date.
- **Watermark idempotency.** Strict-after filtering ensures a run that reaches the watermark value doesn't re-fetch the boundary doc/section. Upsert-by-citation makes re-ingestion safe anyway (idempotent); the filter just avoids redundant embed work.
- **Mid-batch failure atomicity (R8).** If a single item in a batch raises during extract/transform/load, one `status='error'` provenance row is written for that item and the watermark for that source is **not** advanced — held at its pre-batch value. The next run re-processes the batch from the unadvanced watermark; upsert-by-citation makes re-ingest idempotent. No transactional rollback of corpus chunks (Chroma has none); rely on watermark-hold + upsert idempotency.

### Tests

19 pre-existing tests (Phase 0 + 1) + 17 new ETL-focused tests (10 rules, 2 upsert, 4 state, 1 live FedReg). Full suite: 36 tests pass (or 47 with tester's 11 additional gap-coverage tests). All offline tests deterministic; `test_etl_fedreg_live.py` uses real FedReg API with `pytest.skip` on network failure (network-tolerant, matching Phase 1's stance).

### Simplifications / deferred

- No CI auto-PR scheduler (GitHub Actions workflow, cloud credentials) — deferred to Phase 3+.
- No container entrypoint loop (Docker with `ETL_SCHEDULE` cron) — deferred to Phase 5.
- Separate Chroma collections for `proposed`/`advisory` docs — not created. Single `aml_kyc` collection with source-tag disambiguation (`fedreg_proposed`, `fincen_advisory` metadata) keeps scope minimal (D6).
- eCFR removed-section deletion (R4b, repealed-content cleanup) — follow-up iteration.

---

## Phase 1, Iteration 1 — Finish Phase 1: multi-mode retrieval + corpus breadth

**Date:** 2026-07-02 | **Spec:** [`.build/iter-1/spec.md`](.build/iter-1/spec.md) |
**Results:** [`.build/iter-1/changes.md`](.build/iter-1/changes.md)

### New features

- **FinCEN Federal Register corpus.** Static loader (`src/rag/indexing/loaders/fedreg.py`)
  ingests FinCEN final rules, proposed rules, and notices from the Federal Register API
  (default: 50 documents since 2020-01-01, configurable via `FEDREG_SINCE`, `FEDREG_MAX_DOCS`).
  Added 28 advisory notices, 8 final rules, and 14 proposed rules to the corpus alongside
  the existing eCFR 1010/1020 sections, broadening coverage of rulemakings and policy
  changes beyond in-force code.

- **Section-aware eCFR chunking.** Sections longer than a configurable budget (default
  1500 chars) are split on paragraph boundaries (`\n`-joined) into multiple retrievable
  chunks, each carrying the parent section's `citation`/metadata so citations resolve
  correctly. Sections under budget remain single chunks. Expanded the corpus from 105
  sections to 403 citable chunks without duplicating citations.

- **Exact-match answer cache (Tier-2).** SQLite cache in `src/rag/cache.py`, keyed on
  normalized question text (lowercase, whitespace collapsed). Wired into `/chat_stream`
  so a repeated (identically-phrased) question replays the cached answer without
  re-running retrieval or generation (configurable via `ANSWER_CACHE=true` / `false`).
  Caches only generated answers, not extractive fallback or "no match" responses. No
  eviction/TTL (small local demo; upgrading the strategy is deferred).

- **Cross-encoder reranker as `hybrid_rerank` mode.** New optional retrieval mode
  that reranks the hybrid (BM25-RRF) candidate pool using `cross-encoder/ms-marco-MiniLM-L-6-v2`.
  Added because it demonstrably fixes 3 ranking regressions that the plain hybrid mode
  exhibits on the expanded gold set. Not the default; `RAG_MODE=hybrid_rerank` to opt in.

- **Expanded gold eval set (5 → 25 items).** Validation against primary-source text
  before commit. Covers clause-number lookups, dollar thresholds ($10K CTR, $3K/5K
  recordkeeping, $250 CVC), beneficial-ownership requirements, and 4 non-eCFR FedReg
  targets (2022 BO rule, CTA implementation, Banco Delta Asia repeal, proposed CVC
  threshold reduction). Used to drive the naive-vs-hybrid decision and confirm the
  reranker's measured improvement.

### Configuration changes

New environment variables (and `src/rag/config.py` fields):

- `ANSWER_CACHE` (bool, default `true`): enable/disable the exact-match cache.
- `ANSWER_CACHE_PATH` (str, default `ROOT/data/cache.db`): cache database path.
- `FEDREG_AGENCY` (str, default `"financial-crimes-enforcement-network"`): FinCEN
  agency identifier for Federal Register API queries.
- `FEDREG_SINCE` (str, default `"2020-01-01"`): earliest publication date for
  Federal Register documents to index.
- `FEDREG_MAX_DOCS` (int, default `50`): maximum Federal Register documents to fetch.
- `CHUNK_CHAR_BUDGET` (int, default `1500`): character budget for eCFR section
  chunking (sections over this length are split on paragraph boundaries).

### Measured results

Re-ran retrieval eval on the 25-item gold set under both `naive` and `hybrid` modes
against a freshly-built 403-chunk corpus (353 eCFR + 50 FedReg documents):

| Mode | hit@5 | term_recall | avg rank | worst rank |
|------|-------|-------------|----------|------------|
| naive | 1.00 | 0.92 | 1.44 | 5 |
| hybrid | 1.00 | 0.92 | 1.28 | 3 |

Both modes tie on hit@5 and term_recall. Hybrid exhibits 3 **ranking regressions** —
same class as Phase 0 found — where a near-synonym (e.g., adjacent regulatory
section) outranks the controlling one. Per the spec ("If naive ties or wins, naive
stays default"), **`rag_mode` default remains `"naive"`**.

Tested the cross-encoder reranker on hybrid's output. All 3 regressions returned to
rank 1; worst rank in the set improved to 2. Measured reranking results:

| Mode | hit@5 | term_recall | avg rank |
|------|-------|-------------|----------|
| hybrid_rerank (actual) | 1.00 | 1.00 | 1.12 |

This fixes the regression, so the reranker code was added as a new mode. Not the
default (that decision is scoped to the narrower Phase 2), but available and proven.

### API & internal changes

- `src/rag/retrieval/factory.py`: Extended `_MODES` with `"hybrid_rerank"` mode.
  Fixed a correctness bug in hybrid's RRF fusion (was keyed on `citation`, which
  silently collapsed multiple chunks of one split section; re-keyed on unique chunk
  `id` to treat each chunk as an independent candidate). Added `_hybrid_rerank`
  function and a lazily-loaded `_load_cross_encoder` singleton.

- `src/rag/indexing/builder.py`: Extended metadata schema (`_META`) with
  `fedreg_doc_number` and `publication_date` (stored as strings for Chroma
  compatibility).

- `src/rag/indexing/loaders/ecfr.py`: Added `_split_section(text, budget)` helper
  that splits long sections on paragraph boundaries. Wired into `load_part` /
  `load_parts` via a `chunk_char_budget` parameter.

- `scripts/build_index.py`: Loads eCFR (chunked) and FedReg records, merges them,
  prints per-source counts, then builds the index.

- `src/app/api.py` `/chat_stream` handler: Checks cache before retrieval/generation.
  On a hit: streams the cached answer text (one `token` event) + stored `citations`
  + `done`. On a miss: runs retrieve→generate, accumulates the answer, writes cache
  (only for the generated path, not extractive fallback or "no match"), then streams
  normally.

### Tests

All 8 pre-existing tests pass (test_smoke, test_cache, test_fedreg_loader,
test_ecfr_chunking). Added 2 additional test files:

- `tests/test_chat_stream_cache.py`: End-to-end cache behavior (hit/miss,
  normalization, edge cases like disabled cache, extractive fallback, no-match
  fallback). Includes one real generation test to verify cache write shape.

- `tests/test_corpus_breadth.py`: Gold set size/schema, non-eCFR coverage, per-source
  counts, and FedReg citation resolution.

Full suite (19 total) passes fresh against the rebuilt index.

### Simplifications / deferred

- FedReg loader is abstract-only (does not fetch full-text XML). Upgrade path: add
  `full_text_xml_url` fetch+flatten if abstracts prove too thin.

- Cache has no eviction/TTL (small local demo). Upgrade path: add `created_at`
  column + sweep when size becomes a concern.

- CFR-reference filtering of FedReg docs not implemented (index all FinCEN docs
  regardless of 31 CFR relevance). Out of scope (Phase 2 ETL rules R1–R3).

- Reranker model lazy-loads on first call (no warm-cache at startup).

---

## Phase 0, Iteration 1–2 (prior to this changelog)

See [`.pipeline/STATUS.md`](.pipeline/STATUS.md) and
[`.pipeline/HANDOFF.md`](.pipeline/HANDOFF.md) for Phase-0 implementation summary
(eCFR loader, naive retrieval, Phi-4-mini generation, Flask+SSE, minimal UI,
hybrid retrieval exploration, 5-item gold seed).
