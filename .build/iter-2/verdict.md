# Iteration 2 — senior-PM gate verdict

VERDICT: SHIP

**Iteration:** N=2 · "Phase 2: trigger-based ETL" · **Gate role:** senior PM / eng leader (read-only)
**Date:** 2026-07-02 · **Gated against:** `.build/iter-2/spec.md` (frozen, D1–D7 resolved)

---

## Summary

Iteration 2 meets the definition of done. All 7 acceptance criteria are met and
demonstrably true. The load-bearing correctness properties (D4 no-`build()`-in-ETL-path,
R8 watermark-advance-only-on-success, D3 `chapter: null` intersection) were verified by
reading the actual source, not by trusting `changes.md`. The full test suite is green,
independently re-run at this gate (47 passed, including the live network test). No scope
creep, no security regressions, no `ponytail:` additions. Ships. The build loop advances
to Iteration 3.

## AC-by-AC verdict (all PASS, independently checked)

| AC | Verdict | Evidence I checked myself |
|----|---------|---------------------------|
| AC-1 Watchers poll from stored watermark, cold-start fallback | PASS | `src/etl/watchers/fedreg.py:18-19`, `ecfr.py:18-19` read watermark then fall back to `cfg.etl_fedreg_since`/`etl_ecfr_since`. Strict-after filtering present in both. |
| AC-2 Rules R1–R4 unit-tested incl. D3 `chapter:null` | PASS | `src/etl/rules.py:19-25` `touches_watched_cfr` never reads `chapter`, normalizes `title`/`part` to str. `tests/test_etl_rules.py` (10 tests) + the D3 case. |
| AC-3 Upsert-by-citation idempotent, no stale dupes | PASS | `builder.py:60-73` delete-by-citation-then-add on `get_or_create_collection`. `tests/test_etl_upsert.py` proves count-stable, new-text-present, old-text-gone, idempotent-on-rerun, citation-scoped delete (an `_OTHER` citation is untouched). |
| AC-4 Watermark advances only on success (R8) | PASS | `pipeline.py:66-75` (fedreg) / `103-111` (ecfr): `set_watermark` runs only in the `for...else` branch, i.e. only if the batch loop completes without raising; the `except` records an `error` row and re-raises. `tests/test_etl_state.py::test_watermark_not_advanced_after_simulated_mid_batch_failure`. |
| AC-5 `etl_state.db` schema present/populated | PASS | `src/etl/state.py:24-45` DDL matches the spec's exact column names/types for both `watermarks` and `provenance`. |
| AC-6 `/corpus_status` reports `last_etl_run` + `counts_by_source` | PASS | `src/app/api.py:36-58` adds both keys, preserves `indexed`/`as_of`/`rag_mode`, guards the state read in try/except (missing db → `None`, not 500), preserves 503-on-missing-collection. `tests/test_corpus_status_endpoint.py` (4 tests, new this session) exercises the real Flask route incl. all four behaviors. |
| AC-7 Seeded-watermark live FedReg detect + idempotent re-run | PASS | `tests/test_etl_fedreg_live.py` — re-run at this gate: **1 passed in 130s** against the real API; skip-guard on `RequestException` present for both runs; uses a tempdir Chroma + tempfile db so the committed index is never touched. |

## Extra-scrutiny items (per the gate procedure)

1. **D4 — `upsert_by_citation` never calls `build()`/`delete_collection`.** VERIFIED by
   reading `builder.py:60-73`: it uses `get_or_create_collection` → `col.get(where=...)`
   → `col.delete(ids=...)` → `col.add(...)`. `build()` (lines 48-57) is the only caller
   of `delete_collection`/`create_collection` and is untouched (signature + full-rebuild
   behavior intact). `pipeline.py` and `scripts/etl_run.py` import only
   `upsert_by_citation`, never `build`. The only textual `build()` match in the ETL path
   is a docstring stating it is never called. Property holds.

2. **R8 — watermark does NOT advance on mid-batch failure.** VERIFIED by reading the
   control flow, not just the test. In both `_run_fedreg` and `_run_ecfr` the
   `newest_*` accumulator is updated per-iteration but only committed via `set_watermark`
   in the `try/else` block, which Python executes only when the `for` loop finished with
   no exception. A raise inside the loop lands in `except`, records one `error`
   provenance row, and re-raises — never reaching `set_watermark`. `run_once` catches the
   re-raise per-source so a fedreg failure cannot advance/corrupt ecfr's watermark and
   vice-versa. Matches the spec's ordering guarantee exactly.

3. **D3 — `chapter: null` handling in `rules.py`.** VERIFIED by reading
   `touches_watched_cfr` (lines 19-25): iterates refs, tests `str(ref.get("title")) ==
   "31" and str(ref.get("part")) in parts` — `chapter` is never accessed, and both
   `title` (may be int 31) and `part` (str) are normalized with `str()`. Correct.

4. **The 3 new tester test files are meaningful, not tautological.** VERIFIED by reading
   each:
   - `test_ecfr_changed_sections.py` — exercises the real `changed_sections` with an
     inline `/versions` fixture containing a `removed:true` row, a `type:"subpart"` row,
     and a duplicate identifier; asserts the removed one is excluded, non-section
     excluded, dedup-to-latest, and empty-result on removed-only. Real teeth on the
     production `v.get("removed")` filter.
   - `test_corpus_status_endpoint.py` — drives the real Flask test client; asserts both
     new keys populated, three old keys preserved, `null`-on-missing-db yields 200, and
     503-on-missing-collection preserved. First endpoint-level coverage of AC-6.
   - `test_etl_pipeline_r1_schedule.py` — runs the real `pipeline._run_fedreg` (only the
     watcher `poll` is mocked); asserts R1 writes both an `upsert` and a `schedule`
     provenance row (with `as_of=effective_on`, `chunks_changed=0`), R2 writes only
     `upsert`, and the watermark still advances. Exercises the real classify → shape →
     upsert → record → set_watermark path.

## Incident & deviation judgments (per the gate's stated context)

- **`data/chroma` deletion incident (`changes.md` §Incident).** Judged as a process
  incident handled correctly: caught immediately (a follow-up `get_collection` raised),
  reported rather than hidden, the auto-mode safety classifier also blocked a
  self-directed rebuild, and the orchestrator restored the index by re-running the normal
  `scripts.build_index`. `data/chroma` + `data/etl_state.db` are gitignored (derived, not
  committed) — no git-diff footprint, no repo-level consequence, no data permanently lost.
  Not a code defect. The stated lesson (no piping mutating-script output through
  truncating commands) is a sound corrective. No penalty.

- **eCFR "removed section" fix (`ecfr.py:121`).** Judged a correct, in-scope production
  bug fix, not scope creep. Read the code directly: `if v.get("type") != "section" or
  v.get("removed"): continue` — a `removed:true` `/versions` entry has no fetchable text
  (`/full/...&section=...` 404s), which crashed the eCFR batch before the fix (R8
  correctly held the watermark). This is a real defect found via a live run; the spec's
  D1 literally described each entry as "one changed section" without anticipating the
  `removed` flag, so filtering it is the minimal correct fix. `test_ecfr_changed_sections.py`
  now covers it directly. I agree with the senior-dev's read.

## Definition-of-done checklist

- **Every AC demonstrably true** — yes (table above; suite re-run at this gate).
- **Diff matches the spec** — yes. Files created/modified match the spec's create/modify
  lists exactly. No "Do NOT create" path exists (verified: no `src/rag/faq`,
  `orchestration`, `graph_lightrag.py`, `ffiec.py`, `fincen.py`, `seed_faq.py`, no
  `.github/workflows`, no separate proposed/advisory collections).
- **Tests green honestly** — yes. Independently re-ran: 46 deterministic tests pass in
  34s; the 1 live test passes in 130s (47 total). No masked defects, no relaxed criteria,
  no self-heal fixes were needed by the tester (0/2 budget used).
- **Security / validation at trust boundaries** — acceptable for scope. No secrets
  committed; all outbound HTTP uses a UA header + timeout + `raise_for_status()`; SQL is
  parameterized throughout `state.py` (no string interpolation into queries); no new
  dependency added (stdlib `sqlite3`, existing `requests`/`chromadb`). Chroma metadata
  stays scalar-only; `cfr_references` (a list) is used only for classification, never
  stored.
- **Reliability / operability** — R8 atomicity is the load-bearing property and it holds
  (watermark-hold + upsert idempotency). No irreversible action was performed by the
  build (the one destructive event was the accidental local index delete, fully
  reversible and reversed). Provenance ledger provides the observability the plan calls
  for.
- **Documented to repo standard** — yes. README status line and CHANGELOG Phase-2 entry
  updated in the repo's existing style with real measured numbers; D1–D7 + simplifications
  recorded in `changes.md`. (Minor note, non-blocking: `changes.md` cites "36 passed"
  while `test-results.md` cites "47 passed" — both are honest; the tester added 11 gap
  tests after the senior-dev wrote 36. The CHANGELOG reconciles this as "36 (or 47 with
  tester's additions)". No action required.)
- **Shortcuts recorded with ceilings** — yes, in `changes.md` §Deliberate simplifications
  (R1 schedule = provenance marker not timer; no HTTP backoff; `fedreg_max_docs=50` cold-
  start needs multiple passes; eCFR removed-section chunks not actively deleted → R4b
  follow-up; `counts_by_source` recomputed per request). All bounded, all with upgrade
  paths. Carried forward below.

## Non-blocking observations (not gate failures)

- `changes.md` vs `test-results.md` test-count wording differs (36 vs 47) — explained
  above; both honest.
- **Accepted debt carried forward (not new):** a repealed eCFR section's old chunks
  remain in the corpus until an R4b "removed → delete citation" rule is added. The spec's
  R4 interface assumed a fetchable change, so this is correctly out-of-scope here and
  logged with a clean upgrade path. Flagging for Phase 3+ prioritization, not for this
  gate.
