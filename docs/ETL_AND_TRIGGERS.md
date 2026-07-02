# ETL & Trigger Design — AML/KYC RAG Chatbot

**Deviation 1 of 4.** · **Status:** Draft v1 · **Last updated:** 2026-06-25

> **Goal:** keep the answerable corpus current *automatically and incrementally*.
> When FinCEN publishes — or when 31 CFR Chapter X is amended — the system detects
> it, ingests only what changed, re-embeds only the affected chunks, and stamps the
> new `as_of` date. No manual full rebuilds.

This is the headline departure from `fedacq-rag-chatbot`, whose index is built
once and committed. AML/KYC rules change often enough that a static index goes
stale fast, so currency is a first-class, automated property here.

---

## 1. Sources & how they change

| Source | API / access | Change signal we watch |
|--------|--------------|------------------------|
| **eCFR — 31 CFR Ch. X** | eCFR public REST API (`/api/versioner/v1/...`) | `titles.json` → `latest_amended_on` / `up_to_date_as_of` for Title 31 advances |
| **Federal Register — FinCEN** | FedReg public API (`/api/v1/documents.json`) | New document for agency `financial-crimes-enforcement-network` since last watermark |
| **FFIEC BSA/AML Exam Manual** | Public manual sections | Section/version change (lower cadence; checksum compare) |
| **FinCEN advisories & FAQs** | FinCEN.gov publications | New/updated advisory or FAQ entry |

Both primary APIs are **public, key-less, JSON**, which keeps the ETL fully local
and free — consistent with the project's no-cloud-cost principle.

### Federal Register query (trigger feed)

```
GET https://www.federalregister.gov/api/v1/documents.json
    ?conditions[agencies][]=financial-crimes-enforcement-network
    &conditions[publication_date][gte]={last_watermark}
    &order=oldest
    &per_page=100
    &fields[]=document_number&fields[]=type&fields[]=title
    &fields[]=abstract&fields[]=publication_date&fields[]=effective_on
    &fields[]=cfr_references&fields[]=html_url&fields[]=full_text_xml_url
```

Key fields the rules engine consumes:
- `type` — `Rule` (final), `Proposed Rule`, `Notice`.
- `cfr_references` — **which CFR parts the document affects** (the routing key —
  tells us whether 31 CFR Chapter X is touched).
- `effective_on` — when a final rule takes effect (schedules the eCFR re-pull).
- `document_number`, `publication_date` — identity + watermark + "what changed".

### eCFR change check (corpus refresh)

```
GET https://www.ecfr.gov/api/versioner/v1/titles.json          # → latest_amended_on for Title 31
GET https://www.ecfr.gov/api/versioner/v1/structure/{date}/title-31.json   # parts/sections under Chapter X
GET https://www.ecfr.gov/api/versioner/v1/full/{date}/title-31.xml?...     # changed section content
```

`latest_amended_on` advancing for Title 31 is the authoritative signal that the
*in-force text* changed; we then diff Chapter X structure to find changed sections.

---

## 2. The rules engine (intelligent, rules-based)

The "intelligence" is an explicit, auditable **event → action** rule table — not a
black box. Each incoming event is classified and routed. Rules live in
`src/etl/rules.py` and are unit-tested.

| # | Trigger (event) | Condition | Action | Corpus effect |
|---|-----------------|-----------|--------|---------------|
| R1 | FedReg doc, `type=Rule` (final) | `cfr_references` ∩ {31 CFR X} ≠ ∅ | Ingest the rule as a **change record**; **schedule** eCFR re-pull of affected parts for `effective_on` | Adds change record now; updates in-force text at effective date |
| R2 | FedReg doc, `type=Proposed Rule` | touches 31 CFR X | Ingest into **`proposed`** collection, flagged *not in force* | Visible to "what's coming" queries; in-force text untouched |
| R3 | FedReg doc, `type=Notice` / advisory | matches AML/KYC topic filter | Ingest into **`advisory`** collection; mark FAQ-refresh candidate | Enriches advisory answers |
| R4 | eCFR `latest_amended_on` (Title 31) advances | structural diff finds changed sections in Ch. X | **Diff → re-embed → upsert** changed sections; bump `as_of` | In-force corpus updated incrementally |
| R5 | Any successful corpus change (R1/R4) | affected sections intersect FAQ topics | Trigger **FAQ refresh** for affected entries | Cache stays correct |
| R6 | Any successful corpus change | affected sections in the graph subset | Mark **graph rebuild** needed (queued for GPU build) | GraphRAG stays consistent |
| R7 | FFIEC section checksum changes | — | Re-ingest changed manual section | Examiner-guidance corpus updated |
| R8 | Fetch/parse error | retriable | Backoff + retry; on repeated failure, **alert + hold watermark** | No partial/corrupt ingest |

**Why rules, not just "re-embed everything on a timer":**
- **Selective** — only changed sections are re-embedded (cheap on CPU).
- **Correct** — proposed vs. final vs. advisory are handled differently; we never
  let a *proposed* rule contaminate the *in-force* answer.
- **Auditable** — every action is attributable to a rule + a source document, which
  matters in a compliance context.

---

## 3. Pipeline stages

```
WATCH ──▶ CLASSIFY (rules) ──▶ EXTRACT ──▶ TRANSFORM ──▶ LOAD ──▶ SYNC ──▶ RECORD
  │            │                  │            │           │        │         │
 poll       event→action     pull XML/    parse →      upsert    FAQ +    provenance
 FedReg     (R1–R8)          JSON/HTML    chunk →      Chroma    graph    ledger +
 + eCFR                                    embed       (by       refresh  watermark
                                           (changed    citation) (R5/R6)  advance
                                            only)
```

1. **Watch** (`src/etl/watchers/`): `fedreg.py`, `ecfr.py`, polling since the stored
   watermark. Idempotent — re-running yields no duplicate work.
2. **Classify** (`rules.py`): map each event to actions R1–R8.
3. **Extract**: pull the source artifact (FedReg `full_text_xml_url`; eCFR section
   XML; FFIEC section).
4. **Transform** (`pipeline.py`): parse to normalized docs with the metadata schema
   (`source`, `citation`, `part`, `section`, `as_of`, `fedreg_doc_number`,
   `publication_date`, `valid_from`, `valid_to`, `url`); **section-aware chunking**.
5. **Load**: **upsert by citation** into ChromaDB — delete existing chunks for a
   changed `citation`, then add the new ones (clean replace, no stale duplicates).
6. **Sync**: trigger FAQ refresh (R5) and queue graph rebuild (R6) as needed.
7. **Record**: write the provenance ledger row and advance the watermark **only on
   success** (R8 guarantees we never advance past a failed batch).

---

## 4. State, watermarks & provenance

`data/etl_state.db` (SQLite) holds:

- **Watermarks** — last processed `publication_date` / `document_number` (FedReg);
  last `latest_amended_on` (eCFR Title 31); FFIEC section checksums.
- **Provenance ledger** — one row per ingest action: `(timestamp, rule_id,
  source, document_number/citation, action, chunks_changed, as_of, status)`.
  This is the audit trail: *why* is any chunk in the corpus, and *when* did it
  arrive.
- **Version history** — superseded section versions are retained with
  `valid_from`/`valid_to` so the system can answer **"what changed and when"** (R1
  change records + R4 diffs), not just "what is the rule now."

---

## 5. Scheduling & runners

The same `scripts/etl_run.py` entrypoint runs in three contexts (config via
`ETL_SCHEDULE`):

| Context | Mechanism | Use |
|---------|-----------|-----|
| **Local/dev** | `make etl` or cron | Manual or laptop-scheduled runs |
| **CI** | GitHub Actions scheduled workflow (`cron:` daily) | Detect changes; open a PR that commits the refreshed LFS index + ledger |
| **Container** | entrypoint loop honoring `ETL_SCHEDULE` | Self-updating deployment |

Default cadence **daily** comfortably meets the currency SLA — FinCEN publishes on
the order of ~20 Federal Register documents per year, so per-run deltas are small
and runs are cheap. Cadence is configurable down to hourly if desired.

**CI pattern (recommended for the portfolio build):** a scheduled Action runs the
watcher, and if anything changed, **commits the updated `data/chroma/` (Git LFS) +
`etl_state.db` ledger via an automated PR**. This makes the "self-updating corpus"
visible in the repo's history — a strong, concrete demonstration of event-driven
data engineering.

---

## 6. Failure handling & safety

- **Atomicity:** watermark advances only after a batch fully loads (R8). A crash
  mid-batch re-processes that batch next run; upsert-by-citation makes it idempotent.
- **Backoff/retry:** transient HTTP/parse errors retried with exponential backoff;
  persistent failures alert and hold the watermark.
- **Validation gate:** post-transform sanity checks (non-empty text, resolvable
  citation, parseable structure) before load; failures quarantined, not loaded.
- **Reversibility:** version history + the committed-LFS history means any bad
  ingest can be rolled back to a prior `as_of`.
- **Observability:** `GET /corpus_status` surfaces current `as_of`, last successful
  ETL run, and counts by source.

---

## 7. Build order (ties into ROADMAP)

1. **Phase 0** — initial full build (`build_index.py`) over eCFR 31 CFR X snapshot.
2. **Phase 2** — FedReg + eCFR watchers + rules R1–R4 (the core currency loop).
3. **Phase 2** — provenance ledger, `/corpus_status`, version history.
4. **Phase 3** — FAQ/graph sync (R5/R6), FFIEC ingest (R7), scheduled-CI auto-PR.

---

## 8. Open items

- Confirm the most reliable machine-readable FFIEC manual source + change signal.
- Decide whether proposed-rule answers are surfaced by default or behind a toggle.
- Tune section-aware chunking against eCFR XML paragraph structure (see
  ARCHITECTURE §7).
