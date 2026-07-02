# Iteration 2 — Frozen spec

**Iteration:** N=2 · "Phase 2: trigger-based ETL"
**Target tag concept:** `v0.3-etl` (not git-tagged — full-build never tags)
**Written:** 2026-07-02 · **Author role:** PM (this iteration only)

> **Read this file only.** It is self-contained. Do not re-plan from `docs/` — the
> relevant decisions are lifted below (including the live-API contracts I verified
> during this spec). Where a doc is cited it is for the senior-dev's optional
> reference, not required reading.

---

## Note on conventions (read first)

- **Operating mode is "full ponytail" (lazy = shortest working diff, YAGNI,
  stdlib/installed-deps first, one runnable check per change).** But the user has
  explicitly forbidden the literal convention: **do NOT write `ponytail:` comments
  and do NOT use the word "ponytail" anywhere in code, docstrings, or commit
  messages.** Simplifications get recorded in `changes.md` / the tech-debt ledger
  instead. The existing Phase-0/1 files contain `ponytail:` comments — **leave them
  as-is; do not add new ones and do not do a cleanup pass** (out-of-scope churn).
- Match the existing house style: module docstring stating intent, `from __future__
  import annotations`, small pure functions, dict-dispatch, env-driven config via
  `RagConfig`. **Mirror `src/rag/indexing/loaders/ecfr.py` and `fedreg.py` exactly**
  for the new watchers (they reuse/extend those loaders — see below — not replace
  them). Mirror `src/rag/cache.py` for the SQLite state module (stdlib `sqlite3`,
  one connection helper, `CREATE TABLE IF NOT EXISTS` on first use, no ORM).

---

## Goal

Make the corpus update itself **incrementally** when FinCEN (Federal Register) or
eCFR (31 CFR Chapter X) publish changes — detecting deltas from a stored watermark,
routing each event through an auditable rules engine (R1–R4), upserting only what
changed by citation, advancing the watermark only on success, and recording every
ingest action in a provenance ledger — per `docs/ETL_AND_TRIGGERS.md`.

---

## Decisions made (resolved by me during this spec — NOT open questions)

These were verified live against the real public APIs (I have curl access) or read
directly from the current code, so they are **settled**. They are recorded here for
transparency, not to halt the loop. The senior-dev follows them.

- **D1 — eCFR change detection uses the `/versions` endpoint, NOT structure-tree
  diffing.** The ETL doc §1 assumed R4 must "diff Chapter X structure to find changed
  sections" by pulling two full structure trees. I verified a **cleaner** live
  mechanism:
  `GET https://www.ecfr.gov/api/versioner/v1/versions/title-31.json?chapter=X&part={part}&issue_date[gte]={watermark}`
  returns a `content_versions[]` array where **each entry is one changed section**,
  carrying `identifier` (e.g. `"1010.311"`), `amendment_date`, `issue_date`, `date`,
  `part`, `subpart`, `type`. The endpoint **filters server-side by `issue_date[gte]`**
  (verified: filtering `>=2025-01-01` returned exactly 10 changed-section rows for
  part 1010, vs 157 unfiltered). So R4 = "list changed sections since watermark via
  `/versions`, then re-pull only those sections' full text." **No manual structural
  tree-diff is needed or wanted** — do not implement one. This is the authoritative
  per-section change signal.

- **D2 — eCFR single-section re-pull is supported.** `GET .../full/{date}/title-31.xml?chapter=X&part={part}&section={section}`
  returns just that one `<DIV8>` section (verified live for `1010.311`). So R4's
  "re-embed only changed sections" is a per-section fetch, reusing the existing
  `ecfr._text()` / `ecfr._split_section()` parsing. **Add a thin section-scoped
  variant** to `ecfr.py` (see Interfaces) rather than re-fetching the whole part.
  `{date}` must be a date eCFR accepts — use the section's own `issue_date` from the
  `/versions` row (that is a valid issued date), or `titles.json`'s current
  `up_to_date_as_of` for Title 31. Prefer the section's `issue_date` so you fetch the
  exact amended text.

- **D3 — FedReg `cfr_references` intersection keys on `(title, part)`, NOT chapter.**
  Verified live: FinCEN FedReg docs return `cfr_references` as a list of objects like
  `{"chapter": null, "citation_url": null, "part": "1010", "title": 31}`. **`chapter`
  comes back `null`**, so an intersection test that checks chapter would wrongly
  reject every doc. The R1/R2 "touches 31 CFR Chapter X" condition must be implemented
  as: **any ref with `title == 31` (int or str) AND `part` in the watched parts set**
  (`RagConfig.parts`, default `{"1010","1020"}`). Note `part` is a string, `title` may
  be int `31` — normalize both to str before comparing.

- **D4 — There is NO incremental upsert today; this iteration must add one.** I read
  `builder.py`: `build()` does `delete_collection` + `create_collection` — a **full
  teardown/rebuild every run**. `scripts/build_index.py` confirms it ("full rebuild
  each run"). And `builder.get_collection()` calls Chroma's `get_collection`, which
  **raises if the collection does not exist**. Therefore this iteration must introduce
  a true **incremental upsert-by-citation against the existing collection** (delete
  chunks for a changed citation, then add the new ones) — see `upsert_by_citation` in
  Interfaces. Do **not** call `build()` from the ETL path (it would wipe the whole
  index). `build()` and `scripts/build_index.py` remain the initial full-build path,
  unchanged.

- **D5 — FedReg watcher reuses the existing loader parser.** `fedreg._record_from_doc`
  is already a pure `doc -> record | None` parser and `load_documents` already
  paginates oldest-first from a `since` date. The watcher's job is watermark
  bookkeeping + rules routing + upsert, **not** re-implementing the fetch/parse.
  Reuse `fedreg._record_from_doc` for record shaping. The one gap: the current
  `_record_from_doc` **drops `cfr_references`, `type`, and `effective_on`** (it only
  keeps abstract-derived fields). The rules engine needs `type`, `cfr_references`, and
  `effective_on` to classify. **Do not mutate the existing record schema stored in
  Chroma;** instead the watcher reads those fields straight off the raw FedReg `doc`
  dict (which `load_documents` already has in hand) and passes them to the rules
  engine alongside the built record. See Interfaces for the exact watcher shape.

- **D6 — R2 "proposed" and R3 "advisory/notice" collections.** ETL doc §2 says R2
  ingests into a `proposed` collection and R3 into an `advisory` collection. To stay
  YAGNI and avoid a multi-collection retrieval refactor (out of scope — retrieval is
  Phase 3/untouched here), **do NOT create separate Chroma collections.** Instead
  ingest R2/R3 records into the **same `aml_kyc` collection**, disambiguated by their
  existing `source` metadata value (`fedreg_proposed` for R2, `fincen_advisory` for
  R3) — which iteration 1 already established and which the citation/`_format` path
  already carries. The "not in force" flag R2 requires is satisfied by
  `source=fedreg_proposed` (a proposed rule is self-evidently not in force). Record
  this simplification (single-collection-by-source-tag) in `changes.md`. A physical
  `proposed`/`advisory` collection split is a deferred upgrade path if a later phase
  needs collection-level filtering.

- **D7 — Scheduling context for this iteration = local/manual only.** ETL doc §5 lists
  three runner contexts (local, CI, container). The backlog scopes **CI auto-PR OUT**
  (no remote, no credentials). So `scripts/etl_run.py` is a **plain local entrypoint**
  (`python -m scripts.etl_run`) that runs one ETL pass and exits. `ETL_SCHEDULE`
  already exists as a documented env var (ARCHITECTURE §8) — **read it into config for
  completeness but the only behavior this iteration implements is a single pass**; do
  not build a scheduler loop, cron wiring, or GitHub Actions workflow. Document the
  CI/container runners as manual follow-ups in `.build/progress.md`.

---

## Acceptance criteria (testable)

Lifted from backlog Iteration 2 + ETL doc §2/§4/§7 and made observable.

1. **Watchers poll from a stored watermark.** `src/etl/watchers/fedreg.py` and
   `src/etl/watchers/ecfr.py` each read their source's watermark from
   `data/etl_state.db`, query the live API for changes **since** that watermark, and
   yield the changed items. On a fresh DB (no watermark row) they fall back to a
   configured cold-start date (`ETL_FEDREG_SINCE` / eCFR uses part-level `issue_date`
   cold-start from `ETL_ECFR_SINCE`).

2. **Rules engine R1–R4 implemented and unit-tested.** `src/etl/rules.py` classifies
   each event into exactly one of R1 (FedReg final Rule touching 31 CFR X), R2
   (Proposed Rule touching 31 CFR X), R3 (Notice/advisory matching the AML/KYC topic
   filter), R4 (eCFR section amended). Each rule maps to an explicit action record.
   A unit test (inline fixtures, **no network**) proves each rule fires on a matching
   event and does not fire on a non-matching one — including the D3 `chapter: null`
   intersection case.

3. **Upsert-by-citation load (delete + add, no stale duplicates).** A new
   `builder.upsert_by_citation(cfg, citation, records)` deletes all existing chunks
   whose `citation` metadata equals `citation`, then adds the supplied records.
   Re-running the same batch produces the **same** collection count (idempotent — no
   duplicate ids, no orphaned old chunks). A runnable check demonstrates: upsert a
   citation's chunks, upsert again with changed text, assert (a) count unchanged and
   (b) new text present / old text absent.

4. **Watermark advances only on success (R8 atomic/retriable).** The watermark for a
   source advances **only after** its batch fully loads and the provenance rows are
   written. If any item in the batch raises during extract/transform/load, the
   watermark for that source is **not** advanced (the batch re-processes next run;
   upsert-by-citation makes the retry idempotent). A test simulates a mid-batch
   failure and asserts the watermark is unchanged and no partial provenance-`success`
   row was committed for the failed item.

5. **`data/etl_state.db` schema present and populated.** Two tables exist with the
   exact columns in "Interfaces → state schema" below: `watermarks` and
   `provenance`. After an ETL pass, `watermarks` holds one row per source and
   `provenance` holds one row per ingest action (`why` a chunk is in the corpus and
   `when` it arrived — ETL doc §4). DB path is `RagConfig.etl_state_path` (default
   `ROOT/data/etl_state.db`; covered by `.gitignore`'s `data/*.db`).

6. **`GET /corpus_status` reports `as_of`, last ETL run, and counts by source.** The
   existing endpoint is extended (not replaced) to add: `last_etl_run` (timestamp of
   the most recent successful provenance row, or `null`), and `counts_by_source` (a
   dict `{source: chunk_count}` from the collection metadata). The existing `indexed`,
   `as_of`, `rag_mode` keys are preserved. If `etl_state.db` is absent, `last_etl_run`
   is `null` and the endpoint still returns 200 (ETL is optional infra).

7. **Simulated (recorded-fixture watermark) FinCEN change detected + ingested
   incrementally; re-run is idempotent.** A test seeds a watermark **artificially in
   the past** (e.g. `2024-12-31`) into `etl_state.db`, runs the FedReg watcher against
   the **real live API**, and asserts: (a) it detects ≥1 FinCEN document published
   after that watermark, (b) those documents are upserted into the collection, (c) the
   watermark advances to the newest processed `publication_date`, (d) a second
   identical run detects nothing new (watermark already current) and leaves the
   collection count unchanged. This is the "simulated change detected and ingested
   incrementally + idempotent" exit criterion, using a **real live-API fetch with a
   fixture watermark** — the same live-API-at-build-time pattern iteration 1 used for
   its loaders (parser unit-tested on fixtures; live fetch exercised for real, not
   mocked). See "Test strategy" for the network-tolerance guard.

---

## Files to create or modify

**Create:**
- `src/etl/__init__.py` — empty namespace (match existing package init style).
- `src/etl/watchers/__init__.py` — empty namespace.
- `src/etl/watchers/fedreg.py` — FedReg change watcher (watermark → live query →
  changed docs). Reuses `src.rag.indexing.loaders.fedreg`.
- `src/etl/watchers/ecfr.py` — eCFR change watcher (watermark → `/versions` since
  watermark → changed sections). Reuses `src.rag.indexing.loaders.ecfr`.
- `src/etl/rules.py` — rules engine R1–R4 (pure classification, unit-tested).
- `src/etl/pipeline.py` — orchestrates one ETL pass: for each source, watch →
  classify → extract → transform → **upsert** → record provenance → advance watermark.
- `src/etl/state.py` — SQLite watermarks + provenance ledger (mirror `cache.py` style).
- `scripts/etl_run.py` — local entrypoint: `python -m scripts.etl_run` runs one pass.
- Tests (extend `tests/`, mirror existing test style — module docstring, runnable
  `__main__`, `python -m pytest`):
  - `tests/test_etl_rules.py` — R1–R4 classification on **inline fixtures** (no
    network), including the D3 `chapter: null` case (AC-2).
  - `tests/test_etl_upsert.py` — upsert-by-citation idempotency against a **throwaway
    Chroma collection** in a tempdir (no live index dependency) (AC-3).
  - `tests/test_etl_state.py` — watermark read/write + advance-only-on-success +
    provenance row shape, against a **tempfile** `etl_state.db` (AC-4, AC-5).
  - `tests/test_etl_fedreg_live.py` — the seeded-past-watermark **live** FedReg
    detection + idempotency check (AC-7), guarded to **skip** on network failure (see
    Test strategy). This is the one test that hits the network, mirroring how the
    build script — not pytest collection — carried the live path in iteration 1; here
    it is an explicitly-network-tolerant test, not a hard CI dependency.

**Modify:**
- `src/rag/config.py` — add ETL env knobs (see "config additions" — only vars this
  iteration reads).
- `src/rag/indexing/builder.py` — add `upsert_by_citation(cfg, citation, records)` and
  a `collection_exists(cfg)` / safe accessor helper (D4: `get_collection` raises if
  absent; the upsert path and `/corpus_status` counts must not crash on an unbuilt
  index). Do **not** change `build()`'s signature or its full-rebuild behavior.
- `src/rag/indexing/loaders/ecfr.py` — add a section-scoped fetch (D2): e.g.
  `load_section(title, chapter, part, section, as_of, chunk_char_budget)` returning
  the same record schema `load_part` produces, and a `changed_sections(title, chapter,
  part, since)` helper that hits the `/versions` endpoint (D1) and returns
  `[(section_identifier, issue_date), ...]`. Keep `load_part`/`load_parts` unchanged.
- `src/rag/indexing/loaders/fedreg.py` — expose the **raw** doc list to the watcher so
  it can read `type`/`cfr_references`/`effective_on` (D5). Smallest form: add a
  `fetch_documents(agency, since, max_docs) -> list[dict]` that returns the **raw API
  `results` dicts** (before `_record_from_doc`), so the watcher can both classify (raw
  fields) and shape (`_record_from_doc`). `load_documents` (records only) stays for the
  static build path. Do not change `_record_from_doc`'s output schema.
- `src/app/api.py` — extend `/corpus_status` per AC-6 (add `last_etl_run`,
  `counts_by_source`; keep existing keys and the 200/503 behavior).
- `changes.md` and `.build/progress.md` — record the ETL design, D1–D7 decisions/
  simplifications, the resolved CFR-reference-filtering tech-debt (R1–R3 now filter
  FedReg docs by `cfr_references` — the carried-forward item from iter-1), the actual
  live counts observed, and the CI/container manual follow-ups.

**Do NOT create** (deferred / out of scope): `src/rag/faq/**`,
`src/rag/orchestration/**`, `src/rag/retrieval/graph_lightrag.py`,
`loaders/ffiec.py`, `loaders/fincen.py`, any GitHub Actions workflow, any scheduler/
cron loop, any separate `proposed`/`advisory` Chroma collection (D6),
`scripts/seed_faq.py`.

---

## Interfaces / signatures

### `src/etl/state.py` — watermarks + provenance (mirror `cache.py`)

Stdlib `sqlite3`, `RagConfig.etl_state_path`, `CREATE TABLE IF NOT EXISTS` on first
connect, no ORM. Store JSON blobs as text where needed.

**State schema (exact column names/types — the tester and senior-PM check these):**

```sql
CREATE TABLE IF NOT EXISTS watermarks (
    source        TEXT PRIMARY KEY,   -- 'fedreg' | 'ecfr'
    value         TEXT NOT NULL,      -- FedReg: last processed publication_date (YYYY-MM-DD)
                                      -- eCFR:   last processed issue_date       (YYYY-MM-DD)
    document_ref  TEXT,               -- FedReg: last document_number; eCFR: last section id (nullable)
    updated_at    TEXT NOT NULL       -- ISO-8601 UTC timestamp of this advance
);

CREATE TABLE IF NOT EXISTS provenance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,     -- ISO-8601 UTC when the action was recorded
    rule_id         TEXT NOT NULL,     -- 'R1' | 'R2' | 'R3' | 'R4'
    source          TEXT NOT NULL,     -- 'fedreg' | 'ecfr'
    document_ref    TEXT NOT NULL,     -- FedReg document_number OR eCFR citation (e.g. '31 CFR 1010.311')
    citation        TEXT NOT NULL,     -- the corpus citation upserted (FedReg doc number OR '31 CFR ...')
    action          TEXT NOT NULL,     -- 'upsert' | 'schedule' | 'skip'
    chunks_changed  INTEGER NOT NULL,  -- number of chunks added for this citation (0 for schedule/skip)
    as_of           TEXT,              -- currency stamp written for this ingest (nullable)
    status          TEXT NOT NULL      -- 'success' | 'error'
);
```

Suggested surface (keep functions small and pure-ish; take `cfg` for the path):

```python
def get_watermark(cfg, source: str) -> tuple[str, str | None] | None:
    """Return (value, document_ref) or None if no watermark yet."""

def set_watermark(cfg, source: str, value: str, document_ref: str | None) -> None:
    """INSERT OR REPLACE the watermark for source; stamps updated_at."""

def record(cfg, *, rule_id, source, document_ref, citation, action,
           chunks_changed, as_of, status) -> None:
    """Append one provenance row (stamps timestamp)."""

def last_successful_run(cfg) -> str | None:
    """Max(timestamp) over provenance WHERE status='success', or None."""

def counts_by_source(records_metadatas: list[dict]) -> dict[str, int]:
    """Helper: tally 'source' over a metadata list (used by /corpus_status).
    (Or compute this in api.py directly — placement is the dev's call; keep it
    stdlib.)"""
```

**Ordering guarantee (R8 correctness):** within one source's pass, write **all**
provenance rows for the batch, then `set_watermark` **last**, inside the same logical
step — so a crash before the watermark advance leaves the watermark pointing at the
pre-batch position and the batch re-runs. Do not advance the watermark per-item.

### `src/etl/rules.py` — R1–R4 classification (pure, unit-tested)

Pure functions over already-fetched event dicts — **no network here** (fetching is the
watcher's job). Suggested surface:

```python
WATCHED_TITLE = "31"

def touches_watched_cfr(cfr_references: list[dict], parts: set[str]) -> bool:
    """True if any ref has title==31 (normalize int/str) and part in parts.
    Implements D3: keys on (title, part); IGNORES chapter (it is null in the API)."""

def classify_fedreg(doc: dict, parts: set[str], topic_terms: set[str]) -> dict | None:
    """Map one raw FedReg doc to an action, or None to skip.
      type == 'Rule'          and touches_watched_cfr -> R1 (action='upsert' + schedule note)
      type == 'Proposed Rule' and touches_watched_cfr -> R2 (action='upsert', source=fedreg_proposed)
      type == 'Notice'        and matches topic filter -> R3 (action='upsert', source=fincen_advisory)
      else                                             -> None (skip; recorded as action='skip')
    Returns {'rule_id','action','source','effective_on'(R1 only),'schedule'(R1 only)}."""

def classify_ecfr_section(section_id: str, issue_date: str, watermark: str | None) -> dict | None:
    """A section returned by the /versions since-watermark query is by construction
    a changed section -> R4 (action='upsert'). Returns {'rule_id':'R4','action':'upsert'}.
    (The since-watermark filter already did the selection; this stamps the rule.)"""
```

**R1 scheduling note (ETL doc §2):** R1's action includes *scheduling* an eCFR re-pull
for `effective_on`. This iteration does **not** build a scheduler (D7). Implement the
"schedule" as a **provenance row with `action='schedule'`** recording the
`effective_on` date and the affected parts — an auditable "this eCFR re-pull is due on
{effective_on}" marker. The actual re-pull happens whenever the eCFR watcher next runs
after that date (its `/versions` query will surface the amended section). Do **not**
build a timer/queue. State this in `changes.md`.

**R3 topic filter:** the ETL doc says "matches AML/KYC topic filter." Keep it minimal
and explicit: a small case-insensitive keyword set checked against the doc's
`title`+`abstract` (e.g. `{"anti-money laundering","aml","bsa","suspicious activity",
"currency transaction","beneficial owner","customer due diligence","kyc","fincen"}`).
Since the feed is already the FinCEN agency feed, this is a light relevance gate, not a
classifier — a FinCEN Notice that matches none of these terms is skipped. Put the term
set in `rules.py` as a module constant; note it's a heuristic in `changes.md`.

### `src/etl/watchers/fedreg.py`

```python
def poll(cfg) -> list[dict]:
    """Read the 'fedreg' watermark (or cold-start ETL_FEDREG_SINCE), fetch raw
    FinCEN FedReg docs published since it (reuse fedreg.fetch_documents, oldest
    first), and return the raw doc dicts newer than the watermark. Empty list if
    nothing new. Does NOT advance the watermark or upsert — that's pipeline.py."""
```

- Use `>` (strictly after) the watermark's `publication_date` when a watermark exists,
  so the boundary doc isn't re-ingested every run. (`publication_date[gte]` is the API
  filter; then drop docs whose `publication_date == watermark AND document_number <=
  watermark.document_ref` to make it a clean strict-after. Simpler acceptable form:
  filter `gte` watermark, then in Python keep only docs with `document_number` not
  already at/behind the stored `document_ref` — either is fine as long as re-runs are
  idempotent, which upsert already guarantees; idempotency is the real safety net, the
  strict-after is just to avoid redundant work.)

### `src/etl/watchers/ecfr.py`

```python
def poll(cfg) -> list[dict]:
    """For each watched part (cfg.parts), call ecfr.changed_sections(title, chapter,
    part, since=<eCFR watermark or ETL_ECFR_SINCE>) to get sections amended since the
    watermark. Return a list of {'part','section','issue_date'} for changed sections
    across all parts. Empty if nothing changed. Does NOT fetch full text or upsert."""
```

- eCFR watermark `value` = the max `issue_date` processed. `changed_sections` passes
  `issue_date[gte]=since`; then keep only rows with `issue_date > since` (strict) when
  a watermark exists, to avoid re-processing the boundary. Idempotency via upsert is
  again the safety net.

### `src/etl/pipeline.py` — one ETL pass

```python
def run_once(cfg) -> dict:
    """Run one full ETL pass over both sources. Returns a summary dict
    {'fedreg': {...counts...}, 'ecfr': {...counts...}} for the entrypoint to print.
    Per source, in order:
      1. poll() the watcher for changed events.
      2. For each event: classify (rules), extract (fetch section/build record),
         transform (chunk), upsert_by_citation, record provenance (status='success').
      3. On any per-item exception: record provenance status='error' for that item and
         RAISE/abort this source's watermark advance (do not advance past a failed batch).
      4. If the whole batch succeeded, set_watermark to the newest processed
         value/document_ref for that source.
    A failure in one source must not corrupt the other source's watermark."""
```

- **Extract/transform per rule:**
  - R1/R2/R3 (FedReg): build the record via `fedreg._record_from_doc(doc)` (the abstract
    is the text — abstract-only is the accepted iter-1 baseline; do **not** newly fetch
    `full_text_xml_url` this iteration, that's a separate deferred item). The upsert
    `citation` = the FedReg `document_number` (matches iter-1's `citation` for FedReg).
    For R2 force `source='fedreg_proposed'`, R3 `source='fincen_advisory'` (already what
    `_record_from_doc` yields by type, but assert it).
  - R4 (eCFR): fetch the one changed section via `ecfr.load_section(...)` (D2), which
    returns 1+ chunk records sharing `citation='31 CFR {section}'`; upsert by that
    citation.
- **Chunks changed** in the provenance row = `len(records)` upserted for that citation.
- **as_of** written = FedReg `publication_date` (R1–R3) or the eCFR section `issue_date`
  (R4) — the same `as_of` already stored in the record metadata.

### `src/rag/indexing/builder.py` additions

```python
def collection_exists(cfg) -> bool:
    """True if the Chroma collection is present (list_collections / try get)."""

def upsert_by_citation(cfg, citation: str, records: list[dict]) -> int:
    """Incremental upsert against the EXISTING collection (D4):
      1. get_or_create the collection (do NOT delete_collection — that's build()'s job).
      2. Query existing ids where metadata 'citation' == citation; delete them.
      3. col.add(...) the new records (same ids/documents/metadatas shape as build()).
    Returns len(records). Idempotent: re-running with identical records yields the same
    final state (old chunks for the citation are cleared first every time)."""
```

- Use Chroma's metadata `where={"citation": citation}` on `col.get(...)` to find the
  ids to delete, then `col.delete(ids=...)`, then `col.add(...)`. If the collection
  doesn't exist yet, create it (`get_or_create_collection`) so an ETL run against a
  never-built index doesn't crash — but the normal path assumes Phase-0/1 already built
  it. **Reuse the exact same `_META`/id/document construction `build()` uses** (extract
  a shared `_records_to_add_args(records)` helper if it reduces duplication; optional).
- Chroma's `add` errors on **duplicate ids** — because we delete-then-add for the
  citation, and eCFR/FedReg ids are citation-scoped (`ecfr-31-1010.311[-N]`,
  `fedreg-{docnum}`), re-adding after delete is safe. Verify no id from a *different*
  citation collides (it won't, by construction).

### `src/rag/indexing/loaders/ecfr.py` additions

```python
def changed_sections(title, chapter, part, since: str) -> list[tuple[str, str]]:
    """Hit /versions/title-{title}.json?chapter=&part=&issue_date[gte]=since.
    Return [(section_identifier, issue_date), ...] for changed sections (D1).
    dedupe to the latest issue_date per identifier."""

def load_section(title, chapter, part, section, as_of, chunk_char_budget) -> list[dict]:
    """Fetch ONE section's full XML (D2: full/{as_of}/title-{title}.xml?chapter=&
    part=&section=) and return its record(s) — same schema/splitting as load_part,
    just scoped to one DIV8."""
```

- `changed_sections` parses `content_versions[]`; each item's `identifier` is the
  section number (e.g. `"1010.311"`), `issue_date` the amended-issue date. Filter to
  `type == 'section'`. Keep only the max `issue_date` per identifier (a section can
  appear multiple times across historical amendments).
- `load_section` reuses `_text` + `_split_section`; build the same `base` metadata dict
  `load_part` builds, with `as_of` = the section's `issue_date` you pass in.

### `src/rag/indexing/loaders/fedreg.py` addition

```python
def fetch_documents(agency, since, max_docs) -> list[dict]:
    """Same request as load_documents but return the RAW API results dicts (with
    type/cfr_references/effective_on intact) instead of built records (D5). The
    watcher classifies on raw fields then shapes via _record_from_doc."""
```

- Refactor is optional: `load_documents` can become `[_record_from_doc(d) for d in
  fetch_documents(...) if _record_from_doc(d)]`. Keep `load_documents`' existing
  behavior/signature identical for the static build path.

### `src/app/api.py` — `/corpus_status` extension (AC-6)

Extend the existing handler. Final JSON on success:

```python
{
  "indexed": n,                      # existing
  "as_of": as_of,                    # existing (peek metadata)
  "rag_mode": CONFIG.rag_mode,       # existing
  "last_etl_run": <iso ts or None>,  # NEW: state.last_successful_run(CONFIG)
  "counts_by_source": {src: cnt},    # NEW: tally 'source' over col.get(include=['metadatas'])
}
```

- Wrap the new state read in try/except so a missing `etl_state.db` yields
  `last_etl_run=None`, not a 500 (ETL is optional). Keep the existing 503-on-missing-
  collection behavior for `indexed`.
- `counts_by_source` from a single `col.get(include=["metadatas"])` — acceptable for
  the small demo corpus (~400 chunks). Do not add a separate count index.

### `src/rag/config.py` additions

Add only these fields (frozen dataclass, env-driven, existing `_b()`/`int()` style):

```python
etl_state_path: str   # ETL_STATE_PATH,  default ROOT/data/etl_state.db
etl_schedule: str     # ETL_SCHEDULE,    default "daily"  (read for completeness; single-pass only — D7)
etl_fedreg_since: str # ETL_FEDREG_SINCE, default "2020-01-01"  (cold-start watermark, no DB row yet)
etl_ecfr_since: str   # ETL_ECFR_SINCE,   default "2020-01-01"  (cold-start eCFR issue_date floor)
```

Reuse existing `fedreg_agency`, `ecfr_title`, `ecfr_chapter`, `parts` (property),
`chunk_char_budget` — do **not** duplicate them.

---

## Edge cases

- **Never call `build()` from the ETL path.** `build()` deletes and recreates the whole
  collection (D4) — using it for an incremental update would wipe the corpus. The ETL
  path uses only `upsert_by_citation`.
- **Collection absent when ETL runs.** `get_collection` raises if the collection
  doesn't exist. `upsert_by_citation` must `get_or_create` so a first ETL run on an
  unbuilt index doesn't crash; `/corpus_status` already returns 503 gracefully on a
  missing collection — keep that.
- **`chapter: null` in FedReg `cfr_references` (D3).** The intersection test must not
  check chapter. Test this explicitly (AC-2) — it's the single most likely silent bug.
- **`title` type in cfr_references.** `title` may arrive as int `31` (verified) — cast
  to str before comparing to `WATCHED_TITLE="31"`. `part` arrives as str.
- **Watermark boundary re-processing.** Using `[gte]` on the API then not filtering
  strict-after would re-fetch the boundary doc/section every run. Upsert makes that
  *safe* (idempotent) but wasteful; do the strict-after filter to avoid redundant
  embed work. Idempotency (not the filter) is the correctness guarantee.
- **Empty delta (nothing changed).** `poll()` returns `[]`; the pass records **no**
  provenance rows and **does not** advance the watermark (there's nothing to advance
  to). AC-7's second run exercises this. `run_once` must handle an empty delta without
  error and without spurious ledger rows.
- **Mid-batch failure (R8).** If item _k_ of a source's batch raises, record an
  `error` provenance row for item _k_ and **abort the watermark advance for that
  source** (leave it at the pre-batch value). Items 0..k-1 that already upserted stay
  upserted — that's fine, because the next run re-processes the whole batch from the
  unadvanced watermark and upsert-by-citation makes the re-ingest idempotent (no
  duplicates). This is exactly the ETL doc §6 atomicity contract; do not attempt a
  transactional rollback of Chroma (it has no cross-collection transaction) — rely on
  upsert idempotency + watermark-hold instead. Test with an injected failure (AC-4).
- **eCFR `full` requires a valid date.** Use the section's `issue_date` from
  `changed_sections` as `{as_of}` for `load_section` (a real issued date the API
  accepts, verified). Do not invent a date.
- **Chroma metadata scalars only.** All upserted metadata stays scalar strings (same
  `_META` constraint as `build()`); no lists/objects in metadata. `cfr_references`
  (a list) is used only for *classification*, never stored in Chroma metadata.
- **Duplicate ids on add.** Delete-then-add per citation prevents Chroma's duplicate-id
  error. eCFR chunk ids keep the `-N` suffix scheme; a shrinking section (fewer chunks)
  is handled because the delete clears *all* prior chunks for that citation first.
- **Network flakiness in the one live test.** `tests/test_etl_fedreg_live.py` must
  `pytest.skip(...)` on `requests` connection/timeout errors so an offline CI run
  doesn't fail the suite (see Test strategy) — the non-network tests (rules, upsert,
  state) carry the deterministic coverage.

---

## Test strategy (how AC-7's "simulated change detected + ingested" is proven)

Per the framing: watchers hit **live public APIs** (eCFR `/versions`, FedReg
`documents.json`) — same as iteration 1's loaders. There is **no fake API server.** A
repeatable, deterministic-enough test of "a change was detected and upserted" is built
from a **fixture watermark against the real API**:

1. **Deterministic, offline-safe (the bulk of coverage):**
   - `test_etl_rules.py` — R1–R4 on inline event dicts (no network). Includes the
     `chapter: null` intersection, a `Rule`+part-1010 → R1, a `Proposed Rule` → R2, a
     `Notice` matching a topic term → R3, a `Notice` matching nothing → skip, and an
     eCFR section → R4.
   - `test_etl_upsert.py` — build a throwaway Chroma collection in a tempdir, seed 2
     chunks for citation C, `upsert_by_citation(C, new_chunks)`, assert count stable,
     new text present, old text gone; run the same upsert twice, assert idempotent.
   - `test_etl_state.py` — tempfile `etl_state.db`: set/get watermark; record success
     + error provenance rows; assert `last_successful_run` ignores error rows; simulate
     a batch where the watermark is NOT advanced after an error.

2. **Live, network-tolerant (AC-7 exit criterion):**
   - `test_etl_fedreg_live.py` — seed `watermarks` with `('fedreg', '2024-12-31',
     None)`, run `pipeline.run_once` (or the fedreg-only path) against the real API,
     assert ≥1 doc detected + upserted + watermark advanced past 2024-12-31; run again,
     assert no new upserts and count stable. **Guard:** wrap the live call; on
     `requests.exceptions.RequestException` call `pytest.skip("live FedReg API
     unreachable")`. This mirrors iter-1's stance (live fetch exercised for real, not
     mocked; not a hard offline dependency). Use a **tempdir Chroma copy** or a
     dedicated throwaway collection so the test never mutates the committed
     `data/chroma` index.

> The senior-dev should **run the live path once for real** during the build (like
> iter-1 ran `build_index` for real) and record the actual observed counts (e.g. "N
> FinCEN docs since 2024-12-31 detected and upserted") in `changes.md`. Note (from my
> live check today): the FinCEN feed had **33 documents since 2025-01-01**, so a
> `2024-12-31` seed watermark reliably yields a non-empty delta — a dependable
> "change detected" demonstration.

---

## Patterns to follow

- **Watchers/pipeline → mirror the loaders' live-API-at-build-time stance.** `requests`
  + `UA` header + `timeout` + `raise_for_status()`; pure record shaping separated from
  fetching; no fixtures for the live fetch (fixtures only for pure classifiers/parsers).
- **`state.py` → mirror `src/rag/cache.py`** exactly: one `_conn(cfg)` helper with
  `CREATE TABLE IF NOT EXISTS`, small `get`/`set`/`record` functions, JSON-as-text for
  any structured column, `with conn:` for writes, `conn.close()` in `finally`. No ORM,
  no migration framework.
- **`rules.py` → pure dict-returning classifiers**, dict-dispatch style like
  `factory.py`'s `_MODES`. Unit-tested with inline dicts, runnable `__main__`.
- **`upsert_by_citation` → reuse `build()`'s id/document/metadata construction**;
  the only new behavior is delete-by-citation-then-add against an existing collection.
- **`/corpus_status` → extend, don't rewrite;** keep existing keys and status codes,
  add the two new keys, guard the new state read.
- **Config → one frozen dataclass field per env var**, `_b()` for bools, `int(...)`
  for ints, path defaults under `ROOT/data/`.
- **Runnable check per change (house rule):** each new module ships one runnable
  assertion (rules test, upsert test, state test) plus the network-tolerant live test.
- **Provenance completeness (ETL doc §4 requirement):** every ingest action writes a
  row that answers *why* (rule_id + document_ref) and *when* (timestamp, as_of). Skips
  and schedules are also recorded (`action='skip'|'schedule'`) so the ledger explains
  the full pass, not just successful upserts.

---

## Out of scope (do NOT touch this iteration)

- **R5 (FAQ refresh), R6 (graph rebuild), R7 (FFIEC ingest)** — Phase 3. Do not wire
  FAQ or graph sync; do not add `loaders/ffiec.py`. R8 retry/backoff **and** the
  watermark-advance-on-success atomicity **ARE in scope** (they're core to R1–R4
  correctness) — implement the advance-only-on-success + idempotent-retry semantics;
  a full exponential-backoff HTTP retry layer is optional (a single retry or none is
  acceptable — the correctness guarantee is watermark-hold + upsert idempotency, not
  the backoff curve). If you add backoff, keep it minimal (stdlib, no new dep).
- **Scheduled-CI auto-PR / GitHub Actions / container entrypoint loop** — no remote, no
  credentials (backlog + D7). `scripts/etl_run.py` is a single local pass. Document
  CI/container runners as manual follow-ups in `.build/progress.md`; do **not** author
  a workflow file this iteration.
- **Separate `proposed`/`advisory` Chroma collections** — single collection tagged by
  `source` (D6). No multi-collection retrieval refactor.
- **Full-text XML fetch for FedReg docs** — abstract-only stays the baseline (iter-1
  accepted tech-debt). Do not add `full_text_xml_url` fetching here.
- **Orchestration & semantic FAQ cache** (`src/rag/orchestration/**`,
  `src/rag/faq/**`, planner/skills, `answer_verifier`, `seed_faq.py`) — Phase 3.
- **Cognitus UI/UX** — no `src/app/static/**` changes beyond keeping the existing UI
  working (it needs none; `/corpus_status` gains keys the current UI can ignore).
  Phase 4.
- **Graph / LightRAG mode**, **dependency pinning / Dockerfile / CI** — Phase 5.
- **Changing `build()`'s full-rebuild behavior or `_record_from_doc`'s stored schema**,
  or retrieval-mode defaults (`rag_mode` stays `naive` from iter-1). Do not re-open the
  iter-1 retrieval decision.
- **Removing existing `ponytail:` comments** from Phase-0/1 files — leave them; no
  cleanup pass.

---

## Definition of done for this iteration

`python -m scripts.etl_run` runs one ETL pass over FedReg + eCFR: watchers read
watermarks from `data/etl_state.db`, the rules engine classifies each change (R1–R4),
changed material is **upserted by citation** into the existing `aml_kyc` collection
(no full rebuild, no stale duplicates), the provenance ledger gets one row per action
(explaining why/when), and each source's watermark advances **only on a fully
successful batch**. `GET /corpus_status` reports `as_of`, `last_etl_run`, and
`counts_by_source`. Deterministic tests (`test_etl_rules`, `test_etl_upsert`,
`test_etl_state`) pass offline; the network-tolerant `test_etl_fedreg_live`
demonstrates a seeded-past-watermark FinCEN change detected + ingested incrementally
and idempotent on re-run (or skips cleanly if the API is unreachable). The carried-
forward CFR-reference-filtering tech-debt is resolved (R1–R3 now gate FedReg docs by
`cfr_references`). Decisions D1–D7, live counts, and CI/container manual follow-ups are
recorded in `changes.md` and `.build/progress.md`. No `ponytail:` comments or the word
"ponytail" in any new code, docstring, or commit message.
```
