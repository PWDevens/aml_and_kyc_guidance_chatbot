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

- **Iteration 2 — senior-PM gate: SHIP** (2026-07-02; `.build/iter-2/verdict.md`).
  Phase 2 trigger-based ETL. All 7 ACs met and demonstrably true. Verified independently
  at the gate (not on the reports' word):
  - **D4 (no `build()` in ETL path):** read `builder.py:60-73` — `upsert_by_citation`
    uses `get_or_create_collection` + `col.get(where=citation)` + `col.delete` + `col.add`;
    never `delete_collection`/`create_collection`. `build()` untouched. `pipeline.py` +
    `scripts/etl_run.py` import only `upsert_by_citation`.
  - **R8 (watermark advances only on success):** read `pipeline.py` control flow —
    `set_watermark` runs only in the `try/else` (batch loop completed with no raise); the
    `except` records one `error` provenance row and re-raises before any advance;
    `run_once` isolates each source so one source's failure can't corrupt the other's
    watermark. Confirmed by `test_etl_state.py::test_watermark_not_advanced_after_simulated_mid_batch_failure`.
  - **D3 (`chapter: null` intersection):** read `rules.py:19-25` — `touches_watched_cfr`
    never reads `chapter`, normalizes `title`(int/str)/`part` to str. Unit-tested.
  - **eCFR removed-section fix** (`ecfr.py:121`, `v.get("removed")` filter): judged a
    correct, in-scope production bug fix (a `removed:true` `/versions` entry has no
    fetchable text and 404s), not scope creep. Directly unit-covered by the tester's new
    `test_ecfr_changed_sections.py`.
  - **`data/chroma` deletion incident:** judged a process incident handled correctly —
    caught, reported (not hidden), restored via the normal `build_index`; gitignored
    derived data, no repo footprint, no data permanently lost. No penalty.
  - **Tester's 3 new gap-coverage files** (`test_ecfr_changed_sections.py`,
    `test_corpus_status_endpoint.py`, `test_etl_pipeline_r1_schedule.py`): read all three;
    they have real teeth (exercise production code paths, not tautologies).
  - **Suite re-run at the gate:** 46 deterministic tests pass in 34s + the 1 live FedReg
    test passes in 130s against the real API = **47 passed**, independently confirmed.
  - **Scope clean:** no "Do NOT create" path exists (no `faq`/`orchestration`/
    `graph_lightrag.py`/`ffiec.py`/`fincen.py`/`seed_faq.py`, no `.github/workflows`, no
    separate proposed/advisory collections); no `ponytail:` additions in any new src/test
    file; no new dependency; parameterized SQL throughout `state.py`. **Iteration 2 ships.**

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

## Accepted tech-debt from Iteration 2 (bounded, with upgrade paths — carry forward)
- **RESOLVED (was carried from iter-1): CFR-reference filtering of FedReg docs.** R1/R2
  (`touches_watched_cfr`) + R3 (`TOPIC_TERMS`) now gate every FedReg doc before ingest;
  non-matching docs get an `action='skip'` provenance row. The iter-1 deferral is closed.
- **eCFR "removed" sections are skipped, not deleted from the corpus.** A repealed 31 CFR
  section (e.g. `1010.655`) keeps its old chunks in `aml_kyc` from a prior build;
  `changed_sections` no longer trips on it, but nothing actively removes stale content for
  a repealed section. Ceiling: an R4b rule that upserts an empty record list for a removed
  citation (deleting its chunks with none replacing) — clean small follow-up, out of scope
  here because the spec's R4 interface assumes a fetchable change, not a removal.
- **R1 "schedule" is a provenance marker, not a timer/queue** (D7, spec-mandated). The
  actual eCFR re-pull happens whenever the eCFR watcher next surfaces the amended section
  after its `effective_on`. Ceiling: if a later phase needs an active due-date alert, query
  `provenance WHERE action='schedule' AND as_of <= today` rather than build a new mechanism.
- **No HTTP backoff/retry on watcher fetches** — a single `requests` call + `raise_for_status()`
  (spec allowed "a single retry or none"). Correctness rests on watermark-hold + upsert
  idempotency, not the backoff curve. Ceiling: add `time.sleep` + retry count in the
  watcher fetch if live flakiness becomes real (none observed in the build's ~10 live runs).
- **`FEDREG_MAX_DOCS=50` caps every `etl_run` pass**, so a cold-start from
  `ETL_FEDREG_SINCE=2020-01-01` needs multiple invocations to fully catch up (empirically
  3 in this build). This is iter-1's existing default, not new, but its interaction with
  incremental watermarking is worth noting. Ceiling: raise the env var or loop `run_once`
  until `detected == 0` if same-day full catch-up matters later.
- **`counts_by_source` recomputes from a full `col.get(include=["metadatas"])` on every
  `/corpus_status` call** — spec-sanctioned for the ~475-chunk demo corpus ("do not add a
  separate count index"). Ceiling: add a maintained count index if the corpus grows large.

## Next
- **Iteration 3 — Phase 3: orchestration + semantic FAQ cache** (per `.build/backlog.md`).
  Phase 2 (trigger-based ETL) shipped at the iter-2 gate. Iteration 3 opens the Phase-3
  scope deferred out of iter-2: R5 (FAQ refresh) and R6 (graph rebuild) sync triggers,
  R7 (FFIEC ingest / `loaders/ffiec.py`), the semantic FAQ cache tier (`src/rag/faq/**`,
  `scripts/seed_faq.py`), and orchestration (`src/rag/orchestration/**`, planner/skills,
  `answer_verifier`). Carry forward into the iter-3 spec:
  - **F2 (CIP completeness)** from the pre-loop ledger: Phase-3's `answer_verifier` should
    include a mandatory-element completeness check.
  - **eCFR removed-section deletion (R4b)** — the iter-2 accepted-debt item above; a
    natural fit alongside R5/R6 sync rules if Phase 3 touches corpus-mutation rules.
- **Natural later-iteration candidate (not for Iteration 3 unless scoped in):** the measured numbers favor
  `hybrid_rerank` (avg rank 1.12, term_recall 1.00 vs naive's 0.92). AC-4 was scoped to a
  naive-vs-hybrid decision only, so promoting `hybrid_rerank` to default is a *new*
  evidence-based decision for a later iteration to make deliberately — not a gap in
  iteration 1.

## Blockers
- None. Iteration 2 shipped clean at the gate (no required fixes). No irreversible action
  is required by Iteration 3 either. (Historical: iter-1's F1 docstring reword was a
  required fix, not a blocker.)

## Manual follow-ups for the user (accumulate here, do not perform)
- No git remote configured — repo was `git init`'d locally at loop kickoff so each
  iteration is diffable. Push to a remote (e.g. GitHub) is the user's call.
- **Scheduled-CI auto-PR for ETL (Phase-2/iter-2 deferral, D7).** The ETL doc §5
  GitHub-Actions pattern (cron-triggered `python -m scripts.etl_run` + auto-commit of the
  rebuilt `data/chroma` + `data/etl_state.db` via LFS) needs a configured git remote and
  CI credentials — neither exists in this local repo. Follow-up: push to a remote, then
  author the workflow file. `scripts/etl_run.py` is a single local pass; no workflow was
  written this iteration by design.
- **Container entrypoint loop honoring `ETL_SCHEDULE` (Phase-2/iter-2 deferral, D7).**
  `etl_schedule` is read into `RagConfig` but intentionally unused; wiring an actual
  cron/loop inside a container entrypoint for a self-updating deployment is deferred to the
  containerization phase (Phase 5 per the roadmap).
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
