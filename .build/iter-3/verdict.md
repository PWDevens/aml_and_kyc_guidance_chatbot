VERDICT: SHIP

# Iteration 3 — senior-PM gate verdict (RE-GATE after RF-1 fix)

**Iteration:** N=3 · Phase 3 (orchestration + semantic FAQ cache)
**Gate date:** 2026-07-02 · **Role:** senior PM / eng leader (read-only)
**Re-gate of:** the prior NEEDS WORK verdict (RF-1). This file overwrites it.
**Suite at gate:** `py -3.12 -m pytest tests/ -q` → **123 passed, 0 failed, 0 skipped**
(158.26s), run independently by the gate. The live FedReg/eCFR test
(`test_etl_fedreg_live.py`) PASSED (not skipped) in 152.93s against the real API.

---

## Bottom line

**SHIP.** The single required fix from the prior gate (RF-1) is now genuinely and
**durably** fixed — verified the exact way the prior false "resolved" note was not:
by triggering the real corrupting code path myself and confirming the live DB
survived. All code checks from the prior gate still hold, and the fix is exactly
the minimal, correct change (two 1-line test edits + a data reseed), with an honest
root-cause correction in `test-results.md`. Nothing else regressed.

Critically, this iteration's failure mode last time was that "it's fixed" was true
only for a moment: the orchestrator had run `seed_faq` once, but a later pytest run
re-flagged 19/29 entries stale, and the "resolved" note was written before that
regression was caught. This re-gate does not repeat that mistake — it proves
durability under a real suite run the gate itself triggered.

---

## RF-1 — resolved, verified durable (the critical check)

**Prior gate finding:** the real root cause (not diagnosed at the time) was that
`tests/test_etl_fedreg_live.py` isolated `chroma_path`/`etl_state_path` into a
tempdir but never isolated `faq_db_path`. Iteration 3's `pipeline._run_ecfr`
(pipeline.py:127) added an **unconditional** `_flag_faq_stale()` call after every
eCFR (R4) upsert. The live test's cold-start tempdir has no `ecfr` watermark, so
`_run_ecfr` reprocesses years of real eCFR changes against the live API — each
calling `faq_store.flag_stale(cfg, "31 CFR ...")` against `cfg.faq_db_path`, which
defaulted to the **real** `data/faq.db`. Every real run of that live test re-flagged
the same ~19 entries stale.

**Verified independently at this re-gate (six checks, in order):**

1. **Test isolation is real, in both files.** Read both directly:
   - `tests/test_etl_fedreg_live.py:36` — `faq_db_path=str(Path(d) / "faq.db")` now
     inside the tempdir `replace(CONFIG, ...)`.
   - `tests/test_etl_pipeline_r1_schedule.py:47` — same line added to the `_tmp_cfg`
     helper (which all 3 of that file's tests use).
   The `git diff` on both files is **exactly +1 line each** — no other change.
   Confirmed `faq_db_path` is a real `RagConfig` field (config.py:51,
   `os.getenv("FAQ_DB_PATH", .../data/faq.db)`) and that `store.flag_stale` opens
   its connection via `_conn(cfg)` which reads `cfg.faq_db_path` — so the override
   genuinely redirects writes into the tempdir. This is not a silently-ignored
   kwarg; the isolation actually takes effect.

2. **Live `data/faq.db` clean BEFORE my run:** direct SQL — total=29, stale=1 → **0**,
   stale=0 → **29**.

3. **Full suite (I ran it):** `py -3.12 -m pytest tests/ -q` → **123 passed** in
   158.26s, exit 0. Output in `.build/iter-3/regate-pytest.txt`.

4. **THE CRITICAL CHECK — live `data/faq.db` clean AFTER my run:** direct SQL
   immediately after my suite run — total=29, stale=1 → **0**. Then re-ran the live
   test alone (`-v -rs`): it **PASSED** (not skipped) in 152.93s — proving the
   previously-corrupting cold-start code path genuinely executed — and a third SQL
   query after that second run confirmed stale=1 → **0** again (faq.db mtime
   20:27:59). The DB is durably `stale=0` across a suite run and a second live run
   that I triggered myself. This is exactly what was true only momentarily last time
   and is now durable.

5. **Root-cause explanation is technically sound.** Cross-checked the
   `test-results.md` CORRECTION section against the actual code: `_run_ecfr`
   (pipeline.py:106–140) calls `_flag_faq_stale(cfg, ...)` unconditionally at line 127
   after every upsert; `_flag_faq_stale` (line 30) calls `faq_store.flag_stale(cfg,
   citation)`, which writes to `cfg.faq_db_path`. The cold-start-watermark →
   reprocess-years → flag-real-entries chain is accurate. The correction also
   honestly notes `test_etl_pipeline_r1_schedule.py` had the same gap but does not
   cause real corruption today (its synthetic doc number never matches a real FAQ
   `topic_keys`), and was fixed for correctness/defense-in-depth anyway — an accurate,
   non-overstated account.

6. **Scope is exactly as claimed, no surprises.** `git diff --stat`: the only
   working-tree changes to the two test files are +1 line each. The other modified
   files (`src/etl/pipeline.py`, `src/app/api.py`, `scripts/eval.py`, `src/etl/rules.py`,
   `src/rag/config.py`, `test_chat_stream_cache.py`, docs) are the iteration-3 work
   already vetted SHIP-quality at the prior gate — pre-existing to this fix, not new
   edits introduced by it. `requirements.txt` untouched (no new deps). No out-of-scope
   files. `data/faq.db`/`data/etl_state.db` are gitignored derived data. The
   `test-results.md` honesty correction (the CORRECTION section) is present and
   matches the verified reality.

**RF-1 is closed.** Both halves of the prior gate's requirement are satisfied: the
live DB is `stale=0` for all 29 entries (so AC-6's Tier-1 fast-path is now functional
for the full seeded corpus in the delivered environment), AND the artifact
(`test-results.md`) now honestly describes the real root cause and the real, durable
fix rather than a premature false "resolved" claim. The fix is code (test isolation)
plus data reseed, so it will not silently re-break on the next pytest run — which was
the entire failure mode last time.

---

## Everything else re-checked — still holds

All nine independent code checks from the prior gate (verdict body #1–#9) remain
true; the RF-1 fix touched only two test files' tempdir config and the local seed
data, none of the load-bearing source. Spot-re-confirmed the ones a test-file/config
change could conceivably perturb:

- **D9 byte-identical collapse, D8 router constraint, verify.py stopword fix, R5
  mechanism, R5 `if n:` scope call, seed-count honesty, ponytail-marker cleanliness,
  security/deps/scope** — unchanged by a 2-line test edit + reseed; all still pass as
  documented in the prior verdict and re-affirmed by the green 123/123 suite.
- **AC-6** — now demonstrably true against the **live** seeded corpus, not just
  tempdir tests (the prior gate's sole reason it wasn't). 29/29 `stale=0`.
- **Suite** — 123/123, identical count to the prior gate; no test weakened, deleted,
  or newly skipped. The two edited tests still pass (the live one exercised for real).

---

## Why SHIP (not NEEDS WORK, not BLOCK)

The prior gate's single required fix (RF-1) is genuinely and durably resolved,
verified by the gate itself triggering the real code path that used to corrupt the
DB and confirming the DB survived — the specific check the prior false "resolved"
note skipped. The definition of done is now met: every AC (including AC-6) is met and
demonstrably true in the delivered environment, no masked defects remain, the fix is
minimal and correct, the artifact is honest, and nothing else regressed. There is no
remaining required work and nothing irreversible or unsafe. **Iteration 3 ships.**

## Test-isolation lesson (recorded for future iterations)

This is the **second** time in this build a test/script silently interacted with real
data (the first was the iteration-2 `build_index`/head-pipe `data/chroma` deletion
incident). The general rule going forward: **a tempdir/`replace(CONFIG, ...)` test
fixture must isolate ALL config paths any subsystem it exercises may write to — not
only the paths that existed when the test was first written.** When a new iteration
adds a write to a new subsystem on an existing code path (here: iter-3's
unconditional `_flag_faq_stale` on the iter-2 `_run_ecfr` path), every pre-existing
test that drives that path becomes a latent corruption vector until its fixture is
updated. Prefer a single shared `_tmp_cfg`-style helper that sets every derived path
at once, so adding a new path is a one-line change in one place.
