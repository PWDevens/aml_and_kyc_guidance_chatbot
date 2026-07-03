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
- **Iteration 4 — Phase 4: Cognitus UI/UX** (per `.build/backlog.md` §"Iteration 4 —
  Phase 4: Cognitus UI/UX", driven by `docs/UIUX_COGNITUS.md`). Iteration 3 shipped clean
  at its re-gate (2026-07-02, below). Iteration 4 opens the deferred UI scope:
  `cognitus.css`/`cognitus.js` tokens applied to `src/app/static/`, hero + chat/ask
  surfaces per the Cognitus design spec. Live decision to revisit at the top of iter-4:
  whether to flip the `ORCHESTRATION` default to `true` (see the iter-3 open-decision note
  below) with a latency-inclusive end-to-end measurement.
  - **F2 (CIP completeness)** shipped in iter-3's `answer_verifier` (mandatory-element
    completeness check, AC-5) — closed, no longer carried.
  - **eCFR removed-section deletion (R4b)** — still open (deferred D15); not required by
    Phase 4, carry forward.
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

## Blockers
- **None open.** Iteration 3's RF-1 (the prior NEEDS WORK gate) is resolved and durably
  re-verified at the re-gate (2026-07-02): 29/29 `stale=0` confirmed by the gate's own SQL
  query immediately after the gate's own suite run (and after a second live-test run). The
  real root cause (test `faq_db_path` isolation gap, not just a stale db) was found and
  fixed. Iterations 1, 2, and 3 have all shipped at their gates. Iteration 4 (Phase 4:
  Cognitus UI/UX) is clear to open.

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
