VERDICT: SHIP

# Iteration 5 — senior-PM gate (FINAL iteration; closes the build loop)

**Date:** 2026-07-02 · **Gate:** read-only, independent · **Role:** senior PM / eng leader

This is the final planned iteration. This verdict closes the whole build. Every
load-bearing claim below was verified **at the gate against the actual current
files** — not taken on the reports' word — with extra scrutiny on the two things
this iteration exists for: the `ponytail` sweep (a standing user constraint) and
the honesty gate (no false "CI green / Docker built" claims).

---

## Bottom line

The release is real, tested, pinned, and documented to the exact limit this
environment (no Docker, no git remote) can verify — and everything it cannot
verify is plainly, consistently marked as authored-but-never-executed. The
single independent-tester fix (CI missing an index-build step) is present and
sound, and is now reflected in the CHANGELOG. The two downgraded-but-not-rejected
findings are correctly characterized and non-blocking. **Ships.**

---

## VERIFIABLE-HERE ACs — all demonstrably true at the gate

### AC-1 — Dependency pinning, fresh-venv verified — PASS
- `requirements.lock` is a **real, complete `pip freeze`** (112 lines / ~104
  packages), not a stub: real transitive pins incl. `chromadb==1.5.9`,
  `Flask==3.1.3`, `sentence-transformers==5.6.0`, `torch==2.12.1`,
  `numpy==2.5.0`, `onnxruntime-genai==0.14.1` (the documented proven-working
  version — matches progress.md's 0.5.2→0.14.1 migration record).
- `requirements.txt` direct deps all pinned with `==`, explanatory comments
  preserved, ponytail-free.
- **Spot-check that the pin set matches what the code imports:** confirmed
  `flask` (api.py), `chromadb` (builder.py), `numpy` (models.py/faq), `requests`
  (loaders) are all genuinely imported by production code — the lock reflects
  real usage, not padding.
- I did not re-run the multi-minute fresh-venv install (heavy deps); the
  substantive downstream claim — the pinned env yields a green deterministic
  suite — I re-verified directly (see AC-2). The senior-dev's and independent
  tester's fresh-venv records (145 passed) are internally consistent and the
  lock is demonstrably real.

### AC-2 — Coverage added, suite green — PASS (re-run at the gate)
- **I re-ran the deterministic suite myself:**
  `py -3.12 -m pytest tests/ -q --deselect tests/test_etl_fedreg_live.py`
  → **145 passed, 1 deselected in 38.16s.** Matches every prior record exactly
  (139 pre-existing + 7 new − 1 deselected live test).
- New `tests/test_iter5_coverage.py` (7 tests) fills genuine ROADMAP §4 gaps
  (factory mode-dispatch incl. `hybrid_rerank` + invalid-mode path; RRF fusion
  math via independent recomputation). `citation_formatter` correctly not
  duplicated. The independent tester read the RRF test side-by-side with
  `_hybrid_pool` and confirmed it's a real non-tautological recomputation
  against real production code — I accept that finding as well-evidenced.

### AC-3 — Real latency numbers — PASS
- Measured via `scripts/measure_latency.py` against the real app: FAQ hit warm
  median 0.017s (<1s target, met), cache hit warm median 0.025s, fresh gen
  14.7–30.4s / median 17.7s (10–60s band, met). Cold model-load numbers
  reported separately so they can't be mistaken for steady-state. Method is
  written down and reproducible. Finding #2 (first draft silently measured FAQ
  hits as "fresh gen") was caught and corrected honestly — good discipline.

### AC-4 — `ponytail` literal fully swept — PASS (airtight; re-verified independently)
- **I ran my own `grep -rin ponytail`** over `src/`, `scripts/`, `tests/`,
  `docs/`, `data/`, `README.md`, `CHANGELOG.md`, `requirements.txt`,
  `requirements.lock`, `Dockerfile`, `docker/`, `.github/`, `.dockerignore`,
  `LICENSE` → **zero matches** (grep exit 1).
- **Proved the grep is not silently failing:** the same pattern over the
  (correctly excluded) `.build/`/`.pipeline/` process ledgers returns **83**
  historical matches — so the tool finds real matches when present, and the
  zero above is a true negative.
- **Verified the reword is behavior-neutral:** diffed all 10 reworded files;
  every change is a comment/docstring only (`ponytail:` → "Deliberately
  simple/minimal", original design rationale preserved verbatim), no code,
  logic, signature, or SQL line moved. api.py's `_gen_iter2_path` diff is
  comment-only — the byte-identical-collapse constraint is intact. Corroborated
  by the green suite. This is a core AC and it is met cleanly.

### AC-5 — From-scratch reproducibility rebuild — PASS
- `build_index` + `seed_faq` run against scratch `CHROMA_PATH`/`FAQ_DB_PATH`/
  `ANSWER_CACHE_PATH`/`ETL_STATE_PATH` overrides (never the real `data/`),
  produced a working 402-chunk index + 29-entry FAQ from nothing; deterministic
  suite green (145) against it; eval + live `/chat_stream` round-trips succeeded.
- **Guard rail honored:** real `data/` confirmed unchanged (475 chunks / 29 FAQ)
  before and after — independently re-confirmed by the tester via direct
  `get_collection().count()` and SQL. No third `data/` corruption incident.

### AC-6 — Eval numbers re-confirmed & published — PASS
- naive hit@5=0.92 / term_recall=0.96; orchestration on-vs-off delta
  +0.04/+0.04 — matches historical Phase-3 numbers exactly (stable corpus/gold
  set). Independent tester re-ran and reproduced item-for-item, incl. the two
  `2022-21020` misses. The `eval.py` "naive baseline" label wart is **already
  parameterized** (`f"{CONFIG.rag_mode} baseline"`) — verified at the gate;
  correctly left untouched.

### AC-7 — README finalized — PASS
- Quickstart uses the exact AC-5-verified commands; Docker subsection present
  and labeled untested; Results has the real AC-3 latency + AC-6 eval tables;
  Status consolidated to a single v1.0 narrative with an explicit "Honesty
  notes" block; screenshot deferral kept honestly (D5, see below). CHANGELOG has
  a correctly-formatted Phase-5 entry.

---

## AUTHORED-BUT-UNRUNNABLE ACs — correct artifacts, honestly framed

### AC-8 — Docker artifacts — PASS (authored, reviewed, honestly untested)
- `Dockerfile` (`python:3.12-slim`, deps from `requirements.lock`, builds
  index+FAQ in-image, EXPOSE 8000, `CMD ["python","-m","src.app.asgi"]`),
  `docker/docker-compose.yml` (build context `..`, port 8000, documented
  volume-mount alternative), `.dockerignore` (excludes `data/chroma`, `*.db`,
  `.venv`, `.git`, `__pycache__`, `.build`, `.pipeline`) all present and
  internally consistent with each other and the README run story.

### AC-9 — CI workflow — PASS (valid YAML, never executed, tester fix present)
- **I parsed it at the gate:** `yaml.safe_load` succeeds; jobs `test` +
  `docker-build`; test steps in correct order: Checkout → Setup Python 3.12 →
  Install deps → **Build index and seed FAQ** → Run test suite. (The `on:`→`True`
  key is standard PyYAML boolean coercion, harmless.)
- **The independent tester's fix is genuinely present and its reasoning is
  sound:** the index-build step (lines 65–68) sits between install and test, and
  the top-of-file comment correctly explains why — ROADMAP §4's "CI does not
  rebuild the index" premise assumes a Git-LFS-committed index (the sibling
  fedacq project's pattern), which THIS repo explicitly rules out (spec §0:
  index gitignored, LFS out of scope). Without the step, a fresh runner would
  fail at the first test touching the collection. The fix closes a logical gap
  (not an execution gap — which remains correctly out of scope).

### Honesty gate (the core subject of this iteration) — PASS, all four artifacts consistent
Checked all four side by side; **none hedges toward a success claim:**
- `Dockerfile` top comment: "AUTHORED, NOT BUILT/RUN IN THIS ENVIRONMENT …
  never been `docker build`/`docker run`-executed."
- `docker/docker-compose.yml` top comment: "AUTHORED, NOT BUILT/RUN IN THIS
  ENVIRONMENT … never executed."
- `.github/workflows/ci.yml` top comment: "AUTHORED, NEVER EXECUTED … not a
  claim that CI has run or is green."
- `README` Honesty notes + Docker Status block: "never executed … Neither is
  claimed to build, run, or pass" / "have never actually been built or run."
- CHANGELOG "Docker + CI artifacts (authored, not executed)" and the CI
  index-build note both accurate. **Nowhere** in README/CHANGELOG/changes.md/
  test-results.md/progress.md is CI claimed green or the image claimed
  built/run. This is exactly the discipline the iteration demanded.

### LICENSE — PASS
MIT, correct author (Patrick W. Devens), current year (2026), with a sound
attribution note carving out gov-text and third-party models.

---

## The two downgraded-but-not-rejected findings — my independent judgment

**(a) AC-5 corpus-size discrepancy (402 scratch vs. 475 real) — NON-BLOCKING; correction carried forward.**
I read `fedreg.py::fetch_documents` myself: `order=oldest` + fixed
`publication_date[gte]=since` + hard `max_docs` cap (`return docs[:max_docs]`).
The tester is right — the primary mechanism is **structural** (`FEDREG_MAX_DOCS=50`
caps every single `build_index` pass; the real 122-doc FedReg corpus was
accumulated across multiple incremental ETL passes, which a single capped
builder can't reproduce by design — documented in progress.md ~line 128), not
"live-API non-determinism" as changes.md frames it. **But both explanations
reach the same load-bearing conclusion the AC needs: not a rebuild-logic defect,
not corruption; real `data/` verified intact.** The AC verification stands. This
is a documentation-accuracy nuance, not a code defect. Corrected in progress.md
below.

**(b) Disclaimer-in-SSE deferral — NON-BLOCKING; rationale overstated, decision correct.**
I read the four collapse tests in `test_chat_stream_orchestration.py`: they
assert the **event-name sequence** (`== ["token",...,"citations","done"]`) and
token-content and a `["citations"]` sub-key lookup — **not** full-dict equality
on the iter-2-path payloads. So the tester is right: adding a `disclaimer` key
would not literally trip these assertions, and changes.md's "would genuinely
have broken them" is **overstated**. However the **deferral itself is correct**:
the spec (§6) makes this explicitly optional and warns against forcing any test
churn in the final pass; it's a **pre-existing PRD gap, not introduced here**;
and it's honestly recorded as a follow-up in changes.md, CHANGELOG "Not done",
and progress.md. The flaw is in the precision of one sentence of rationale, not
in the decision or in any concealment. Does not block release. Correction noted
in progress.md.

---

## Scope discipline — clean
- `ORCHESTRATION` default still `false` (`config.py:49`) — D6 respected, no flip.
- No `src/rag/**` or `src/etl/**` logic touched beyond the comment reword
  (diffs confirmed comment-only). No new retrieval/orchestration/FAQ feature.
- No new Python dependency introduced. `git status`/`git diff --stat` show only
  the expected create/modify set from the spec's §3 file list.

## Ponytail-minimality note
The implementation is appropriately minimal and does not gold-plate: the
disclaimer-in-SSE was correctly left un-built rather than forced; the eval.py
label was left alone once found already-fixed; the Dockerfile uses the simple
Flask-dev CMD rather than an unverified Hypercorn wrap. Minimal work that meets
the bar → SHIP, not penalized.

---

## Definition of done (spec §9) — all 12 satisfied
1. AC-1 fresh-venv green — met. 2. AC-2 suite green (145 det. / 146 full), real
tests — met (re-run at gate). 3. AC-3 real latency w/ method — met. 4. AC-4
grep=0 over shipping files — met (re-verified, airtight). 5. AC-5 from-scratch
rebuild, data safe — met. 6. AC-6 eval re-run & published — met. 7. AC-7 README
+ CHANGELOG — met. 8. AC-8 Docker artifacts authored/consistent/untested — met.
9. AC-9 CI valid YAML, never-executed, index-build fix present — met. 10. LICENSE
(MIT) — met. 11. progress.md debt triage + follow-ups + screenshot outcome —
met (final update below). 12. No deliverable claims CI green / image built —
**confirmed across all layers.**

**VERDICT: SHIP.** The build loop is complete.
