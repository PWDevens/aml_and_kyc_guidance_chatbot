# Iteration 1 — Implementation summary

Spec: `.build/iter-1/spec.md` ("Finish Phase 1: multi-mode retrieval + corpus
breadth"). All 7 acceptance criteria met. Details, numbers, and decisions below.

---

## Environment note (not a spec item, recorded for the tester)

No Python environment on this machine had the project's dependencies installed
at session start (conda `base` is empty, `.pipeline/HANDOFF.md`'s documented
3.12.10 env no longer has packages). Installed `requirements.txt` + `pytest`
into the `py -3.12` interpreter (`C:\Users\pwdev\AppData\Local\Python\pythoncore-3.12-64`).
All commands below were run with `py -3.12 -m ...` from the project root.

**Found, not fixed (out of scope):** the freshly-installed `onnxruntime-genai`
resolved to **0.14.1**, not the 0.5.2 HANDOFF.md documents. Its `GeneratorParams`
no longer has a settable `.input_ids` attribute, so `src/rag/llm/models.py`'s
`stream()` raises `AttributeError` on every live generation call, and
`/chat_stream` — because there's no try/except around `models.stream()`, same
as before this iteration — either 500s mid-stream or (when `GENERATE=false`) is
masked by the extractive fallback. `models.py` is not in this iteration's file
list, so it was **not touched**. Flagged in `.build/progress.md` and spawned as
a follow-up task (`task_e0289248`). All verification below that needed a
"generated answer" used a monkeypatched `models.stream` to isolate the cache
logic from this pre-existing/environment-drift bug; retrieval-only paths
(build, eval, smoke test) are unaffected and were run for real, unmocked.

---

## Files created

- **`src/rag/indexing/loaders/fedreg.py`** — FinCEN Federal Register loader.
  Mirrors `ecfr.py`'s shape: `requests` + `UA` header + timeout, pure parser
  (`_record_from_doc`) separated from the paginating network fetch
  (`load_documents`). Maps FedReg `type` → `source` (`Rule`→`fedreg_rule`,
  `Proposed Rule`→`fedreg_proposed`, `Notice`→`fincen_advisory`, else
  `fedreg`). Abstract-only text (no `full_text_xml_url` fetch — see
  Simplifications). Confirmed live against the real API before coding (Q3):
  `results[]` with `document_number`, `type`, `title`, `abstract`,
  `publication_date`, `cfr_references` (list of objects), `html_url`,
  `full_text_xml_url` — exactly as documented, no surprises.
- **`src/rag/cache.py`** — SQLite exact-match answer cache. `_normalize`
  (lower/strip/collapse-whitespace), `get`/`put` keyed on the normalized
  question, `citations` stored as JSON. Table created on first use.
- **`tests/test_cache.py`** — cache round-trip + normalization check, against
  a tempdir-backed `RagConfig` (never touches the real `data/cache.db`).
- **`tests/test_fedreg_loader.py`** — `_record_from_doc` against small inline
  JSON fixtures (type→source mapping, schema, empty-abstract skip). No
  network call.
- **`tests/test_ecfr_chunking.py`** — `_split_section` (short section
  untouched; long section splits on paragraph boundaries; no paragraph is
  ever cut mid-clause).

## Files modified

- **`src/rag/config.py`** — added `answer_cache`, `cache_path`,
  `fedreg_agency`, `fedreg_since`, `fedreg_max_docs`, `chunk_char_budget`
  (all per the spec's exact names/defaults). `rag_mode` default **unchanged**
  (`"naive"`).
- **`src/rag/indexing/loaders/ecfr.py`** — added `_split_section(text,
  budget)` (greedy paragraph packing, never splits inside a paragraph) and
  wired it into `load_part`/`load_parts` via a new `chunk_char_budget`
  parameter (default 1500, matching `RagConfig`). Sections under budget are
  unchanged (single chunk, same id as before); sections over budget become
  multiple records (`ecfr-{title}-{cite}-0`, `-1`, …) sharing the same
  `citation`/metadata so citations still resolve to the whole section.
- **`src/rag/indexing/builder.py`** — extended `_META` with
  `fedreg_doc_number`, `publication_date`.
- **`src/rag/retrieval/factory.py`** — **bugfix required by chunking**:
  `_hybrid`'s RRF fusion and `_corpus()` were keyed on `citation`, which
  silently collapses multiple chunks of one section into a single candidate
  once a section is split (a real correctness bug chunking would have
  introduced into hybrid mode). Re-keyed on the unique chroma chunk `id`
  instead (`_corpus()` now also returns `ids`; `dres["ids"][0]` used in place
  of citations for the dense ranking list). Also added `_hybrid_pool` (shared
  RRF-fusion helper, pool not yet truncated to top_k) and a new
  **`hybrid_rerank`** mode — see AC-5 below. `_MODES` now has 3 entries;
  `retrieve()`'s dispatch/signature unchanged.
- **`scripts/build_index.py`** — loads eCFR (chunked, via
  `CONFIG.chunk_char_budget`) and FedReg records, merges them, prints
  per-source counts (`Counter`), then builds. `build()`'s signature untouched.
- **`src/app/api.py`** — `/chat_stream` now checks the cache first
  (`CONFIG.answer_cache` gated); on a hit, streams the stored answer as one
  `token` event + the stored `citations` + `done`, skipping retrieval and
  generation. On a miss, runs the existing retrieve→generate path, accumulates
  the streamed chunks, and — **only on the generated path**
  (`CONFIG.generate and models.available()`) — writes to the cache after
  the full answer is produced. The extractive fallback and the "no matching
  text" message are never cached (spec requirement — they aren't
  verified/authoritative). SSE event names/shape (`token`, `citations`,
  `done`) unchanged; UI needs no changes.
- **`data/eval/gold.jsonl`** — expanded 5 → 25 items (see AC-1 below).

## Files not modified (per spec's explicit guidance)

- `src/rag/indexing/loaders/__init__.py` — left as an empty namespace;
  `build_index.py` imports `fedreg` the same way it already imported `ecfr`.
- `requirements.txt` — no new runtime deps (sqlite3 stdlib,
  `sentence-transformers` already provides `CrossEncoder` for the reranker).
  `pytest` was installed to run the suite but not added to `requirements.txt`
  — it was already an *implicit* dependency of the pre-existing
  `tests/test_smoke.py` docstring's documented run command
  (`python -m pytest tests/ -q`) from Phase 0, predating this iteration; every
  test file also runs standalone via `if __name__ == "__main__":` without
  pytest. Left alone rather than scope-creeping a Phase-0 gap.
- `src/rag/llm/models.py` — see environment note above; out of this
  iteration's file list.

---

## AC-1 — Gold set expanded to 25 items (validated against primary text)

`data/eval/gold.jsonl` grew 5 → **25** items. Every `expect_citation` was
checked against the actual retrieved primary-source text (eCFR section body
pulled from the live-built index) or the live FedReg abstract before being
committed — not invented from memory (the Phase-0 lesson: 1020.410 vs
1010.410). Coverage:

- **21 eCFR items** across 15 distinct sections (1010.100/230/311/312/313/314/
  330/340/350/410/415, 1020.210/220/315/320/410) — clause-number lookups
  (e.g. "How many days... 15 days" for 1010.330(b)(1)), dollar thresholds
  ($10,000 CTR/structuring, $3,000 monetary-instrument/funds-transfer
  recordkeeping, $5,000 SAR floor, $250 proposed CVC threshold, 25% beneficial
  ownership), and a "what must be filed" (Form 8300) item.
- **4 FedReg/non-eCFR items** — two on the 2022 Beneficial Ownership
  Information Reporting final rule (`2022-21020`, CTA implementation), one on
  the Banco Delta Asia special-measure repeal (`2020-17143`), one on the
  proposed CVC/cross-border funds-transfer threshold reduction (`2020-23756`).

`python -m scripts.eval` runs clean over the new set (verified in all three
modes below).

## AC-2 — Corpus breadth

`python -m scripts.build_index` (rerun fresh from scratch as a final check)
indexes eCFR 1010/1020 **plus** FinCEN FedReg documents:

```
353 eCFR chunks loaded.
50 FedReg documents loaded.
per-source counts: {'ecfr': 353, 'fincen_advisory': 28, 'fedreg_rule': 8, 'fedreg_proposed': 14}
Done. 403 chunks/documents in collection 'aml_kyc' at .../data/chroma
```

`GET /corpus_status` (via Flask test client): `{'indexed': 403, 'as_of':
'2026-06-30', 'rag_mode': 'naive'}` — up from 105 in the prior iteration, and
3 non-`ecfr` source values present (`fincen_advisory`, `fedreg_rule`,
`fedreg_proposed`). Q2's default (`FEDREG_SINCE=2020-01-01`,
`FEDREG_MAX_DOCS=50`, oldest-first) was used as-is; the live agency feed has
131 matching documents total (confirmed via direct API probe), so the 50
pulled are a subset, not the full feed — noted per the spec's "if the live
pull returns far more... note the actual count, do not pad."

## AC-3 — Section-aware chunking

`_split_section` in `ecfr.py`: sections ≤1500 chars stay one chunk (unchanged
id/behavior); longer sections split on paragraph (`\n`-joined) boundaries,
greedily packed to the budget, never mid-paragraph. 353 eCFR chunks came out
of what was 105 sections pre-chunking — confirms splitting is active. Each
split chunk keeps the parent section's `citation`/`heading`/`url`/etc., with a
suffixed id (`ecfr-31-1010.100-0`, `-1`, …). Verified via
`tests/test_ecfr_chunking.py` (3 cases: short section untouched, long section
splits into >1 chunk with every original paragraph surviving intact and
in order, and a synthetic 3-paragraph/400-char-each case where I assert the
rejoined paragraphs equal the originals exactly — i.e. no paragraph was cut).

**Bugfix this AC required:** `_hybrid`'s RRF fusion in `factory.py` was keyed
on `citation`; once one citation maps to N chunks, the old code's
`by_cite = {citation: (doc, meta)}` dict silently kept only the *last* chunk
per section and dropped the rest from consideration. Re-keyed fusion and the
corpus cache on the chroma chunk `id` (unique per chunk) instead — each chunk
is now correctly treated as an independent retrievable candidate. This is a
direct, in-scope consequence of implementing AC-3 correctly against the
existing hybrid-mode contract (not a speculative refactor).

## AC-4 — naive vs hybrid re-measured; default decided by the numbers

Ran `python -m scripts.eval` for real under `RAG_MODE=naive` and
`RAG_MODE=hybrid` against the 25-item gold set (same freshly-built 403-chunk
index for both):

| Mode   | hit@5 | term_recall | avg rank (of hits) | worst rank |
|--------|-------|-------------|---------------------|------------|
| naive  | 1.00  | 0.92        | 1.44                | 5          |
| hybrid | 1.00  | 0.92        | 1.28                | 3          |

hit@5 and term_recall **tie** exactly. Hybrid's lower average/worst rank looks
like a win at a glance, but breaking it down: hybrid **promotes** 3 items
(fixes two borderline rank-5 FedReg hits down to rank-3, and one rank-4 eCFR
hit to rank-1) while **demoting** 3 different items from rank-1 to rank-2. I
inspected all 3 demotions directly (`retrieve(cfg, question)` with
`rag_mode="hybrid")` and every one reproduces the *exact same ranking-
regression class* the Phase-0 AML/KYC SME already documented in
`.pipeline/STATUS.md` (F1): BM25's lexical overlap pulls a near-synonym or
adjacent section above the controlling one, e.g.:
- "Who must file a report of a transaction in currency over $10,000?" → hybrid
  ranks **1010.330** (trade-or-business Form 8300 reporting) above the
  controlling **1010.311** (FI CTR filing obligation).
- "What records must be made for extensions of credit over $10,000?" → hybrid
  ranks **1010.420** ("Records to be made... by persons having custody...")
  above the controlling **1010.410**.
- "What minimum elements must a bank's AML program include?" → hybrid ranks
  **1020.220** (CIP) above the controlling **1020.210** (AML program itself).

This is not noise — it is the same, reproducible regression pattern on a
larger and harder set, which is exactly what the spec asked iteration 1 to
determine. Per the spec's explicit instruction ("If naive still wins or ties,
naive stays default — do not adopt hybrid without a measured win"):

**Decision: `RagConfig.rag_mode` default stays `"naive"`.** (No code change —
the default was already `"naive"`; this iteration's job was to confirm that
was still the right call with better evidence, and it is.) `RAG_MODE=hybrid`
remains available and unchanged in behavior.

## AC-5 — Reranker added because it fixes the measured regression

Per AC-5's exact gate, I tested (before writing any shipped reranker code)
whether `cross-encoder/ms-marco-MiniLM-L-6-v2` fixes hybrid's 3 regressions,
using a throwaway probe script (not committed) that reranked hybrid's RRF
candidate pool for all 25 gold questions:

| Mode                | hit@5 | avg rank (of hits) |
|----------------------|-------|---------------------|
| hybrid                | 1.00  | 1.28                |
| hybrid + rerank (probe) | 1.00 | 1.12               |

All 3 previously-demoted items returned to rank 1, and the reranker also beat
hybrid's own remaining weak spots (the two FedReg items moved from rank-3 to
rank-1/rank-2). This is a demonstrable, measured fix — AC-5's condition is
met, so the reranker code was added, in the smallest form the spec allows: a
new `_hybrid_rerank` mode inside the existing `src/rag/retrieval/factory.py`
(no new file, no speculative `reranker.py` module). It reuses the same
`_hybrid_pool` RRF candidates, scores `(question, doc_text)` pairs with a
`CrossEncoder` (lazily loaded, `lru_cache`'d singleton), and truncates to
`retrieval_top_k` after resorting by cross-encoder score.

Re-ran the **real** eval (not the probe) through the actual `retrieve()` path
with `RAG_MODE=hybrid_rerank`:

```
hit@5=1.00  term_recall=1.00
```

term_recall improved to a clean 1.00 (up from 0.92 for both naive and hybrid)
because the correct chunk is now more consistently pulled into the top-5
context. All three regressed items are back at rank 1; the worst rank in the
whole set is 2 (down from hybrid's 3 and naive's 5).

**Decision:** `hybrid_rerank` is added as a new, available mode
(`RAG_MODE=hybrid_rerank`) but is **not** made the default `rag_mode` this
iteration. AC-4 is explicitly scoped to a naive-vs-hybrid decision; AC-5 is a
narrower, separate gate on whether the reranker code should exist at all
(it should — the evidence says so). Promoting `hybrid_rerank` itself to
default is a natural next-iteration candidate given these numbers, but that
is a new decision outside what AC-4 asked for this iteration, so I left
`rag_mode` untouched rather than smuggling in an unrequested default change.

## AC-6 — Exact-match answer cache

`src/rag/cache.py` + `/chat_stream` wiring (see "Files modified" above).
Verified end-to-end through the real Flask test client and the real
`chat_stream` handler (generation mocked via `unittest.mock.patch` on
`models.stream`/`models.available` only, to isolate this from the unrelated
onnxruntime-genai environment bug — retrieval, caching, and SSE formatting
were all exercised for real):

1. First call, cache miss: retrieves, "generates" (mocked), streams tokens,
   accumulates the full answer, writes one cache row keyed on the normalized
   question.
2. Second call, same question **differently cased and padded with
   whitespace**: cache hit, generation mocked to raise if called (it wasn't),
   confirms retrieval + generation were both skipped — only the stored
   `token`/`citations`/`done` events were streamed, with the exact cached
   answer text and citations.
3. Separately verified (real generation stack, `GENERATE=false` extractive
   path) that the extractive fallback does **not** write to the cache, per
   spec.

`data/cache.db` (gitignored, `.gitignore`'s `data/*.db`) is created on first
use; no eviction/TTL — small local demo, noted as an intentional omission per
the spec.

## AC-7 — Citations still resolve correctly

`tests/test_smoke.py` (unmodified, pre-existing) passes against the rebuilt
403-chunk index. FedReg citation objects were inspected directly in the cache
round-trip test output — e.g. `{"citation": "2020-10310", "source":
"fincen_advisory", "url": "https://www.federalregister.gov/documents/...",
"as_of": "2020-05-14"}` — correct `url`, `source`, and `as_of` all resolve.
No regression in the existing CTR (1010.311) retrieval, which is exactly what
`test_smoke.py` checks.

---

## Full test suite

`python -m pytest tests/ -q` → **8 passed** (test_cache.py ×1,
test_ecfr_chunking.py ×3, test_fedreg_loader.py ×3, test_smoke.py ×1), run
fresh against a from-scratch `python -m scripts.build_index` rebuild.

---

## Deliberate simplifications (upgrade-path ceilings)

- **FedReg loader is abstract-only.** `full_text_xml_url` is captured in the
  record schema's URL field usage note but never fetched/parsed. Ceiling:
  if abstract text proves too thin for retrieval quality in a later eval
  round, add an XML fetch+flatten step mirroring `ecfr._text()`'s
  `itertext()` approach — same pattern, more HTTP calls per doc.
- **No cache eviction/TTL.** `cache.py` grows unboundedly. Ceiling: add a
  `created_at` column + a `DELETE ... WHERE created_at < ?` sweep, or an
  `LRU`-by-row-count cap, whenever the local demo DB size becomes a real
  concern (not yet, per spec).
- **CFR-reference filtering of FedReg docs is not implemented** — every
  FinCEN FedReg doc since 2020-01-01 is indexed regardless of
  `cfr_references` relevance. Explicitly out of scope (Phase-2 ETL rules
  R1–R3 per the spec); `cfr_references`' object-list shape (not a plain
  string list, per Q3) is preserved untouched in the raw API response but
  not used.
- **`hybrid_rerank`'s reranker model is not warmed/cached at startup** — it
  lazy-loads via `lru_cache` on first call, same pattern as `models._load()`.
  First `hybrid_rerank` request in a process pays the model-load cost.
- **`onnxruntime-genai` version drift left unfixed** — see the Environment
  note at the top. Not in this iteration's file list; flagged for the tester
  and spawned as a follow-up task.
