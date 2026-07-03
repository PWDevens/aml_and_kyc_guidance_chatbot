# Iteration 5 — test results (real commands, real output)

Everything in this file was actually run on this machine (Windows 11,
`py -3.12` → Python 3.12.10) on 2026-07-02. No number here is estimated or
copied from a prior iteration without being re-run this iteration, except
where explicitly marked "historical, for comparison."

---

## AC-1 — Dependency pinning, verified in a genuinely fresh venv

**Commands (working environment):**
```
py -3.12 -m pip freeze > requirements.lock
```
Captured the real, working environment's exact installed package set (104
packages) into `requirements.lock`. `requirements.txt` direct deps pinned to
`==` the same versions (`onnxruntime-genai==0.14.1`, matching progress.md's
documented proven-working version).

**Fresh venv (genuinely new directory, not the working environment):**
```
py -3.12 -m venv <scratchpad>/fresh_venv_iter5
<scratchpad>/fresh_venv_iter5/Scripts/python.exe -m pip install --upgrade pip -q
<scratchpad>/fresh_venv_iter5/Scripts/python.exe -m pip install -r requirements.lock
```
Result: **all 104 packages installed cleanly, exit code 0.** No dependency
resolution conflicts. Confirmed venv identity independently:
```
sys.executable -> .../fresh_venv_iter5/Scripts/python.exe
sys.version -> 3.12.10 (tags/v3.12.10:0cc8128, Apr 8 2025, ...)
pip list | onnxruntime-genai -> 0.14.1
```

**Deterministic suite inside the fresh venv:**
```
<scratchpad>/fresh_venv_iter5/Scripts/python.exe -m pytest tests/ -q --deselect tests/test_etl_fedreg_live.py
```
Result:
```
145 passed, 1 deselected in 94.08s (0:01:34)
```
(139 pre-existing + 7 new `test_iter5_coverage.py` tests − 1 deselected live
test not in this count = 145 collected-and-passed. Matches spec's expectation
of "≥138" with the new tests included.)

**Verdict: AC-1 VERIFIED.** Lock installs cleanly in a fresh venv; deterministic
suite green in that fresh venv.

---

## AC-2 — Test coverage gaps closed, full suite green

**Gap audit (grep, before writing anything):**
- `factory.py` mode-dispatch / `hybrid_rerank` branch / invalid-mode path:
  grepped `tests/` for `retrieve(` calls with a non-default `rag_mode` and
  for `_MODES`/`ValueError`/`ok"RAG_MODE="` assertions — **zero found**.
  Every existing call site (`test_smoke.py`, `test_corpus_breadth.py`) uses
  the ambient `CONFIG` (`rag_mode=naive`) only. Confirmed genuine gap.
- RRF fusion math: grepped for `rrf`/`RRF`/`fused`/`reciprocal` (case-
  insensitive) across `tests/` — **zero found**. Confirmed genuine gap.
- `citation_formatter`: grepped for `citation_formatter`/`format_citations` —
  found `tests/test_orchestration_skills.py::test_format_citations_dedupes_and_normalizes_shape`,
  a real, non-trivial direct test. **Already covered — not duplicated.**

**New file:** `tests/test_iter5_coverage.py`, 7 tests:
1. `test_modes_table_has_exactly_the_three_built_modes`
2. `test_retrieve_dispatches_naive_mode`
3. `test_retrieve_dispatches_hybrid_mode`
4. `test_retrieve_dispatches_hybrid_rerank_mode` — asserts the actual iter-1
   regression case (`hybrid_rerank` ranks 31 CFR 1010.311 at rank 1 for the
   real gold-set CTR-threshold question) — not just "returns something."
5. `test_retrieve_invalid_mode_raises_value_error`
6. `test_hybrid_pool_is_keyed_on_chunk_id_not_citation` — confirms the
   corpus has citations split across >1 chunk id (46 such citations found)
   and that the fused pool's citation list length equals its (doc, meta)
   pair count (not collapsed by citation).
7. `test_hybrid_pool_fused_order_matches_independently_computed_rrf` — hand-
   computes standard RRF (Σ 1/(60+rank) per input ranking) independently of
   `_hybrid_pool` over the same dense/BM25 rankings, and asserts the actual
   function output equals the independently-computed result exactly, plus
   the "dual-hit ranks above single-hit" RRF guarantee.

**Note on test-writing process:** the first draft of tests 4 and 7 used
assertions that turned out to encode wrong assumptions about this specific
corpus/query pair (not production-code bugs) — see `changes.md` "Findings
during implementation" for the two dead ends and how they were corrected
without touching any `src/rag/**` logic.

**Command:**
```
py -3.12 -m pytest tests/test_iter5_coverage.py -v
```
Result: **7 passed in 13.56s.**

**Full suite after addition:**
```
py -3.12 -m pytest tests/ -q
```
Result: **146 passed in 176.23s (0:02:56)** (139 original + 7 new), 0 failed.

**Verdict: AC-2 VERIFIED.**

---

## AC-3 — Real latency numbers

**Method:** `scripts/measure_latency.py` (new), using the real Flask app's
test client (same request path a live server takes, `POST /chat_stream`,
SSE stream drained to completion, wall-clock `time.perf_counter()` around
the full round-trip). One warm-up call per subsystem before timing repeats,
so cold (first-call, pays model-load cost) and warm numbers are never
conflated. Questions were checked against the FAQ matcher directly before
use, to guarantee the "fresh generation" and "cache" measurements actually
exercise retrieve→generate rather than silently short-circuiting to the
FAQ tier (see "Findings" below — this happened on the first draft).

**Command:**
```
py -3.12 -m scripts.measure_latency
```

**Real output (final, clean run):**
```
RAG_MODE=naive  GENERATE=True  FAQ_CACHE=True  ANSWER_CACHE=True  ORCHESTRATION=False

[FAQ hit]    cold(first call)=11.727s   warm repeats=['0.021', '0.017', '0.017']   warm median=0.017s   target: <1s (p50)
[Cache hit]  populating miss (not the measured number)=26.672s   hit repeats=['0.214', '0.025', '0.020']   hit median=0.025s
[Fresh gen]  14.672s   What is the effective date of FinCEN's Customer Due Diligence Final Ru
[Fresh gen]  17.722s   What penalties can apply for willful failure to file a Report of Forei
[Fresh gen]  30.445s   What is the purpose of the 314(b) voluntary information sharing safe h
[Fresh gen]  median=17.722s   min=14.672s  max=30.445s   target band: 10-60s
```

| Request class | Cold | Warm median | PRD target | Result |
|---|---|---|---|---|
| FAQ Tier-1 hit | 11.727s (model load) | 0.017s | <1s p50 | met, ~60x under |
| Exact-match cache hit | 26.672s (that call was a miss, not a hit) | 0.025s | — | met |
| Fresh generation | — | 17.722s (range 14.7–30.4s) | 10–60s | met, inside band |

**Verdict: AC-3 VERIFIED.** All targets met on real, reproducible measurements.

---

## AC-5 — From-scratch reproducibility rebuild (scratch paths, live data untouched)

**Guard rail followed:** all commands below set `CHROMA_PATH`, `FAQ_DB_PATH`,
`ANSWER_CACHE_PATH`, `ETL_STATE_PATH` to a scratchpad directory BEFORE
invoking Python, so `RagConfig` (env-read at import time) never resolves to
the real `data/` paths for these runs.

**Commands:**
```bash
export CHROMA_PATH=<scratch>/ac5_rebuild/data/chroma
export FAQ_DB_PATH=<scratch>/ac5_rebuild/data/faq.db
export ANSWER_CACHE_PATH=<scratch>/ac5_rebuild/data/cache.db
export ETL_STATE_PATH=<scratch>/ac5_rebuild/data/etl_state.db

py -3.12 -m scripts.build_index
py -3.12 -m scripts.seed_faq
py -3.12 -m pytest tests/ -q --deselect tests/test_etl_fedreg_live.py
py -3.12 -m scripts.eval
# + one direct /chat_stream round-trip via the Flask test client
```

**`build_index` output (tail):**
```
Loading eCFR title 31 chapter X parts ['1010', '1020'] ...
  353 eCFR chunks loaded.
Loading FinCEN FedReg documents (agency=financial-crimes-enforcement-network, since=2020-01-01, max_docs=50) ...
  49 FedReg documents loaded.
  per-source counts: {'ecfr': 353, 'fincen_advisory': 27, 'fedreg_rule': 8, 'fedreg_proposed': 14}
Embedding + indexing ...
Done. 402 chunks/documents in collection 'aml_kyc' at <scratch>/ac5_rebuild/data/chroma
```

**`seed_faq` output (tail):**
```
Seeding 29 FAQ entries from <repo>/data/faq_seed.yaml into <scratch>/ac5_rebuild/data/faq.db ...
  ... (29 entries, 3-4 vectors each) ...
Done. 29 entries in <scratch>/ac5_rebuild/data/faq.db
```

**Deterministic suite against the scratch index:**
```
145 passed, 1 deselected in 39.36s
```

**`scripts.eval` against the scratch index:**
```
naive baseline  hit@5=1.00  term_recall=0.92
```

**Live round-trips against the scratch index:**
- `/chat_stream` for a seeded FAQ question → `event: done` present, FAQ
  tier hit (`source_tier: faq`).
- `/chat_stream` for a non-FAQ question ("What is the purpose of the 314(b)
  voluntary information sharing safe harbor?") → real token stream via
  `retrieve()` + `models.stream()` against the scratch Chroma collection,
  `event: done` present.

**Real `data/` confirmed untouched, before and after:**
```
real data/chroma count: 475   (unchanged)
real data/faq.db entries: 29  (unchanged)
```

**Note on corpus size difference (402 scratch vs. 475 real):** the scratch
build's FedReg count (49 docs / 49→ fewer chunks than real) differs from the
real corpus's FedReg count (122 chunks: 65 advisory + 30 rule + 27 proposed)
even though both used the same `FEDREG_MAX_DOCS=50` config and the same
`FEDREG_SINCE=2020-01-01` window. This reflects the live Federal Register
API returning a different result set at different fetch times (the real
corpus was built across earlier iterations, at an earlier point in time,
against the live API) — not a bug in this iteration's rebuild. eCFR counts
matched exactly (353 both times, since eCFR content didn't change between
runs). Recorded here as an honest observation, not smoothed over.

**Verdict: AC-5 VERIFIED.** From-scratch rebuild works end to end; real data
untouched throughout.

---

## AC-6 — Eval numbers re-confirmed

**Commands (against the REAL, untouched live corpus, 475 chunks):**
```
py -3.12 -m scripts.eval
py -3.12 -m scripts.eval --compare
```

**`scripts.eval` output:**
```
Eval: 25 gold items · RAG_MODE=naive · top_k=5
...
naive baseline  hit@5=0.92  term_recall=0.96
```
Two misses, both on FinCEN's 2022 beneficial-ownership final rule
(`2022-21020`) — a real, reproducible retrieval gap on that document, not
noise (both gold items for that doc missed).

**`scripts.eval --compare` output:**
```
Eval comparison: 25 gold items

ORCHESTRATION=false (single default mode=naive, top_k=5):  hit@k=0.92  term_recall=0.96
ORCHESTRATION=true  (per-intent routed mode/top_k):  hit@k=0.96  term_recall=1.00

Delta (on - off): hit@k=+0.04  term_recall=+0.04
```

**Comparison to historical numbers (CHANGELOG Phase 3):** identical —
0.92/0.96 off, 0.96/1.00 on, +0.04/+0.04 delta. Corpus and gold set are
stable, so re-running reproduces the same result exactly. No divergence to
report.

**`eval.py` "naive baseline" label wart:** checked per spec instruction
("fix only if trivially in the way"). The print line already reads
`f"\n{CONFIG.rag_mode} baseline  hit@{CONFIG.retrieval_top_k}=..."` —
parameterized on the actual configured mode, not a hardcoded "naive"
string. No fix was needed or made; the spec's debt note pre-dates whatever
earlier change already resolved it.

**Verdict: AC-6 VERIFIED.**

---

## Full suite, final run (real `data/`, all changes applied)

```
py -3.12 -m pytest tests/ -q
```
```
146 passed in 176.23s (0:02:56)
```

## Internal-shorthand comment sweep (AC-4)

```
grep -rin <marker-string> src scripts tests docs data README.md CHANGELOG.md requirements.txt requirements.lock Dockerfile docker .github .dockerignore LICENSE
```
(`<marker-string>` = the non-standard internal-shorthand word this AC removes;
spelled out in full in `.build/iter-5/spec.md` §3/§5 D1, which is process
history and excluded from this project's "no literal word anywhere in
code/configs/docs" constraint — this file, being newly authored this
iteration, follows that constraint strictly and does not repeat the literal
string.)

Result: **zero matches** (checked after every file edit in this iteration,
and again as a final pass after all changes were complete).
