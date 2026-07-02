# Iteration 1 — Frozen spec

**Iteration:** N=1 · "Finish Phase 1: multi-mode retrieval + corpus breadth"
**Target tag concept:** `v0.2-multimode` (not git-tagged — full-build never tags)
**Written:** 2026-07-02 · **Author role:** PM (this iteration only)

> **Read this file only.** It is self-contained. Do not re-plan from `docs/` — the
> relevant decisions are lifted below. Where a doc is cited it is for the
> senior-dev's optional reference, not required reading.

---

## OPEN QUESTIONS

These must be resolved before or during build. Items **Q1** and **Q2** are
answered inline with a **default decision** the senior-dev should follow unless the
orchestrator overrides; they are surfaced here for visibility, not to halt the
loop. **Q3 halts** only if the live FedReg API contract cannot be confirmed at
build time (see mitigation).

- **Q1 — One FedReg loader or two ("FedReg" + "advisory")?**
  The backlog says "FedReg (FinCEN) + advisory static loaders"; ARCHITECTURE §10
  lists loader files `fedreg.py` **and** `fincen.py`. The Federal Register API is
  the single machine-readable source for *both* FinCEN rules/notices **and** the
  Federal-Register-published advisories/notices (ETL doc §1 confirms FinCEN
  advisories surface as FedReg `Notice`-type documents).
  **Default decision (build this):** implement **one** loader,
  `src/rag/indexing/loaders/fedreg.py`, that pulls FinCEN Federal Register
  documents and tags each record's `source` by document `type`
  (`fedreg_rule` | `fedreg_proposed` | `fincen_advisory`) — see "Interfaces"
  below. Do **not** create a separate `fincen.py` this iteration; a distinct
  FinCEN.gov-advisory scraper (non-FedReg) is deferred to a later phase and is
  **out of scope** here. Rationale: YAGNI + one live API keeps the loader testable
  and mirrors the existing single-`ecfr.py` pattern.

- **Q2 — How many advisory/rule docs to ingest for "corpus breadth"?**
  The plan says "add corpus breadth beyond 31 CFR 1010/1020" without a count.
  **Default decision:** pull FinCEN FedReg documents with `publication_date >=`
  `FEDREG_SINCE` (default `2020-01-01`, env-overridable) capped at
  `FEDREG_MAX_DOCS` (default `50`). This is enough to broaden the corpus and give
  the expanded gold set non-eCFR targets without ballooning CPU embed time. If the
  live pull returns far more or far fewer than expected, note the actual count in
  `changes.md` — do not pad.

- **Q3 — FedReg API response shape — RESOLVED by orchestrator (2026-07-02).**
  Verified live: `GET .../documents.json?...` for `financial-crimes-enforcement-network`
  since `2020-01-01` returns `count`, `total_pages`, `next_page_url`, and
  `results[]` with exactly the fields below (confirmed against real response, not
  assumed). 131 matching documents exist (well above `FEDREG_MAX_DOCS=50`, so
  pagination via `next_page_url` or `page=` matters if you want the *oldest* 50 —
  confirm which end of the range you want; "oldest" order is already the default
  requested). `cfr_references` is a list of objects (`{chapter, citation_url, part,
  title}`), not plain strings — irrelevant this iteration since CFR-ref filtering is
  out of scope, but don't assume it's a string list if you touch it later.
  No live-shape blocker remains. Original question preserved below for record:
  The request contract is specified in ETL doc §1 and reproduced under "Interfaces"
  below, and it is a public, key-less JSON API. The senior-dev **must confirm the
  live response JSON shape at build time** (field names: `results[]`,
  `document_number`, `type`, `title`, `abstract`, `publication_date`,
  `cfr_references`, `html_url`, `full_text_xml_url`) before finalizing the parser —
  do **not** guess field names from memory. If the live API is unreachable or its
  shape differs materially from ETL doc §1, **stop and record the discrepancy as an
  updated open question** rather than shipping a loader against an assumed shape.
  Getting the real contract right matters more than speed (this is the plan's
  explicit instruction). The eCFR loader already proves the "live public API at
  build time" pattern; follow it (no recorded fixtures for the loader itself).

---

## Note on conventions (read first)

- **Operating mode is "full ponytail" (lazy = shortest working diff, YAGNI,
  stdlib/installed-deps first, one runnable check per change).** However, the user
  has explicitly forbidden the literal convention: **do NOT write `ponytail:`
  comments and do NOT use the word "ponytail" anywhere in code, docstrings, or
  commit messages.** Simplifications get recorded in `changes.md` / the tech-debt
  ledger instead. (The existing files contain `ponytail:` comments from Phase 0 —
  leave those as-is; just don't add new ones. Do not do a cleanup pass to remove
  them — that's churn outside this iteration's scope.)
- Match the existing house style: module docstring stating intent, `from __future__
  import annotations`, small pure functions, dict-dispatch, env-driven config via
  `RagConfig`. Mirror `src/rag/indexing/loaders/ecfr.py` exactly for the new loader.

---

## Goal

Prove or correctly reject hybrid retrieval on a harder, expanded eval set; broaden
the corpus beyond eCFR parts 1010/1020 with FinCEN Federal Register documents; tune
section-aware chunking to eCFR XML; and add the exact-match answer cache — all so
the default retrieval mode is an **evidence-based decision**, not an assumption.

---

## Acceptance criteria (testable)

1. **Gold set expanded to ~20–30 items.** `data/eval/gold.jsonl` grows from 5 to
   **20–30** items covering: clause-number lookups, dollar-threshold questions,
   and at least a few non-eCFR (FedReg/advisory) targets. Each item keeps the
   existing schema (`q`, `expect_citation`, `answer_contains`) and every
   `expect_citation` is **validated against primary source text** before it is
   committed (the Phase-0 lesson: a wrong gold label — 1020.410 vs 1010.410 —
   was the highest-value catch; do not repeat it). `python -m scripts.eval` runs
   clean over the new set.

2. **Corpus breadth.** `python -m scripts.build_index` indexes eCFR 1010/1020
   **plus** FinCEN FedReg documents (Q1/Q2 defaults). `GET /corpus_status` and the
   build log show a higher `indexed` count and at least one non-`ecfr` `source`
   value present in the collection.

3. **Section-aware chunking tuned to eCFR XML.** eCFR sections longer than a
   configurable budget are split on paragraph boundaries (eCFR XML `P`/`DIV`
   structure) into multiple citable chunks that still carry the section's
   `citation`/metadata, rather than one monolithic per-section chunk. Short
   sections remain a single chunk. No chunk splits mid-clause. (Details under
   "Interfaces".)

4. **naive vs hybrid re-measured and default decided by the numbers.**
   `scripts/eval.py` produces per-mode metrics on the expanded set for **both**
   `RAG_MODE=naive` and `RAG_MODE=hybrid`. The chosen default is set in
   `RagConfig.rag_mode` **based on the measured result** and the decision +
   numbers are written to `changes.md` (and reflected in `.build/progress.md`).
   If naive still wins or ties, naive stays default — that is an acceptable and
   expected outcome; do not adopt hybrid without a measured win.

5. **Reranker added ONLY if it fixes a measured regression.** The cross-encoder
   reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`, already cached) is added
   **only if** hybrid shows a ranking regression on the expanded set AND the
   reranker demonstrably fixes it in the numbers. If hybrid has no regression, or
   the reranker doesn't fix it, **do not add the reranker** — record the decision
   and the evidence in `changes.md`. Speculative reranking is explicitly forbidden.

6. **Exact-match answer cache.** `src/rag/cache.py` (SQLite) exists and is wired
   into `src/app/api.py`'s `/chat_stream` so an identical (normalized) question
   replays a stored answer without re-running generation. Gated by `ANSWER_CACHE`
   (default `true`). A runnable check demonstrates a cache write then an
   exact-match replay.

7. **Citations still resolve correctly.** `tests/test_smoke.py` still passes, and
   citation objects for FedReg records carry a working `url` and the correct
   `source`/`citation`. No regression in the existing CTR/CIP/credit retrievals.

---

## Files to create or modify

**Create:**
- `src/rag/indexing/loaders/fedreg.py` — FinCEN Federal Register static loader.
- `src/rag/cache.py` — SQLite exact-match answer cache.
- One test file for the new surface (extend `tests/` — e.g. `tests/test_cache.py`;
  a loader/parser test may use a **small inline JSON fixture** for the *parser*
  function only, not for the live fetch — see "Edge cases").

**Modify:**
- `src/rag/config.py` — add env knobs: `answer_cache` (bool, `ANSWER_CACHE`,
  default true), `cache_path` (`ANSWER_CACHE_PATH`, default
  `ROOT/data/cache.db`), FedReg knobs (`fedreg_agency`, `fedreg_since`,
  `fedreg_max_docs`), and chunking knobs (`chunk_char_budget`, default e.g. `1500`).
  Only add vars this iteration reads (house rule: no speculative config).
- `src/rag/indexing/loaders/__init__.py` — currently empty (1 blank line); leave as
  a namespace or add explicit re-exports only if the build script imports that way.
  `scripts/build_index.py` imports `from src.rag.indexing.loaders import ecfr` — add
  the analogous `fedreg` import there, not necessarily in `__init__`.
- `src/rag/indexing/builder.py` — extend `_META` if new metadata fields
  (`fedreg_doc_number`, `publication_date`) must be stored; add section-aware
  chunking (or add it in the loader / a small `chunking.py` helper — see below).
- `scripts/build_index.py` — load FedReg records and merge with eCFR records before
  `build(...)`. Print per-source counts.
- `scripts/eval.py` — support running/printing **both** modes in one invocation (or
  keep single-mode via `RAG_MODE` and document running it twice); print
  per-controlling-section rank so a ranking regression is visible (the Phase-0 eval
  already tracks `@rank` — preserve and lean on it).
- `src/app/api.py` — wrap the `/chat_stream` generation path with the answer cache
  (lookup before generate; store after a full non-cached generation).
- `data/eval/gold.jsonl` — expand to 20–30 validated items.
- `requirements.txt` — no new deps expected (sqlite3 is stdlib; sentence-transformers
  already pulls the cross-encoder). Only touch if the reranker path needs an import
  not already present — it does not (`sentence-transformers` provides `CrossEncoder`).
- `changes.md` and `.build/progress.md` — record the measured retrieval decision,
  the reranker decision, and any simplifications (this is where "ponytail"
  simplifications go instead of code comments).

**Do NOT create** (deferred / out of scope): `src/rag/faq/**`, `src/rag/orchestration/**`,
`src/etl/**`, `src/rag/retrieval/graph_lightrag.py`, `src/rag/retrieval/reranker.py`
as a *speculative* standalone module (only add reranker code if AC-5's condition is
met, and even then the smallest form — a function in `factory.py` is acceptable),
`loaders/ffiec.py`, `loaders/fincen.py`, `scripts/seed_faq.py`.

---

## Interfaces / signatures

### `src/rag/indexing/loaders/fedreg.py`

Mirror `ecfr.py`'s shape: pure module functions, `requests` + stdlib, returning a
`list[dict]` of records using the **same record schema** the builder consumes.

Request contract (from ETL doc §1 — **confirm live shape per Q3**):

```
GET https://www.federalregister.gov/api/v1/documents.json
    ?conditions[agencies][]={fedreg_agency}          # default financial-crimes-enforcement-network
    &conditions[publication_date][gte]={fedreg_since} # default 2020-01-01
    &order=oldest
    &per_page=100
    &fields[]=document_number&fields[]=type&fields[]=title
    &fields[]=abstract&fields[]=publication_date&fields[]=effective_on
    &fields[]=cfr_references&fields[]=html_url&fields[]=full_text_xml_url
```

Suggested functions:

- `load_documents(agency: str, since: str, max_docs: int) -> list[dict]`
  Fetch the FinCEN document list (paginate if needed up to `max_docs`), then for
  each document build one record. For document body text, use `abstract` as the
  retrievable text if present; optionally fetch `full_text_xml_url` for fuller
  text, but **abstract-only is an acceptable minimal implementation** for corpus
  breadth (full-text XML parsing is heavier and can be deferred — note it in
  `changes.md` if you stop at abstracts).
- Keep the actual JSON parsing in a separate pure function, e.g.
  `_record_from_doc(doc: dict) -> dict | None`, so it is unit-testable without a
  network call (see Edge cases).

**Record schema** each FedReg record must produce (compatible with `builder._META`):

```python
{
  "id": f"fedreg-{document_number}",
  "text": abstract_or_fulltext,              # non-empty; skip doc if empty
  "citation": document_number,                # e.g. "2024-12345" (FedReg doc number;
                                              #   this is the click-through identity)
  "heading": title,
  "source": source_by_type,                   # see mapping below
  "title": "", "chapter": "", "part": "",     # empty for FedReg (keeps _META scalars)
  "section": "",
  "url": html_url,
  "as_of": publication_date,
  # new metadata fields (add to builder._META):
  "fedreg_doc_number": document_number,
  "publication_date": publication_date,
}
```

`source_by_type` mapping (drives Q1's single-loader tagging):

| FedReg `type`   | `source` value      |
|-----------------|---------------------|
| `Rule`          | `fedreg_rule`       |
| `Proposed Rule` | `fedreg_proposed`   |
| `Notice`        | `fincen_advisory`   |
| anything else   | `fedreg`            |

> **Note:** Phase-0's `_format`/citation code keys off `citation`, `heading`, `url`,
> `source`, `as_of` — all present above — so FedReg records flow through the existing
> `(context, citations)` contract with no factory change.

### Section-aware chunking (AC-3)

Keep it minimal and local. Preferred placement: a small helper the eCFR loader (or
builder) calls — e.g. `_split_section(text: str, budget: int) -> list[str]` — that:
- returns `[text]` unchanged when `len(text) <= budget`;
- otherwise splits on paragraph boundaries (the eCFR `_text()` already joins
  paragraphs on `\n`; split there, then greedily pack paragraphs into ≤`budget`
  chunks) — never split inside a paragraph;
- each resulting chunk becomes its own record with a suffixed id
  (`ecfr-31-1010.311-0`, `-1`, …) but **identical** `citation`/metadata so citations
  still resolve to the section.

`budget` = `RagConfig.chunk_char_budget` (default ~1500 chars, safely under the
`CONTEXT_CHAR_BUDGET=8000` generation cap so several chunks fit). Do not over-engineer
a tokenizer-aware splitter; character/paragraph packing is sufficient and matches
house style. If splitting changes the eval numbers, that's expected — re-measure
(AC-4) after chunking is in place so the naive/hybrid comparison reflects the final
chunking.

### `src/rag/cache.py`

Exact-match answer cache over stdlib `sqlite3`. Suggested surface:

```python
def _normalize(question: str) -> str: ...   # lower/strip/collapse-whitespace key
def get(cfg, question: str) -> dict | None:  # -> {"answer": str, "citations": list, "as_of": str} or None
def put(cfg, question: str, answer: str, citations: list, as_of: str | None) -> None:
```

- DB path from `cfg.cache_path` (default `ROOT/data/cache.db`; already covered by
  `.gitignore`'s `data/*.db`). Create table on first use (`CREATE TABLE IF NOT
  EXISTS ...`). Store `citations` as a JSON string.
- Key on the **normalized** question string (exact match after normalization — this
  is Tier-2 exact cache, NOT the Phase-3 semantic FAQ cache; do not add embeddings
  or similarity here).
- No eviction/TTL needed this iteration (small local demo). Note the omission in
  `changes.md`.

### `/chat_stream` integration (`src/app/api.py`)

Current handler streams `retrieve -> generate -> citations -> done`. Wire the cache
so:

1. If `CONFIG.answer_cache` and `cache.get(...)` hits: stream the stored answer text
   (as one or more `token` events), then the stored `citations` event, then `done` —
   **skipping retrieval and generation entirely**.
2. On a miss: run the existing path, **accumulate** the generated answer text, and on
   successful completion call `cache.put(question, full_answer, citations, as_of)`.
   Only cache the **generated** (`models.available()`) path — do **not** cache the
   extractive fallback or the "no matching text" message (they're not
   verified/authoritative answers). Note this rule in code intent.
3. Preserve SSE event names/shape exactly (`token`, `citations`, `done`) so the UI is
   unchanged.

Keep the disclaimer behavior identical — this iteration does not add the API-payload
disclaimer (that's PRD §7 / a later UI phase); do not introduce it here.

### `src/rag/config.py` additions

Add only these fields (frozen dataclass, env-driven, same style):

```python
answer_cache: bool          # ANSWER_CACHE, default "true"
cache_path: str             # ANSWER_CACHE_PATH, default ROOT/data/cache.db
fedreg_agency: str          # FEDREG_AGENCY, default "financial-crimes-enforcement-network"
fedreg_since: str           # FEDREG_SINCE, default "2020-01-01"
fedreg_max_docs: int        # FEDREG_MAX_DOCS, default 50
chunk_char_budget: int      # CHUNK_CHAR_BUDGET, default 1500
```

---

## Edge cases

- **FedReg live API unreachable at build time.** The *build script* may fail loudly
  (same as eCFR today — build is an online operation). But **tests must not depend on
  a live network call.** Therefore: the FedReg **parser** (`_record_from_doc`) is
  unit-tested against a small inline JSON dict fixture; the live `load_documents`
  fetch is exercised only by the (online) build script, exactly as `ecfr.load_part`
  is today. Do not add a network call to `pytest` collection.
- **Empty/absent `abstract`.** If a FedReg doc has no abstract (and you didn't fetch
  full text), skip it (`return None`) rather than indexing an empty document —
  mirrors eCFR's `if not body: continue`.
- **Non-CFR-X FedReg docs.** The FinCEN agency feed may include documents that don't
  touch 31 CFR Chapter X. For Phase-1 *corpus breadth* this is acceptable — index
  them as advisory/notice context; filtering by `cfr_references` is a **Phase-2 ETL
  rules** concern (R1–R3), explicitly out of scope here. Do not implement CFR-ref
  filtering this iteration.
- **Chroma metadata must be scalar.** `builder._META` picks scalar fields only; keep
  all new metadata (`fedreg_doc_number`, `publication_date`) as strings. Empty string
  for eCFR records that lack them (eCFR loader should set them to `""` or the builder
  should default via `r.get(k, "")` — the builder already does `r.get(k, "")`, so
  eCFR records need no change if the fields are just absent).
- **Duplicate ids across sources.** eCFR ids are `ecfr-...`; FedReg ids are
  `fedreg-...`; chunked sections get `-N` suffixes — no collisions. Verify ids are
  unique before `col.add` (chroma errors on duplicate ids).
- **Cache key collisions / normalization.** Two differently-cased identical questions
  must hit the same cache row (normalize before keying). Whitespace-only or empty
  questions are already rejected by the handler before caching.
- **Reranker candidate pool.** If AC-5 triggers adding the reranker, pull a larger
  pool then re-score to `retrieval_top_k`; the cross-encoder input is
  `(question, doc_text)` pairs. Keep it CPU-fast; it's already a cached model.
- **Eval over both modes.** `_corpus()` in `factory.py` is `lru_cache`'d on
  `(chroma_path, collection)`; if you run both modes in one Python process after a
  rebuild, the BM25 cache is fine (same corpus). No action needed unless you rebuild
  mid-process.

---

## Patterns to follow

- **New loader → mirror `src/rag/indexing/loaders/ecfr.py`** precisely: module
  docstring stating the source + the "one citable unit" intent, `from __future__
  import annotations`, `requests` with a `UA` header + timeout, `raise_for_status()`,
  return `list[dict]` in the exact record schema the builder consumes. The FedReg
  loader is the eCFR loader's sibling — same public API-at-build-time approach, **no
  fixtures for the live fetch** (fixtures only for the pure parser's unit test).
- **Builder integration → `src/rag/indexing/builder.py`** already accepts any
  `list[dict]` with the `_META` keys; extend `_META` for the two new fields and merge
  eCFR + FedReg record lists in `scripts/build_index.py` before calling `build(...)`.
  Do not change the `build()` signature.
- **Retrieval contract → `src/rag/retrieval/factory.py`** — every mode returns
  `(context, citations)` via `_format`. FedReg records satisfy `_format` already; do
  not special-case sources in the factory.
- **Cache → new `src/rag/cache.py`** wraps the API handler, matching how the plan
  frames it (ARCHITECTURE §2/§3: cache short-circuits before generation). It is the
  Tier-2 exact cache from FAQ_CACHE §1 — **exact normalized match only**, stdlib
  sqlite3, no embeddings. The Phase-3 semantic FAQ tier layers on top later; keep
  this one simple so that layering is clean.
- **Config → `src/rag/config.py`** — one frozen dataclass field per env var, using
  the existing `_b()` helper for booleans and `int(os.getenv(...))` for ints.
- **Eval → `scripts/eval.py`** — keep the retrieval-only metrics (`hit@k`,
  `term_recall`) and the printed `@rank`; that rank column is exactly what exposes a
  ranking regression (Phase-0 used it to catch hybrid demoting the controlling CTR
  section). Do not add a metrics framework.
- **Runnable check per change (house rule):** each new module ships one runnable
  assertion — cache round-trip test; FedReg parser test on the inline fixture;
  smoke/eval still green.

---

## Out of scope (do NOT touch this iteration)

- **Trigger-based ETL** — `src/etl/**`, watchers, rules engine R1–R8, watermarks,
  provenance ledger, `/corpus_status` ETL fields, CFR-reference filtering of FedReg
  docs. That is **Iteration 2 / Phase 2**. This iteration ingests FedReg docs
  **statically** at build time only.
- **Orchestration & semantic FAQ cache** — `src/rag/orchestration/**`,
  `src/rag/faq/**`, planner/skills, `answer_verifier`, `scripts/seed_faq.py`,
  `data/faq_seed.yaml`, `FAQ_SIM_THRESHOLD`. Iteration 3 / Phase 3. (This iteration's
  `cache.py` is the exact-match Tier-2 only.)
- **Cognitus UI/UX** — no changes to `src/app/static/**` beyond what's strictly
  required to keep the existing minimal UI working (it should need nothing). Phase 4.
- **Graph / LightRAG mode** — `graph_lightrag.py`, `build_graph*.py`. The backlog
  says defer unless it's cheap; it is **not** cheap (GPU build, new dep) so **defer**.
  Do not add a `graph` mode.
- **FFIEC ingest** and a separate FinCEN.gov advisory scraper (`loaders/ffiec.py`,
  `loaders/fincen.py`). Deferred (see Q1).
- **Reranker as a standalone speculative module** — only add reranker code if AC-5's
  measured condition is met; even then, smallest form.
- **Dependency pinning / `requirements.lock`, Dockerfile, CI workflows** — Phase 5.
- **API/UI compliance disclaimer payload** — PRD §7, delivered with the UI phase.
- **Removing existing `ponytail:` comments** from Phase-0 files — leave them; no
  cleanup pass (out-of-scope churn).

---

## Definition of done for this iteration

`python -m scripts.build_index` (eCFR + FedReg, section-aware chunked) →
`python -m scripts.eval` for both `naive` and `hybrid` on the 20–30-item validated
gold set → default `rag_mode` set from the numbers → reranker added only if it fixes
a measured regression → `src/rag/cache.py` wired into `/chat_stream` with a passing
round-trip check → `tests/test_smoke.py` green → decision + numbers recorded in
`changes.md` and `.build/progress.md`. No `ponytail:` comments or the word
"ponytail" in any new code or commit message.
