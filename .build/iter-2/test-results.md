# Iteration 2 — Test results

**Role:** SME in testing/debugging (tester gate) · **Date:** 2026-07-02
**Spec:** `.build/iter-2/spec.md` · **Changes:** `.build/iter-2/changes.md`

## RESULT: PASS

`py -3.12 -m pytest tests/ -q` → **47 passed**, exit code 0 (run twice for real: 168.29s
and 143.78s, both clean, no flakes). 36 pre-existing/senior-dev tests (19 iteration-1 +
17 iteration-2) + **11 new gap-coverage tests added this session**, zero failures, **zero
self-heal fixes needed** (0/2 budget used).

No `python -m scripts.build_index` or `python -m scripts.etl_run` was run against the
real `data/chroma`/`data/etl_state.db` this session. No output was piped through
`head`/`tail`/similar truncating commands — the harness's auto-mode classifier correctly
blocked one attempt (`... | tail -n 40` on a pytest run) per the safety note; all test
runs redirected to a log file and were read in full with `Read` instead.

---

## New tests added (gap coverage — not duplicating the senior-dev's 17)

### `tests/test_ecfr_changed_sections.py` (4 tests) — Gap 1
Direct unit coverage of `src/rag/indexing/loaders/ecfr.py::changed_sections`, the
function itself (not just callers), with `requests.get` mocked via an inline
`content_versions` fixture — no network:
- `test_changed_sections_excludes_removed_entries` — a `removed: true` row (modeled on
  the real 1010.655 case from changes.md's incident note) is excluded from the result.
- `test_changed_sections_excludes_non_section_types` — a `type: "subpart"` row is
  excluded independent of the removed filter.
- `test_changed_sections_dedupes_to_latest_issue_date_per_identifier` — existing D1
  dedup behavior, now covered directly against the loader (previously only implied by
  the pipeline-level live test).
- `test_changed_sections_only_removed_entry_yields_empty_result` — reproduces the exact
  incident scenario (the only change since watermark is a removed section) and asserts
  a clean empty result, not an error.
- Sanity-checked out-of-band that this test has teeth: called `changed_sections` with a
  removed-only fixture and confirmed the result is `[]` (i.e., the fix in
  `ecfr.py::changed_sections` is genuinely active, not something these tests would pass
  against vacuously).

### `tests/test_corpus_status_endpoint.py` (4 tests) — Gap 2
Integration-level test of `GET /corpus_status` via the real Flask test client, mirroring
`tests/test_chat_stream_cache.py`'s pattern (`patch("src.app.api.CONFIG", cfg)` +
tempdir-backed config + real `app.test_client()`), not just `state.py` unit tests:
- `test_corpus_status_reports_last_etl_run_and_counts_by_source` — builds a throwaway
  2-record Chroma collection, writes one provenance row, hits the real endpoint, asserts
  both new AC-6 keys are populated correctly AND the three pre-existing keys
  (`indexed`, `as_of`, `rag_mode`) are preserved.
- `test_corpus_status_last_etl_run_is_null_when_etl_state_db_absent` — `etl_state.db`
  path points at a subdirectory that was never created (sqlite3.connect itself fails);
  asserts 200 (not 500) with `last_etl_run: None`.
- `test_corpus_status_counts_by_source_empty_when_no_provenance_yet` — confirms
  `counts_by_source` is derived from collection metadata (populated even with zero
  provenance rows), while `last_etl_run` stays `None`.
- `test_corpus_status_still_503_on_missing_collection` — regression guard: the
  pre-existing 503-on-missing-collection behavior is unchanged by the new state read.

### `tests/test_etl_pipeline_r1_schedule.py` (3 tests) — Gap 3
Tests `pipeline._run_fedreg`'s actual behavior (not just `rules.classify_fedreg`'s
return dict), against a tempdir Chroma collection + tempfile `etl_state.db`, with only
`fedreg_watcher.poll` mocked (an inline raw R1 `Rule` doc fixture) — everything
downstream (`classify_fedreg`, `_record_from_doc`, `upsert_by_citation`, `state.record`,
`set_watermark`) is the real production code path, no network:
- `test_r1_final_rule_writes_both_upsert_and_schedule_provenance_rows` — asserts BOTH an
  `action='upsert'` row and a separate `action='schedule'` row are written for the same
  R1 document, both `rule_id='R1'`/`status='success'`; the upsert row's `as_of` is
  `publication_date`, the schedule row's `as_of` is `effective_on`; the schedule row's
  `chunks_changed` is 0 (a marker, not a corpus write); the corpus actually has the
  upserted chunk.
- `test_r2_proposed_rule_writes_upsert_only_no_schedule_row` — contrast case proving R2
  does NOT get a schedule row (only R1 schedules an eCFR re-pull).
- `test_r1_schedule_row_survives_watermark_advance` — the extra schedule row doesn't
  confuse the batch-success bookkeeping; the watermark still advances normally.

All 11 new tests pass individually (`pytest -v` on the three new files: 11/11 PASSED)
and as part of the full 47-test suite.

---

## Acceptance criteria mapping (spec's 7 ACs)

| AC | Description | Verdict |
|----|---|---|
| AC-1 | Watchers poll from stored watermark, cold-start fallback | PASS — `test_etl_state.py` (watermark round-trip), `test_etl_fedreg_live.py` (live cold/warm start). No gap found; watcher poll() logic read and matches spec. |
| AC-2 | R1-R4 rules engine, unit-tested incl. D3 chapter:null | PASS — `test_etl_rules.py` (10 tests, senior-dev) covers all four rules + D3 explicitly. No gap. |
| AC-3 | Upsert-by-citation idempotent, no stale duplicates | PASS — `test_etl_upsert.py` (2 tests, senior-dev). No gap. |
| AC-4 | Watermark advances only on success (R8) | PASS — `test_etl_state.py::test_watermark_not_advanced_after_simulated_mid_batch_failure` (senior-dev, deterministic) + live incident evidence in changes.md. No gap. |
| AC-5 | `etl_state.db` schema present/populated | PASS — `test_etl_state.py` schema exercised via `state.py`'s own functions; column names verified against spec's exact DDL by direct read of `src/etl/state.py`. No gap. |
| AC-6 | `/corpus_status` reports `last_etl_run`, `counts_by_source` | PASS — **gap found and closed this session**: `tests/test_corpus_status_endpoint.py` (new, 4 tests) is the first direct endpoint-level test; previously only `state.py`'s underlying functions were unit-tested, not the Flask route's wiring/error-handling. |
| AC-7 | Seeded-watermark live FedReg detection + idempotent re-run | PASS — `test_etl_fedreg_live.py` (senior-dev, live API, ran clean per changes.md's live-run log). Not re-run this session (network-dependent, already verified live 4x per changes.md); read and confirmed correct. |

---

## The 5 scrutiny items from changes.md — carried forward with verdict

1. **eCFR "removed" section filter** (`ecfr.py::changed_sections`, the
   `v.get("removed")` check). **Verdict: correct, and now has explicit unit coverage.**
   Previously untested directly (only exercised incidentally by the live `etl_run`
   passes). Added `tests/test_ecfr_changed_sections.py` with an inline `removed: true`
   fixture (no network) — confirmed the filter excludes removed entries, excludes
   non-`type=="section"` entries, dedupes to latest `issue_date`, and handles the
   removed-only-change case (the exact incident scenario) as an empty result, not an
   error. Independently re-verified outside pytest that the filter is genuinely active
   (not a vacuously-passing test).

2. **Multi-pass fedreg catch-up behavior** (a cold-start needs multiple `etl_run`
   invocations to fully catch up given `FEDREG_MAX_DOCS=50`). **Verdict: acceptable,
   confirmed by code inspection.** `src/etl/watchers/fedreg.py::poll` and
   `pipeline._run_fedreg` correctly advance the watermark to the newest doc processed
   *within* the current batch (not to "now"), so each subsequent run resumes forward —
   this is deliberate, correct incremental-fetch semantics, not a bug. Spec's AC-1 only
   requires "one pass" semantics per run, which this satisfies. No test gap: this
   behavior is implied by the watermark-advance logic already covered in
   `test_etl_state.py` and demonstrated live in changes.md's 3-pass table. Not
   re-demonstrated live this session (would require running `etl_run` against the real
   index, which the safety note prohibits without explicit test requirement — this
   behavior is already adequately covered by existing watermark tests + the live record
   in changes.md).

3. **R8 mid-batch failure semantics.** **Verdict: correct, well-tested, no gap.**
   `test_etl_state.py::test_watermark_not_advanced_after_simulated_mid_batch_failure`
   deterministically proves the contract at the state layer. Additionally, this
   session's new `test_etl_pipeline_r1_schedule.py` exercises the *success* path of
   `pipeline._run_fedreg` end-to-end (real classify/upsert/record/watermark-advance
   code, not simulated), which indirectly increases confidence in the same function's
   error branch (read directly in `src/etl/pipeline.py` lines 66-72: the `except`
   records one `error` row and re-raises, `else` on the `try` only advances the
   watermark if no exception occurred — matches spec exactly). Did not add a new
   mid-batch-failure test at the pipeline level (would require injecting a failure into
   `upsert_by_citation` or `fedreg._record_from_doc` mid-batch) because the existing
   state-layer test already covers the R8 contract precisely as spec'd, and duplicating
   it at the pipeline level for marginal gain was judged out of the "gap, not
   duplication" mandate — flagging this as a defensible line call for the senior-PM to
   weigh in on if stricter pipeline-level fault injection is wanted in iteration 3.

4. **`upsert_by_citation`'s Windows tempdir cleanup accommodation**
   (`ignore_cleanup_errors=True` in `test_etl_upsert.py` / `test_etl_fedreg_live.py`).
   **Verdict: confirmed safe, does not mask failures.** Read both test files line by
   line: all `assert` statements execute and are checked *inside* the
   `with tempfile.TemporaryDirectory(...)` block, before the block's `__exit__` runs
   the (possibly-failing) `rmtree` teardown. `ignore_cleanup_errors=True` only
   suppresses errors from that teardown step — if any assertion inside the block had
   failed, pytest would report the test as FAILED at that point, before teardown is
   ever reached. Confirmed this is standard `tempfile` behavior (the flag only affects
   `__exit__`'s cleanup, not exceptions raised inside the `with` body). No fix needed.

5. **The `data/chroma` incident and its recovery.** **Verdict: confirmed resolved, no
   test depends on exact pre-incident chunk count.** Grepped the full `tests/`
   directory for any hardcoded exact-chunk-count assertion tied to the pre-incident
   402/475 figures: `test_corpus_breadth.py::test_corpus_status_shows_breadth_beyond_ecfr`
   only asserts `indexed > 105` (a floor, not an exact match), which is satisfied by
   both the pre- and post-incident chunk counts. No other test references an absolute
   chunk count from the real index. This session did not touch `data/chroma` or
   `data/etl_state.db` at all (all new tests use tempdir/tempfile fixtures per the
   safety note).

---

## Ponytail compliance

Grepped all new test files and this report for `ponytail` — zero occurrences. No
`# ponytail:` comments were added. Pre-existing `ponytail:` comments in `config.py`,
`builder.py`, `ecfr.py`, `api.py` were not touched (this session made no source-code
changes at all — see next section).

## Fixes made this session

**None.** The suite was green on the first run after adding the 3 new gap-coverage test
files (11 tests). Self-heal budget: 0/2 used. No source files under `src/` or `scripts/`
were modified — only test files were added under `tests/`.

## Files added this session

- `tests/test_ecfr_changed_sections.py` (4 tests)
- `tests/test_corpus_status_endpoint.py` (4 tests)
- `tests/test_etl_pipeline_r1_schedule.py` (3 tests)

## Recommendation for senior-PM gate

All 7 ACs pass. All 5 changes.md scrutiny items have been independently verified with a
verdict (4 confirmed correct as-is with new/existing test coverage; 1 — item 3, pipeline-
level fault injection beyond the state-layer test — is a judgment call worth a second
opinion but not a blocker, since the R8 contract is already deterministically proven at
the layer the spec's AC-4 targets). No defects found; no fixes required. Suite is stable
across repeated runs (47/47, twice). Recommend PASS to advance the gate.
