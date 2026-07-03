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
- **Iteration 5 — Phase 5: hardening & release** (per `.build/backlog.md` §"Iteration 5 —
  Phase 5: hardening & release", ROADMAP Phase 5 + Definition of done §6). Iterations 1–4
  have all shipped at their gates. Iteration 5 scope: test suite coverage across
  loaders/parsers + retrieval factory dispatch + RRF + ETL rules + each orchestration skill
  + FAQ matcher; `requirements.lock` (or pinned `requirements.txt`) for reproducibility;
  Dockerfile + one-command-run docs; README updated with eval results + demo walkthrough;
  clean-machine reproducibility check (documented, re-run if feasible). **Out of scope for
  iter-5:** any actual `git push`/deploy/publish/CI-provider account setup (document as
  manual follow-ups, do not perform); GitHub Actions workflow *files* may be authored but
  never triggered/pushed/connected to a real account.
  - **Live decision now due at iter-5:** whether to flip the `ORCHESTRATION` default to
    `true` — iter-4 explicitly did NOT take this up (D6, out of UI scope). It remains a
    latency-inclusive end-to-end `/chat_stream` measurement decision (see the iter-3
    open-decision note below), unresolved and carried forward.
  - **Screenshot capture (iter-4 debt):** the three README screenshots (landing, answer+
    citations desktop/mobile, verifier-decline) still need manual capture with working
    screenshot tooling — steps are already in the README's "Screenshots" section.
  - **eCFR removed-section deletion (R4b)** — still open (deferred D15); not required by
    Phase 4, carry forward. Candidate for iter-5 test-coverage or a bounded follow-up.
  - **F2 (CIP completeness)** shipped in iter-3's `answer_verifier` — closed, not carried.
- **Natural later-iteration candidate (not for Iteration 3 unless scoped in):** the measured numbers favor
  `hybrid_rerank` (avg rank 1.12, term_recall 1.00 vs naive's 0.92). AC-4 was scoped to a
  naive-vs-hybrid decision only, so promoting `hybrid_rerank` to default is a *new*
  evidence-based decision for a later iteration to make deliberately — not a gap in
  iteration 1.

## Iteration 3 — implemented (senior-dev pass, pre-gate; 2026-07-02)
Phase 3: `src/rag/faq/**` (semantic FAQ Tier-1: `embed.py`, `store.py`,
`matcher.py`), `src/rag/orchestration/**` (`intents.py`, `router.py`,
`verify.py`, `planner.py`), `data/faq_seed.yaml` (29 curated entries) +
`scripts/seed_faq.py`, R5 staleness flagging in `src/etl/rules.py`/`pipeline.py`,
`/chat_stream` Tier-1 + orchestrated-path wiring in `src/app/api.py`. Full
details, AC-9 real numbers, and every divergence-from-docs decision in
`.build/iter-3/changes.md`. Suite: 100 passed (47 carried + 53 new).

Carried-forward deferrals for Iteration 4's awareness (per D5/D14/D15,
already resolved-not-open in the iter-3 spec, not new debt):
- **`change_resolver` skill — deferred (D5).** Needs a queryable version-
  history/valid_from-valid_to ledger iter-2 did not build (iter-2's
  provenance ledger records ingest *actions*, not a before/after timeline).
  The `change` intent is classified/routed (to `hybrid_rerank`) but no
  bespoke temporal timeline is assembled. Iteration 4's "what changed
  timeline view" is explicitly conditional on this shipping.
- **R5 `reverify_inline` policy — not built (D14).** Only `FAQ_STALE_POLICY=
  suppress` is implemented; any other value is accepted but treated as
  suppress. Upgrade path: re-verify-inline requires running the full
  retrieve+verify loop from ETL, which couples ETL to generation — a
  deliberate scope boundary, not an oversight.
- **R4b (eCFR removed-section chunk deletion) — deferred (D15).** Still open
  from iter-2's accepted debt; not required by any iter-3 AC. Unchanged.
- **`ORCHESTRATION` ships `false` by default (D6).** AC-9's real on-vs-off
  numbers (retrieval-relevance only) show a small, unambiguous win
  (hit@k +0.04, term_recall +0.04) with no regression — see changes.md for
  the full table and the reasoning for NOT flipping the default this
  iteration despite the positive delta (the eval is retrieval-only; it does
  not measure the orchestrated path's added per-request latency/verification
  cost). This is a live decision Iteration 4 should revisit with a fuller
  (latency-inclusive) measurement before flipping.

## Iteration 3 — senior-PM gate: NEEDS WORK (2026-07-02; `.build/iter-3/verdict.md`)
Phase 3 (orchestration + semantic FAQ cache). **The code ships clean; one required
non-code fix blocks final SHIP.** Every load-bearing architectural claim was verified
independently at the gate (not on the reports' word) and holds — see verdict.md #1–#9.
Suite re-run at the gate: `py -3.12 -m pytest tests/ -q` → **123 passed, 0 failed** (171s).

**Required fix (RF-1) — data-only, no code change:** the live `data/faq.db` has **19 of
29 entries `stale=1`** (queried directly at the gate, reproducible). Under the shipped
default `FAQ_STALE_POLICY=suppress` this suppresses the Tier-1 FAQ fast-path for ~65% of
the seeded corpus, so **AC-6 is not demonstrably true against the live db** (it passes in
tempdir tests only). `test-results.md`'s appended "RESOLVED by the orchestrator" note
claims the seed was re-run and "all 29 entries now `stale=0`" — **false against the
current db** (db mtime 20:14:18 precedes the report's 20:14:46; a real 29-row seed run
would have bumped it). The R5 *code* is correct and `store.py::upsert_entry`'s
`INSERT OR REPLACE` + the no-`stale`-key `data/faq_seed.yaml` make the seed the correct
idempotent instrument — it simply was not actually run. **Path to SHIP:** (1) run
`py -3.12 -m scripts.seed_faq` against the real `data/faq.db`; (2) confirm
`SELECT COUNT(*) FROM faq_entries WHERE stale=1` = 0 (total 29); (3) correct the false
"RESOLVED" note in `test-results.md`. On completion the re-gate is a formality (all code
checks already pass, suite green). The gate is read-only and did **not** run the seed
(running a build/seed script against live data is the write the tester was correctly
blocked from). `data/etl_state.db`'s 0-R5-rows-vs-19-stale history is correctly left as-is
(no fabricated retroactive provenance) — only `faq.db` needs the reset.

## Iteration 3 — senior-PM RE-GATE: SHIP (2026-07-02; `.build/iter-3/verdict.md` overwritten)
The prior NEEDS WORK verdict (RF-1) is resolved and **durably** verified; iteration 3 ships.
The prior gate's RF-1 finding turned out to have a deeper root cause than the "reseed the db"
remediation it prescribed — and the orchestrator found and fixed the real one.

**Real root cause (verified against the code at re-gate):** `tests/test_etl_fedreg_live.py`
(an iter-2 live-API test) isolated `chroma_path`/`etl_state_path` into a tempdir but never
isolated `faq_db_path`. Harmless in iter-2 (no faq.db existed), it became a live corruption
bug the moment iter-3's `pipeline._run_ecfr` (pipeline.py:127) started calling
`_flag_faq_stale()` **unconditionally** after every R4 upsert. The test's cold-start tempdir
has no `ecfr` watermark, so `_run_ecfr` reprocesses years of real eCFR changes against the
live API, each calling `faq_store.flag_stale(cfg, ...)` against `cfg.faq_db_path` — which
defaulted to the **real** `data/faq.db`. Every real run of that live test re-flagged ~19
entries stale. That is why the orchestrator's earlier one-time `seed_faq` "fix" didn't stick
and the prior gate found 19/29 stale again. `test_etl_pipeline_r1_schedule.py`'s `_tmp_cfg`
had the same gap (no real corruption today — its synthetic doc number never matches a real
FAQ `topic_keys` — fixed anyway for correctness).

**Fix (exactly as claimed, no scope creep):** `+faq_db_path=str(Path(d) / "faq.db")` added to
both tests' tempdir config (`git diff` = **+1 line each**, nothing else), plus a real
`seed_faq` reseed of `data/faq.db`. `test-results.md`'s false "RESOLVED" note replaced with an
honest CORRECTION describing the real root cause + durable fix.

**Verified independently at the re-gate — the check the prior false note skipped:**
- Both test files read directly: `faq_db_path` genuinely isolated (fedreg_live.py:36,
  r1_schedule.py:47 in `_tmp_cfg`). Confirmed `faq_db_path` is a real `RagConfig` field
  (config.py:51) and `store.flag_stale` writes via `_conn(cfg)` → the override truly redirects
  writes; not an ignored kwarg.
- Live `data/faq.db` queried by SQL **before** the gate's own suite run: 29 total, **0 stale**.
- Gate ran the full suite itself: `py -3.12 -m pytest tests/ -q` → **123 passed** (158.26s,
  exit 0; `.build/iter-3/regate-pytest.txt`). The live test PASSED (not skipped) in 152.93s —
  the previously-corrupting cold-start path genuinely executed.
- **Critical durability check:** live `data/faq.db` queried by SQL **immediately after** the
  gate's own suite run, and again after a second standalone live-test run → **0 stale both
  times** (still 29/29 `stale=0`). This is exactly what was true only momentarily last time and
  is now durable under a real run the gate triggered. RF-1 closed; **AC-6 now demonstrably true
  against the live seeded corpus**, not just tempdir tests.
- All nine prior code checks (D9 byte-identical collapse, D8 router, verify.py stopword fix,
  R5 mechanism + `if n:` scope, seed-count honesty, ponytail cleanliness, security/deps/scope)
  unchanged by a 2-line test edit + reseed; re-affirmed by the green suite. `requirements.txt`
  untouched. No surprise edits in `git status`/`git diff --stat`. **Iteration 3 ships.**

## Accepted tech-debt from Iteration 3 (bounded, with upgrade paths — carry forward)
Carried forward from `.build/iter-3/changes.md`; all judged sound scope calls at the gate.
- **No LLM-escalation path for gray-band verifier claims (D12).** Verifier is
  lexical-overlap-only; gray-band (weak-but-nonzero overlap) claims are labeled
  `grounded_with_caveat`, not escalated (the documented over-budget fallback). `Budget`
  plumbing exists and is tested. Ceiling: wire `Budget.spend()` + a Phi-4 entailment
  prompt into `verify.py`'s gray-band branch if lexical-only precision/recall proves
  inadequate on real generated answers.
- **No LLM fallback for `intent_classifier`/`query_framer` (D13).** Fully absent (not
  stubbed); heuristic path is complete and tested. Ceiling: add a `Budget.has_budget()`-
  gated Phi-4 few-shot fallback for genuinely ambiguous input if the
  default-to-`definitional` heuristic proves too coarse on real traffic.
- **`router.py`'s `top_n` is advisory-only.** `RagConfig` has no `top_n` field, so
  `route()`'s `top_n` is returned per the interface contract but not consumed by
  `factory.py`'s pool-size logic (which derives its own from `retrieval_top_k`). Not a
  correctness bug. Ceiling: thread `top_n` into `_hybrid`/`_hybrid_rerank` as an explicit
  pool-size override if per-intent tuning becomes valuable.
- **R5 provenance row written only when `flag_stale` flags ≥1 entry (`if n:`).** An upsert
  matching no FAQ entry writes no R5 row (avoids flooding the ledger with no-op rows).
  Judged consistent with the ETL doc's "one row per ingest *action*" — an unfired trigger
  is not an action. Ceiling: change the `if n:` guard in `pipeline._flag_faq_stale` to
  always record if a complete "checked, no match" audit trail is later required.
- **FAQ seed = 29 entries** (spec target ~30–50; floor ≥12). All real 31 CFR citations,
  no padding — honest per the backlog's explicit allowance. Ceiling: add more curated
  entries (and more paraphrase variants per entry to close measured recall-boundary
  misses, e.g. the 0.73-scoring wordier CTR paraphrase the tester recorded) in a later
  curation pass.

## Iteration 3 — live decision left open for Iteration 4+
- **Whether to flip the `ORCHESTRATION` default to `true` (D6).** AC-9's on-vs-off eval
  shows a small, unambiguous **retrieval-only** win (hit@k +0.04, term_recall +0.04, no
  regression). D6's flip bar also requires "no latency regression that breaks the demo,"
  which this retrieval-only eval cannot measure (it never exercises generation, buffered
  verification, or the FAQ tier). **Iteration 4 should revisit with a latency-inclusive,
  end-to-end `/chat_stream` measurement before flipping.** Until then the safe default
  stays `false`; the `true` code path is fully built and tested.

## Iteration 3 — deferred items (carry forward, unchanged)
- **`change_resolver` skill — deferred (D5).** `change` intent is classified/routed (to
  `hybrid_rerank`) but no bespoke temporal timeline is assembled. Needs a queryable
  version-history / valid_from–valid_to ledger iter-2 did not build. Iteration 4's "what
  changed timeline view" is explicitly conditional on this shipping.
- **R5 `reverify_inline` policy — not built (D14).** Only `FAQ_STALE_POLICY=suppress` is
  implemented; any other value is accepted but treated as suppress. Upgrade path:
  reverify-inline requires running the full retrieve+verify loop from ETL, coupling ETL to
  generation — a deliberate scope boundary, not an oversight.
- **`graph` retrieval mode / LightRAG, R6 (graph rebuild), R7 (FFIEC ingest) — not built.**
  Out-of-scope per the iter-3 spec; router falls back to `hybrid_rerank` for
  cross-reference. Confirmed absent at the gate.
- **R4b (eCFR removed-section chunk deletion) — deferred (D15).** Still open from iter-2's
  accepted debt; not required by any iter-3 AC. Unchanged.

## Iteration 4 — senior-PM gate: SHIP (2026-07-02; `.build/iter-4/verdict.md`)
Phase 4 (Cognitus UI/UX restyle — frontend-only + one additive backend FAQ field). All
AC-1..AC-12 demonstrably true. Three actors touched the static files in sequence
(senior-dev build, orchestrator static-route fix, UI/UX reviewer ARIA fix); the **final**
combined state was verified coherent at the gate, not just each patch in isolation. Every
load-bearing claim checked against the actual final source, not on the reports' word:
- **Static-route security (the trust boundary):** read `api.py:42-54` — all three routes
  (`/cognitus.css`, `/cognitus.js`, `/app.js`) are zero-argument functions serving
  **hardcoded filenames** via `send_from_directory(STATIC, "<literal>")`. No variable path
  param, no `<path:>` converter — arbitrary-path traversal is impossible *by construction*,
  not merely because a test passed. `static_folder=None` means no implicit static handler
  either. Traversal tests are correct defense-in-depth on top. No secrets. Sound.
- **D9 byte-identical collapse:** read all three branches — only the FAQ fast-path
  (`api.py:198`) carries `"source_tier": "faq"`; `_gen_iter2_path` (:95) and
  `_gen_orchestrated_path` (:127/:150/:179) emit two-key dicts, no `source_tier`. Four new
  tests assert key *absence* (not `None`) on all four non-FAQ branches. Preserved.
- **ARIA fix:** `#answer` has no `aria-live`; the new visually-hidden `#answer-status`
  (`role=status aria-live=polite`) updates **exactly once** per answer — at `done`
  (`app.js:303-305`, guarded so it doesn't clobber a decline message) or on decline
  (`app.js:171`), never per token. Correctly implemented.
- **Scope:** both out-of-literal-file-list edits are legitimate spec/reality-mismatch
  corrections (same class as iter-2's "removed section" fix), not scope creep: the
  static-route fix resolves that `static_folder=None` would 404 the spec's own required
  files; the ARIA/`.visually-hidden`/`aria-describedby` fixes address the spec's
  non-negotiable a11y baseline (the missing `.visually-hidden` class was a real bug — the
  label rendered visible/unstyled). `git diff --stat` confirms no "NOT to touch" path
  (`src/rag/**`, `src/etl/**`, `requirements.txt`, `.github/workflows`, Dockerfile) changed;
  no new Python dependency; `.claude/launch.json` is a harmless dev-tooling file.
- **Manual visual-AC verification accepted:** for a no-build-step/no-visual-regression
  iteration, the evidence clears "demonstrably true — specific, reproducible": contrast
  **independently recomputed** by the reviewer (Jefferson Blue 13.56:1, Bronze 5.10:1,
  Bronze-on-alt 4.80:1, ink-muted 5.98:1, Cyan-on-white 1.90:1 → cyan correctly never text,
  grepped to 3 non-text call sites), real SSE round-trips through the actual UI, computed
  `grid-template-columns` + `scrollWidth===innerWidth` at 375/1280px, synthetic-event render
  hooks (`CognitusRender.*`) exactly as the spec's Testing-hooks section sanctions.
- **Suite re-run at the gate:** `py -3.12 -m pytest tests/ -q` → **139 passed in 154.73s**,
  0 failed (matches test-results.md: 123 pre-existing + 16 new). New tests have real teeth
  (byte-for-byte disk-vs-route, traversal rejection ×3 routes, `source_tier` absence ×4
  branches, `assert "<style>" not in html` re-inlining regression guard). No new `ponytail:`
  text in any new/edited static file; no `box-shadow`/gradient in the CSS. **Iteration 4
  ships.**

## Accepted tech-debt from Iteration 4 (bounded, with upgrade paths — carry forward)
- **Three README screenshots not captured as image files** (landing/hero+corpus strip;
  answer+citations desktop & mobile; verifier-decline). Reproducible preview-tool screenshot
  timeout across two independent server instances — environment/tooling limitation, not a
  page defect (page loads/runs correctly, confirmed via DOM/computed-style inspection + a
  live end-to-end `/chat_stream` exchange). Honestly disclosed at every layer
  (changes.md, test-results.md, docs.md, README "Screenshots" section, CHANGELOG DoD); **no
  fabricated/placeholder images added**; alternative specific evidence substitutes credibly.
  Judged **acceptable, non-blocking** — the DoD's intent (the visual states are true) is met
  by reproducible specific evidence. Ceiling: capture the three shots manually
  (`python -m src.app.asgi`; use the `CognitusRender.verification()` hook for the decline
  shot) at the next opportunity with working screenshot tooling; steps already in the README.
- **`#health-dot` `title` not reliably AT-exposed** (frontend-review.md deferral #1). Element
  is `aria-hidden="true"`, explicitly optional/supplementary per spec, no unique info.
  Ceiling: promote to a real labeled element only if a future iteration makes system health a
  user-facing non-decorative status.
- **`.eyebrow` class serves both real `<h2>` section labels and decorative `<span>`s**
  (frontend-review.md deferral #2). Semantics correct today. Ceiling: split into `.eyebrow`
  vs `.eyebrow-heading` if non-heading eyebrow uses proliferate; not worth it at 2 instances.
- **Visual ACs (AC-3/4/5-render/6-caret/7-render/8-render/9-render/11/12) are manual-only** —
  no automated visual-regression coverage. Acceptable for this dependency-light, no-build-step
  iteration; the backend contracts underlying them (SSE shapes, `/corpus_status`, static-file
  serving) ARE now automated. Ceiling: add a headless-browser/visual-regression harness only
  if/when the project takes on a build step.
- **Non-blocking note (no fix required):** CHANGELOG's DoD block says "AC-1..AC-10, AC-12
  verified" then lists several of those same ACs under "manual verification only" — cosmetic
  phrasing wrinkle; underlying evidence is honest (nothing overclaimed as automated). Not
  worth a re-gate.

## Iteration 5 — Phase 5: Hardening & release (implemented, 2026-07-02)

Final planned iteration. `.build/iter-5/changes.md` has the full AC-by-AC account
(what actually ran, real numbers, verified vs. authored-but-untested). Summary:

- **AC-1 (pinning):** `requirements.lock` = real `pip freeze`; `requirements.txt`
  pinned to `==`. Verified in a genuinely fresh venv (new directory under the
  scratchpad): lock installed cleanly, deterministic suite → 145 passed.
- **AC-2 (coverage):** confirmed via grep that factory mode-dispatch and RRF
  fusion had zero direct tests (only ever exercised implicitly through the
  default `naive` mode); `citation_formatter` was already covered, not
  duplicated. Added `tests/test_iter5_coverage.py` (7 tests, real production
  code, no tautologies). Full suite: 146 passed, 0 failed.
- **AC-3 (latency):** real numbers via `scripts/measure_latency.py` against the
  live app — FAQ hit warm median 0.017s, cache hit warm median 0.025s, fresh
  generation 14.7-30.4s (median 17.7s). All within/well-inside PRD targets.
- **AC-4 (internal-shorthand comment reword):** all 13 known occurrences of
  the non-standard internal-shorthand marker reworded to plain rationale
  comments, zero behavior change (full suite re-run green immediately after,
  before any other change). A repo-wide scan of all shipping paths (incl.
  the new Docker/CI files) confirms zero remaining occurrences.
- **AC-5 (from-scratch rebuild):** `build_index` + `seed_faq` run against
  scratch `CHROMA_PATH`/`FAQ_DB_PATH`/`ANSWER_CACHE_PATH`/`ETL_STATE_PATH`
  overrides — never the real `data/`. Produced a working 402-chunk index +
  29-entry FAQ store from nothing; deterministic suite green (145) against
  it; a real `/chat_stream` round-trip and a full `scripts.eval` run
  (hit@5=1.00) both succeeded against the scratch index. Real `data/`
  confirmed byte-for-byte unchanged (475 chunks, 29 FAQ entries) before/after.
- **AC-6 (eval):** re-run for real against the live corpus — naive baseline
  hit@5=0.92/term_recall=0.96; orchestration on-vs-off delta +0.04/+0.04 —
  both match the historical Phase-3 CHANGELOG numbers exactly. Published in
  README "Results" with a recommendation (evidence now supports flipping
  `ORCHESTRATION`, but D6 keeps the shipped default `false` this release).
- **AC-7 (README):** Quickstart, Docker note (labeled untested), Results
  (real AC-3 + AC-6 tables), consolidated v1.0 Status. CHANGELOG Phase-5
  entry added.
- **AC-8/AC-9 (Docker/CI):** `Dockerfile`, `docker/docker-compose.yml`,
  `.dockerignore`, `.github/workflows/ci.yml` authored, reviewed for
  internal consistency (index-build-in-image strategy consistent across all
  three + README), and **honestly marked untested everywhere** — this
  machine has no Docker install and this repo has no git remote/Actions
  runner, so none of these was ever built/run. Not claimed otherwise
  anywhere.
- **`LICENSE`:** MIT, added.
- **D5 (screenshots):** one genuine re-attempt made with the same
  preview/screenshot tooling as iteration 4. Page loads and renders
  correctly (all routes 200 OK, full a11y-tree snapshot confirms content);
  the screenshot capture call itself timed out twice in a row — same
  tooling-limitation failure mode as iteration 4, not a page defect. Honest
  deferral note kept, date updated, no placeholder images added.
- **Disclaimer-in-SSE:** considered, not implemented — `_gen_iter2_path` is
  under an explicit hard byte-identical-collapse constraint from iter-3
  (D9/AC-2), directly asserted by `test_chat_stream_orchestration.py`.
  Adding a `disclaimer` field there risked exactly the test churn the spec
  said to avoid forcing in the final pass. Recorded as a still-open,
  pre-existing PRD-conformance gap (PRD §5/§7), not introduced this
  iteration, not silently dropped either.
- **`eval.py` label wart:** checked; already parameterized
  (`f"{CONFIG.rag_mode} baseline"`, not hardcoded "naive"). No fix needed —
  the spec's debt note pre-dates whatever change already resolved it.

### D7 debt triage (per spec, recorded here as required)

**Closed this iteration:** dependency pinning, README finalization (incl.
Quickstart), `LICENSE`, the internal-shorthand comment reword, published eval +
latency numbers, Docker + CI artifacts *authored* (their live execution
stays deferred to a Docker/remote host — that split is intentional, not a
partial close).

**Stays deferred, reasons unchanged from prior iterations, re-confirmed
still correct at Phase 5:**
- **R4b (eCFR removed-section chunk deletion)** — feature/logic change, out
  of hardening scope.
- **R6 (graph re-sync), R7 (FFIEC ingest), `graph`/LightRAG mode** — unbuilt,
  Phase-6/stretch.
- **`change_resolver` / "what changed" timeline** — needs a version-history
  ledger not built; not a hardening item.
- **R5 `reverify_inline` policy** — couples ETL to generation; out of scope.
- **Scheduled-CI auto-PR for ETL + container ETL-loop entrypoint** — need a
  real remote + credentials + live scheduler; `.github/workflows/ci.yml`
  documents the *intent* (test + Docker-build jobs) but the auto-PR/LFS
  automation and the `ETL_SCHEDULE`-honoring container loop stay manual
  follow-ups.
- **Answer-cache eviction/TTL, FedReg full-text XML fetch, HTTP backoff,
  count index** — bounded iter-1/iter-2 debt with ceilings; none is a
  release blocker.

## Blockers
- **None open.** Iterations 1, 2, 3, 4, and 5 have all shipped/implemented at
  their gates. Iteration 3's RF-1 (the prior NEEDS WORK gate) was resolved and
  durably re-verified at its re-gate (2026-07-02): 29/29 `stale=0` confirmed by
  the gate's own SQL query immediately after its own suite run (and after a
  second live-test run); the real root cause (test `faq_db_path` isolation gap)
  was found and fixed. Iteration 5 (Phase 5: hardening & release) is the final
  planned iteration — the build loop ends after its gate.

## General observations for future iterations (cross-cutting lessons)
- **Test fixtures must isolate ALL config paths any subsystem they exercise may write to —
  not only the paths that existed when the test was written.** This is the **second** time
  in this build a test/script silently touched real data: (1) iter-2's `build_index`/
  head-pipe incident that deleted `data/chroma`; (2) iter-3's RF-1, where `test_etl_fedreg_live.py`
  isolated `chroma_path`/`etl_state_path` but not `faq_db_path`, so iter-3's new
  unconditional `_flag_faq_stale` call on the existing `_run_ecfr` path corrupted the real
  `data/faq.db` on every live-test run. Rule going forward: when an iteration adds a write
  to a NEW subsystem on an EXISTING code path, every pre-existing test that drives that path
  becomes a latent real-data corruption vector until its tempdir fixture is updated to
  isolate the new path. Prefer a single shared `_tmp_cfg`-style helper that sets every
  derived path (`chroma_path`, `etl_state_path`, `faq_db_path`, `cache_path`, …) at once, so
  adding a new path is a one-line change in one place rather than an easily-missed edit
  across N test files.

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
- **Docker live-run (Phase-5/iter-5, D7/AC-8).** `Dockerfile` +
  `docker/docker-compose.yml` are authored and internally reviewed but have
  never been `docker build`/`docker run`-executed — Docker is not installed
  on this machine. Follow-up: on a Docker-enabled host, run
  `docker compose -f docker/docker-compose.yml up --build` (or
  `docker build . && docker run -p 8000:8000 <image>`) and confirm the
  in-image `build_index`/`seed_faq` step succeeds and the app serves on
  port 8000, then update README/changes.md from "authored, untested" to
  "verified."
- **Real CI run (Phase-5/iter-5, D7/AC-9).** `.github/workflows/ci.yml` is
  valid, inert YAML — never executed (no git remote, no Actions runner).
  Follow-up: push this repo to a GitHub remote, enable Actions, and confirm
  the `test` job actually goes green (expect ~3 minutes, dominated by the
  one live-API FedReg test, which is network-tolerant and `pytest.skip`s if
  unreachable — do not expect/require a sub-minute run). The `docker-build`
  job builds only; wire real registry credentials before expecting a push.
- **`git push` / remote setup (Phase-5/iter-5).** Still no git remote
  configured this iteration either (unchanged from earlier notes) — the
  above two follow-ups both depend on this being done first. User's call
  which host (GitHub, etc.).
- **Screenshots (Phase-5/iter-5, D5).** Re-attempted with the same
  preview/screenshot tooling as iteration 4; same timeout failure mode
  (page loads/renders correctly per DOM snapshot + 200 OK on every route;
  the screenshot capture call itself hangs). Follow-up: capture the three
  README-documented shots manually in a real browser
  (`python -m src.app.asgi`, visit `http://127.0.0.1:8000/`) once outside
  this tooling's limitation, or with different screenshot tooling.
- **Disclaimer-in-SSE (Phase-5/iter-5, PRD §5/§7 gap, pre-existing, not
  introduced this iteration).** The compliance disclaimer lives only in the
  UI footer, not in every API/SSE response payload as PRD §7 requires.
  Considered this iteration; not implemented because `_gen_iter2_path` is
  under an explicit byte-identical-collapse hard constraint (iter-3 D9/AC-2)
  that a new SSE field would violate, with existing tests
  (`test_chat_stream_orchestration.py`) directly asserting that collapse.
  Follow-up: a future iteration that can budget updating the SSE-shape
  contract and its dependent tests together should add a `disclaimer` field
  to the `citations`/`done` events (or a comparable mechanism) across all
  three `chat_stream` code paths (iter-2 collapse, orchestrated, FAQ tier)
  in one coordinated change, not a piecemeal one.
- **`ORCHESTRATION` default flip (Phase-5/iter-5, D6 recommendation).** Real
  evidence now published (README "Results" / this file's Iteration 5
  section): retrieval-only delta +0.04 hit@k / +0.04 term_recall, and
  fresh-generation latency (median ~18s) leaves headroom inside the PRD's
  10-60s band even with orchestration's extra routing step. This release
  still ships `ORCHESTRATION=false` (Phase 5's mandate was hardening, not
  re-tuning routing). Follow-up: flip to `true` via the env var when ready;
  it's a one-line, fully reversible change with evidence already in hand —
  re-run `scripts/measure_latency.py` with `ORCHESTRATION=true` first to
  confirm end-to-end (not just retrieval) latency is still acceptable before
  flipping the shipped default.

## Iteration 5 — senior-PM gate: SHIP (2026-07-02; `.build/iter-5/verdict.md`) — FINAL GATE, BUILD LOOP CLOSED

Phase 5 (hardening & release, v1.0). All 9 ACs met to the limit this environment
can verify; the two AUTHORED-BUT-UNRUNNABLE artifacts (Docker, CI) are honestly
labeled never-executed everywhere. Verified independently at the gate, not on
the reports' word:
- **Suite re-run at the gate:** `py -3.12 -m pytest tests/ -q --deselect
  tests/test_etl_fedreg_live.py` → **145 passed, 1 deselected in 38.16s**
  (139 pre-existing + 7 new − 1 deselected). Matches every prior record exactly.
- **Ponytail sweep (AC-4) re-verified airtight:** own `grep -rin ponytail` over
  all shipping paths (`src`,`scripts`,`tests`,`docs`,`data`,README,CHANGELOG,
  `requirements*`,Dockerfile,`docker`,`.github`,`.dockerignore`,LICENSE) → **0
  matches**; the identical pattern over the (excluded) `.build`/`.pipeline`
  ledgers returns 83 historical matches, proving the grep works and the zero is
  a true negative. All 13 occurrences diffed → comment/docstring reword only,
  zero behavior change (corroborated by the green suite).
- **Honesty gate — all four artifacts consistent, no hedging:** Dockerfile,
  `docker/docker-compose.yml`, `.github/workflows/ci.yml` top-of-file comments +
  README Honesty-notes/Docker-status block all state "authored / never
  built/run/executed"; nowhere is CI claimed green or the image claimed built.
- **Independent tester's CI fix confirmed present & sound:** the index-build
  step (Checkout → Setup Python → Install → **Build index + seed FAQ** → Run
  tests) is in `ci.yml`; its reasoning (ROADMAP §4's "don't rebuild the index"
  assumes an LFS-committed index this repo doesn't use; index is gitignored, so
  a fresh runner must build it) is correct. YAML parses (`yaml.safe_load`).
  CHANGELOG reflects the fix accurately.
- **AC-1 lock is real:** `requirements.lock` is a genuine 112-line `pip freeze`
  (real pins: chromadb 1.5.9, Flask 3.1.3, sentence-transformers 5.6.0, torch
  2.12.1, onnxruntime-genai 0.14.1), and its pins match code imports
  (flask/chromadb/numpy/requests all imported by production modules).
- **Scope clean:** `ORCHESTRATION` default still `false` (config.py:49), no
  `src/rag/**`/`src/etl/**` logic touched beyond comment rewords, no new
  dependency, no `ORCHESTRATION` flip, no new retrieval/orchestration/FAQ
  feature. `LICENSE` (MIT, correct author/year) present.

**Two record-corrections carried forward from the independent test-results-review
(documentation-accuracy only — neither is a code defect or a blocker; the gate
concurs with the tester after re-deriving both):**
1. **AC-5 corpus-size discrepancy (402 scratch vs. 475 real) — better
   explanation:** the primary cause is **structural**, not "live-API
   non-determinism" as `changes.md`/`test-results.md` frame it. `fetch_documents`
   uses `order=oldest` + fixed `since` + a hard `max_docs` cap, so a single
   `build_index` pass structurally yields ~49–50 FedReg docs; the real 122-doc
   FedReg corpus was accumulated across **multiple incremental ETL passes**
   (empirically 3, see the `FEDREG_MAX_DOCS=50` note ~line 128 above) that a
   single capped builder cannot reproduce by design. Both framings reach the
   same load-bearing conclusion the AC needs — **not a rebuild-logic defect, not
   corruption; real `data/` verified intact (475/29) before & after** — so AC-5
   still passes. Use the structural explanation if corpus-count determinism ever
   becomes load-bearing (e.g. an exact-count test).
2. **Disclaimer-in-SSE deferral — rationale overstated, decision still correct:**
   the four collapse tests in `test_chat_stream_orchestration.py` assert
   event-name-sequence + token-content + a `["citations"]` sub-key lookup, **not**
   full-dict equality on the iter-2-path payloads — so adding a `disclaimer` key
   would **not** literally break them, contrary to `changes.md`'s "would
   genuinely have broken them." The **deferral itself remains the right call**
   (spec §6 makes it explicitly optional and warns against forcing test churn in
   the final pass; it's a pre-existing PRD §5/§7 gap, not introduced here, and is
   honestly recorded as a follow-up). If a future iteration adds it, the real
   constraint to design around is "these tests check event-name order + token
   content, not payload equality" — a `disclaimer` field is likely low-churn.

### Final accepted tech-debt (consolidated, full list — carried past v1.0)
All bounded, with ceilings; none is a release blocker.
- **R4b — eCFR removed-section chunk deletion.** Repealed sections keep stale
  chunks; nothing actively deletes them. Ceiling: an R4b rule upserting an empty
  record list for a removed citation. (Feature/logic change — out of hardening
  scope.)
- **R6 (graph re-sync), R7 (FFIEC ingest), `graph`/LightRAG retrieval mode** —
  unbuilt Phase-6/stretch features; router falls back to `hybrid_rerank`.
- **`change_resolver` skill / "what changed" timeline** — needs a queryable
  version-history (valid_from/valid_to) ledger not built; `change` intent is
  routed but no bespoke temporal timeline is assembled.
- **R5 `reverify_inline` policy** — only `FAQ_STALE_POLICY=suppress`
  implemented; reverify-inline couples ETL to generation (deliberate boundary).
- **R5 provenance row only written when `flag_stale` flags ≥1 entry (`if n:`)** —
  an unfired trigger records no row. Ceiling: drop the guard if a complete
  "checked, no match" audit trail is later required.
- **Scheduled-CI auto-PR for ETL + container ETL-loop entrypoint honoring
  `ETL_SCHEDULE`** — need a real remote + credentials + live scheduler;
  `ci.yml` documents the intent (test + Docker-build jobs) but the auto-PR/LFS
  automation and the container cron-loop stay manual follow-ups. `etl_schedule`
  is read into `RagConfig` but intentionally unused.
- **Answer-cache eviction/TTL** — `data/cache.db` grows unbounded. Ceiling:
  `created_at` column + a sweep/LRU cap when local DB size matters.
- **FedReg loader is abstract-only** — no `full_text_xml_url` fetch/parse.
  Ceiling: add an XML fetch+flatten mirroring `ecfr._text()` if abstracts prove
  too thin.
- **No HTTP backoff/retry on watcher fetches** — single `requests` call +
  `raise_for_status()`; correctness rests on watermark-hold + upsert
  idempotency. Ceiling: add retry if live flakiness appears (none seen in ~10
  live runs).
- **`counts_by_source` recomputes from a full `col.get()` per `/corpus_status`
  call** — sanctioned for the ~475-chunk demo corpus. Ceiling: a maintained
  count index if the corpus grows large.
- **`router.py`'s `top_n` is advisory-only** — no `top_n` field in `RagConfig`;
  `factory.py` derives pool size from `retrieval_top_k`. Not a correctness bug.
- **Verifier is lexical-overlap-only; no LLM escalation for gray-band claims
  (D12); no LLM fallback for `intent_classifier`/`query_framer` (D13).**
  Heuristic paths complete and tested; `Budget` plumbing exists. Ceiling: wire a
  Phi-4 entailment/few-shot fallback if lexical precision proves inadequate.
- **FAQ seed = 29 entries** (target ~30–50; floor ≥12). All real citations, no
  padding. Ceiling: add curated entries / more paraphrase variants per entry.
- **`hybrid_rerank` reranker model is lazy-loaded** (`lru_cache`), not warmed at
  startup — first request pays model-load cost. Fine for the demo.
- **`hybrid_rerank` is not the default** despite measuring best (avg rank 1.12,
  term_recall 1.00 vs naive 0.92) — promoting it is a deliberate future
  evidence-based decision, not a gap.
- **Disclaimer-in-SSE (PRD §5/§7)** — compliance disclaimer lives only in the UI
  footer, not in every SSE payload. Pre-existing gap; see correction #2 above.

### Manual follow-ups for the user (nothing here was performed by the loop — all require the user)
1. **`git push` / remote setup.** Repo is local-only (`git init`, no remote).
   Push to a host (GitHub, etc.) — this is the prerequisite for follow-ups 2 & 3.
2. **Real CI run.** After pushing + enabling Actions, confirm the `test` job
   actually goes green (expect ~3 min, dominated by the one network-tolerant
   live-API FedReg test; not sub-minute). The `docker-build` job builds only —
   wire registry credentials before expecting a push. `ci.yml` is valid, inert
   YAML today; "CI is green" is NOT a claim this build makes.
3. **Docker: install + build/run the image.** Docker is not installed here.
   On a Docker-enabled host: `docker compose -f docker/docker-compose.yml up
   --build` (or `docker build . && docker run -p 8000:8000 <image>`); confirm the
   in-image `build_index`/`seed_faq` step succeeds and the app serves on :8000,
   then flip README/changes.md from "authored, untested" to "verified."
4. **Capture the three README screenshots** (landing/hero+corpus strip; answer+
   citations desktop & mobile; verifier-decline). Preview-tool capture timed out
   twice (same tooling limitation as iter-4; page renders correctly per DOM/a11y
   snapshot + 200 OK on all routes). Capture manually (`python -m src.app.asgi`,
   visit `http://127.0.0.1:8000/`; use the `CognitusRender.verification()` hook
   for the decline shot) with working screenshot tooling. No placeholder images
   were fabricated.
5. **Decide whether to flip `ORCHESTRATION` to `true`.** Evidence is published
   (README "Results": retrieval delta +0.04 hit@k / +0.04 term_recall; fresh-gen
   median ~18s leaves headroom in the 10–60s band). This release ships `false`
   (Phase 5 = hardening, not routing re-tune). It's a one-line, fully reversible
   env-default change — re-run `scripts/measure_latency.py` with
   `ORCHESTRATION=true` first to confirm end-to-end latency before flipping.
6. **Disclaimer-in-SSE** — a future iteration that can budget the SSE-shape +
   dependent-test updates together should add a `disclaimer` field to the
   `citations`/`done` events across all three `chat_stream` paths in one
   coordinated change (see correction #2 for the actual — low — test constraint).

### Screenshot outcome (D5)
Re-attempted this iteration; same timeout failure as iter-4 (tooling limitation,
not a page defect — all routes 200 OK, full a11y-tree snapshot confirms complete
render). Honest deferral note kept in README, date updated, no fabricated images.

---

## BUILD LOOP COMPLETE (2026-07-02)

All five planned iterations (ROADMAP Phases 1–5) have shipped at their gates:
Iteration 1 (multi-mode retrieval + corpus breadth) SHIP · Iteration 2
(trigger-based ETL) SHIP · Iteration 3 (orchestration + FAQ cache) SHIP (after
one NEEDS WORK re-gate on the RF-1 faq.db isolation bug, durably resolved) ·
Iteration 4 (Cognitus UI/UX) SHIP · Iteration 5 (hardening & release, v1.0)
SHIP. **`.build/backlog.md` is now exhausted** — every iteration in it is
complete; Phase 6 was explicitly out of scope for this run. The project is a
real, tested, pinned, documented v1.0 release to the exact limit a single local
dev machine (no Docker, no git remote) can verify, with everything it cannot
verify plainly marked authored-but-unexecuted — not faked. Remaining work is the
six manual follow-ups above (all requiring the user: remote/push, real CI run,
Docker build/run, screenshots, the `ORCHESTRATION` flip decision, disclaimer-in-
SSE) plus the bounded accepted tech-debt, none of which blocks the release.
