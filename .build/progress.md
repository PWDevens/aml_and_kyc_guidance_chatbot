# Progress ledger — full-build loop

## Done (before this loop started)
- **Phase 0** (`.pipeline/` iteration 1, 2026-06-29): eCFR loader, index builder,
  naive dense retrieval, Phi-4-mini ONNX generation, Flask+SSE app, minimal UI,
  5-item gold eval seed.
- **Phase 1, partial** (`.pipeline/` iteration 2, 2026-06-29): hybrid (BM25-RRF)
  retrieval built; measured naive vs hybrid on corrected 5-item gold set —
  **naive wins (no gain, ranking regression on hybrid)**; naive stays default.
  `RAG_MODE=hybrid` available but unproven. One gold-label defect found and fixed
  (1020.410 → 1010.410).

## Carried-over tech debt (from `.pipeline/STATUS.md` / `HANDOFF.md`)
- **F2 — CIP completeness.** Earlier answer's missing element was a
  `MAX_NEW_TOKENS=80` test-cap artifact, not a retrieval defect. Action item:
  Phase 3's `answer_verifier` should include a mandatory-element completeness
  check. Ceiling: revisit if verifier still misses omitted required elements.
- **Gold eval set too small (5 items)** to discriminate naive vs hybrid — saturated
  at hit@5=1.00 either way. Iteration 1 must expand it before re-judging hybrid.
- **Hybrid ranking regression**: BM25-RRF pulled a near-synonym CTR section above
  the controlling one on at least one query. Root-cause before re-adopting hybrid.

## Done
- **Iteration 1** (`.build/iter-1/`, 2026-07-02): FinCEN FedReg static loader
  (`src/rag/indexing/loaders/fedreg.py`); section-aware eCFR chunking
  (`_split_section`, budget 1500 chars); gold set expanded 5 → 25 validated items
  (clause lookups, dollar thresholds, 4 non-eCFR FedReg/advisory targets); exact-
  match SQLite answer cache (`src/rag/cache.py`) wired into `/chat_stream`.
  **Re-measured naive vs hybrid on the expanded set: both hit@5=1.00; hybrid
  reproduces the same near-synonym ranking-regression class documented in
  iteration 2 (e.g. 1010.330 outranks the controlling 1010.311, avg rank 1.28 vs
  naive's 1.44) — naive stays default per the "ties → naive" rule.** Added the
  cross-encoder reranker as a new `hybrid_rerank` mode (not default) because it
  demonstrably fixes every regressed item (avg rank 1.12, all 3 regressions back
  to rank 1) — AC-5's bar was met. Full details + numbers in
  `.build/iter-1/changes.md`.

## Done (cont.)
- **Iteration 1 — senior-PM gate: SHIP** (2026-07-02, re-gate; `.build/iter-1/verdict.md`
  now overwritten to SHIP). First pass was NEEDS WORK on a single required fix (F1: the
  literal word "ponytail" in three new files' module docstrings — an explicit user
  constraint). Orchestrator applied F1 as a docstring-only reword (zero behavior change).
  **Re-gate verified independently:**
  - F1 fixed, checked four ways: (a) direct `grep -i ponytail` over the 3 named files →
    none; (b) `git diff HEAD | grep -i '^+.*ponytail'` → none (no added line reintroduces
    it); (c) whole-diff any-occurrence scan → 4 pre-existing context lines + 1 *removal*
    (the pre-existing `# ponytail:` comment in `models.py` deleted by the earlier
    onnxruntime-genai fix), **zero `+` additions** — the word count went *down* by one;
    (d) whole-working-tree untracked-file scan → none (the 3 fixed files are new/untracked,
    so `git diff HEAD` doesn't surface them — hence the direct scan). The only remaining
    tree occurrence is `tests/test_smoke.py:4`, a tracked, unmodified Phase-0 file,
    correctly untouched and out of F1's scope.
  - Docstring edits confirmed purely cosmetic on re-read — original intent preserved
    (`cache.py`: one-table/no-ORM note; `fedreg.py`: abstract-only deferral note;
    `test_cache.py`: tempfile/no-framework note). No code, logic, signatures, or SQL
    touched.
  - Suite re-run by the gate: `py -3.12 -m pytest tests/ -q` → **19 passed in 43.92s**
    (not taken on the orchestrator's word). All 7 ACs + security/scope/reliability/
    tech-debt ledger remain satisfied from the first pass (unchanged by a docstring-only
    edit). **Iteration 1 is complete and ships.**

## Accepted tech-debt from Iteration 1 (bounded, with upgrade paths — carry forward)
- **FedReg loader is abstract-only.** No `full_text_xml_url` fetch/parse. Ceiling: if
  abstract text proves too thin in a later eval round, add an XML fetch+flatten step
  mirroring `ecfr._text()`'s `itertext()` approach.
- **Answer cache has no eviction/TTL.** `data/cache.db` grows unbounded. Ceiling: add a
  `created_at` column + a `DELETE … WHERE created_at < ?` sweep or a row-count LRU cap
  when the local demo DB size becomes a real concern.
- **No CFR-reference filtering of FedReg docs** — every FinCEN FedReg doc since
  2020-01-01 is indexed regardless of `cfr_references` relevance. Explicitly deferred to
  Phase-2 ETL rules R1–R3.
- **`hybrid_rerank` reranker model is lazy-loaded** (`lru_cache`) on first request, not
  warmed at startup — first `hybrid_rerank` request in a process pays the model-load
  cost. Fine for the demo.
- **`scripts/eval.py` hardcodes the "naive baseline" summary label** regardless of
  `RAG_MODE` (pre-existing Phase-0 wart; not in iter-1's required scope). One-line label
  fix whenever `eval.py` is next touched.

## Next
- **Iteration 2 — Phase 2: trigger-based ETL** (per `.build/backlog.md`). Goal: the corpus
  updates itself incrementally when FinCEN/eCFR publish changes, with a provenance ledger
  (`docs/ETL_AND_TRIGGERS.md`). Acceptance criteria: `src/etl/watchers/` (fedreg.py,
  ecfr.py) polling from a stored watermark; rules engine `src/etl/rules.py` implementing
  R1–R4; upsert-by-citation load (delete+add, no stale dupes) with watermark advancing
  only on success (R8 atomic/retriable); `data/etl_state.db` watermarks + provenance
  ledger; `GET /corpus_status` reporting `as_of` / last-run / per-source counts; a
  recorded-fixture FinCEN change detected + ingested incrementally, idempotent on re-run.
  Out of scope: R5/R6 (FAQ/graph sync — Phase 3), R7 (FFIEC — Phase 3), scheduled-CI
  auto-PR (needs a real remote — document as a manual follow-up).
  - **Carry into Iteration 2** the Phase-2-deferred item already logged below: no
    CFR-reference filtering of FedReg docs yet (deferred to ETL rules R1–R3).
- **Natural later-iteration candidate (not for Iteration 2):** the measured numbers favor
  `hybrid_rerank` (avg rank 1.12, term_recall 1.00 vs naive's 0.92). AC-4 was scoped to a
  naive-vs-hybrid decision only, so promoting `hybrid_rerank` to default is a *new*
  evidence-based decision for a later iteration to make deliberately — not a gap in
  iteration 1.

## Blockers
- None. (F1 is a required fix, not a blocker — no irreversible action, no correctness or
  security risk. No irreversible action is required by the next iteration either.)

## Manual follow-ups for the user (accumulate here, do not perform)
- No git remote configured — repo was `git init`'d locally at loop kickoff so each
  iteration is diffable. Push to a remote (e.g. GitHub) is the user's call.
- Machine migration note in `.pipeline/HANDOFF.md` §0b (RTX 5070 GPU build path) is
  informational only; this loop runs CPU-only per the project's default.
- **`onnxruntime-genai` version drift — FIXED by orchestrator (2026-07-02,
  outside any iteration spec).** `pip install -r requirements.txt` pulled
  `onnxruntime-genai` 0.14.1 (HANDOFF.md documents 0.5.2 from the prior
  machine); 0.14.1 dropped `GeneratorParams.input_ids` and
  `Generator.compute_logits()` in favor of `Generator.append_tokens()`.
  Updated `src/rag/llm/models.py:stream()` to the new API (`gen.append_tokens(
  np.asarray([input_tokens], dtype=np.int32))`, no separate `compute_logits()`
  call). Verified with a real generation call against the locally-cached
  Phi-4-mini-instruct-onnx weights — produces a correct, grounded answer — and
  the full test suite (8/8) still passes. Noted the working version
  (`>=0.6`, tested 0.14.1) as a comment in `requirements.txt`; formal pinning
  stays deferred to Phase 5 per the existing header comment. Fixed ahead of the
  loop reaching it because it silently broke every live (non-cached,
  non-extractive) answer — directly blocking the user's "E2E version to test"
  goal — and the fix was small, isolated to one file, and low-risk.
