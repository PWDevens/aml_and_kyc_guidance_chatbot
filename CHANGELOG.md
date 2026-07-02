# Changelog

All notable changes to this project are documented here, organized by iteration
and phase. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the overall plan.

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
