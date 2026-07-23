# aml-kyc-rag-chatbot

### Anti-Money-Laundering / Know-Your-Customer Retrieval-Augmented Generation (RAG) Chatbot

A production-minded, **fully local** RAG system that gives fast, accurate,
citation-backed answers about U.S. **AML/KYC regulation** — the Bank Secrecy Act
implementing rules (31 CFR Chapter X), FinCEN rulemakings and advisories, and the
FFIEC BSA/AML Examination Manual. Built for compliance analysts, BSA officers, and
financial-institution teams who need defensible answers grounded in primary
sources. Runs on a consumer laptop — no GPU, no cloud API, no subscription.

This project is the AML/KYC sibling of
[**fedacq-rag-chatbot**](https://github.com/PWDevens/fedacq-rag-chatbot) and
reuses its proven local-first architecture (LlamaIndex + ChromaDB + ONNX
Phi-4-mini, a selectable retrieval `factory`, a cross-encoder reranker, an answer
cache, Flask/SSE serving, Docker, and a tagged version progression). It then
**extends** that baseline in four deliberate directions:

| # | Deviation from fedacq | Why it matters |
|---|------------------------|----------------|
| 1 | **Trigger-based ETL** — an intelligent, rules-driven ingestion pipeline that watches FinCEN's Federal Register feed and the eCFR change endpoints and re-indexes only what changed. | AML/KYC rules move constantly (CDD rule, beneficial-ownership/CTA, advisories). The corpus must stay current without full rebuilds. |
| 2 | **Agent / skill orchestration** — a lightweight planner that frames the query, classifies intent, picks the retrieval strategy, and verifies the answer against retrieved text. | Compliance questions are heterogeneous (definitional, threshold/numeric, procedural, "what changed"). One naive path under-serves them. |
| 3 | **Cached FAQ fast-path** — the most common BSA/AML questions are pre-answered and served from a semantic cache. | Sub-second answers for the ~80% of traffic that is repeat questions; saves CPU generation for novel queries. |
| 4 | **Cognitus UI/UX** — the front end adopts the Cognitus design system (Jefferson-Blue palette, Abadi ExtraLight headings, hairline rules). | A credible, consulting-grade interface that matches the house brand and reads as professional, not toy. |

> ⚠️ **Not legal or compliance advice.** This tool surfaces and summarizes
> public regulatory text with citations. It is a research aid, not a substitute
> for qualified counsel or a firm's compliance program. See
> [`docs/PRD.md` §Compliance & Disclaimers](docs/PRD.md).

---

## Status

✅ **v1.0 — Phase 0–5 complete.** This is a tested, pinned, documented release,
to the limit a single local development machine (no Docker, no git remote) can
verify — see "Honesty notes" below for exactly what that limit is.

- **Phase 0:** eCFR loader, naive retrieval, generation, Flask+SSE app.
- **Phase 1:** Multi-mode retrieval backbone (`naive` / `hybrid` / `hybrid_rerank`), FinCEN Federal Register corpus, section-aware chunking, exact-match answer cache.
- **Phase 2:** Trigger-based ETL (watchers for FedReg + eCFR, rules engine R1–R4, incremental upsert-by-citation, provenance ledger).
- **Phase 3:** Local orchestration layer (query framing, intent classification, retrieval routing, answer verification) + semantic FAQ cache (Tier-1, 29 curated entries). Orchestration **off** by default; FAQ cache **on** by default.
- **Phase 4:** Cognitus design system UI: Jefferson-Blue structural color, Bronze eyebrow kickers / source badges, Cyan streaming caret accent, hairline rules. All interaction states rendered (streaming, citations, verifier-decline, FAQ-hit marker).
- **Phase 5 (this release):** Dependencies pinned to a verified lockfile (`requirements.lock`); test suite expanded to close retrieval-factory/RRF coverage gaps; real latency and eval numbers measured and published (see "Results" below); a genuine from-scratch rebuild demonstrated; the codebase's internal shorthand comments reworded to plain language; Docker + CI **built, run, and verified green** on a Docker-enabled host (see "Honesty notes"); README/CHANGELOG finalized; MIT `LICENSE` added.

**Honesty notes (read before trusting a "done" claim in this README):**
- Everything under "Quickstart" and "Results" below was **actually run** and
  the numbers are real — see `.build/iter-5/test-results.md` for the exact
  commands and full output.
- The **Docker** image and the **CI workflow** were **built, run, and verified**
  on a Docker-enabled host on 2026-07-23. `docker build` produces a working
  image whose container serves the app; GitHub Actions (`test` + `docker-build`
  jobs) runs green — see run
  [#30031024428](https://github.com/PWDevens/aml_and_kyc_guidance_chatbot/actions/runs/30031024428).
  Two defects surfaced by that first real run (bare-`pytest` import path; the
  container binding `127.0.0.1` instead of `0.0.0.0`) were fixed as part of it.

See [CHANGELOG](CHANGELOG.md) for per-iteration details and [`docs/ROADMAP.md`](docs/ROADMAP.md) for the phased plan this release completes.

---

## Quickstart / Run

Prerequisites: **Python 3.12 required** (built and tested against 3.12.10; the
`requirements.lock` freeze is a 3.12 environment and the CI/Docker images pin
`python:3.12`). Newer interpreters (e.g. 3.13) are **not** a supported target —
some pinned wheels in the lock have no 3.13 build. No GPU required (int4 CPU
generation), no external services beyond outbound HTTPS to the eCFR/Federal
Register public APIs during index build.

```bash
# 1. Install pinned dependencies (the exact versions this build was verified against)
pip install -r requirements.lock

# 2. Build the retrieval index from eCFR + FinCEN Federal Register (~1-2 min; live API calls)
python -m scripts.build_index

# 3. Seed the semantic FAQ cache (29 curated entries)
python -m scripts.seed_faq

# 4. Run the app
python -m src.app.asgi
# -> http://127.0.0.1:8000/
```

These are the exact commands verified end-to-end (fresh index + FAQ db, then a
live chat round-trip) in `.build/iter-5/test-results.md` (AC-5) — not
aspirational steps.

Run the test suite:

```bash
python -m pytest tests/ -q                                        # full suite, ~139-146 tests, ~3 min
python -m pytest tests/ -q --deselect tests/test_etl_fedreg_live.py  # deterministic subset, ~35-95s
```

### Docker

A `Dockerfile` (repo root) and `docker/docker-compose.yml` are provided for a
one-command containerized run:

```bash
docker compose -f docker/docker-compose.yml up --build
# or:  docker build -t aml-kyc-rag-chatbot . && docker run -p 8000:8000 aml-kyc-rag-chatbot
```

> **Status: built, run, and verified (2026-07-23, Docker-enabled host).**
> `docker build` produces a ~9.4 GB image (`python:3.12-slim` base, deps from
> `requirements.lock`, index + FAQ db built at image-build time). The running
> container serves `/healthz`, `/corpus_status` (402 chunks), and
> `/chat_stream` — FAQ fast-path and live Phi-4 generation, both HTTP 200 —
> reachable on the published port because the container binds `0.0.0.0`
> (`HOST=0.0.0.0`, set in the Dockerfile; `src/app/asgi.py` defaults to
> `127.0.0.1` for local dev). The same `docker build` runs green in CI.

---

## Knowledge base (corpus)

| Source | Role | Access |
|--------|------|--------|
| **eCFR — 31 CFR Chapter X** (FinCEN BSA regs: CIP, CDD, beneficial ownership, SAR/CTR, recordkeeping) | **Primary answerable corpus** — the in-force rules | eCFR public REST API (`versioner` structure + XML) |
| **Federal Register — FinCEN documents** (final rules, proposed rules, notices, advisories) | **ETL trigger stream** + recent/proposed changes | Federal Register public API (`financial-crimes-enforcement-network` agency) |
| **FFIEC BSA/AML Examination Manual** | Examiner guidance / practical "how-to" depth | Public manual sections |
| **FinCEN advisories & FAQs** | Topical guidance; seed material for the FAQ cache | FinCEN.gov publications |

See [`docs/ETL_AND_TRIGGERS.md`](docs/ETL_AND_TRIGGERS.md) for how each source is
ingested, normalized, and kept current.

---

## Documentation index

The full product development plan lives in [`docs/`](docs/):

| Doc | Covers |
|-----|--------|
| [`PRD.md`](docs/PRD.md) | Problem, users, user stories, scope, acceptance criteria, compliance disclaimers, success metrics |
| [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System architecture, retrieval modes, repo layout, local-first stack, serving path |
| [`ETL_AND_TRIGGERS.md`](docs/ETL_AND_TRIGGERS.md) | **Deviation 1** — intelligent, rules-based ETL keyed off FinCEN/eCFR change triggers |
| [`AGENT_ORCHESTRATION.md`](docs/AGENT_ORCHESTRATION.md) | **Deviation 2** — query framing, intent routing, retrieval selection, answer verification |
| [`FAQ_CACHE.md`](docs/FAQ_CACHE.md) | **Deviation 3** — semantic FAQ fast-path and caching strategy |
| [`UIUX_COGNITUS.md`](docs/UIUX_COGNITUS.md) | **Deviation 4** — UI/UX built on the Cognitus design system |
| [`ROADMAP.md`](docs/ROADMAP.md) | Phased E2E roadmap, milestones, testing/CI, risks, version progression |

---

## Architecture at a glance

```
                         ┌─────────────────────────────────────────────┐
   User question ───────▶│  Orchestrator (planner / skills)            │
                         │  frame → classify intent → route            │
                         └───────┬───────────────┬─────────────────────┘
                                 │               │
                    FAQ semantic │               │ novel / complex query
                    cache hit    ▼               ▼
                       instant   ┌───────────────────────────────────┐
                       replay    │  Retrieval factory (RAG_MODE)     │
                                 │   naive | hybrid | graph          │
                                 │   + cross-encoder reranker        │
                                 └───────────────┬───────────────────┘
                                                 │ (context, citations)
                                                 ▼
                                 ┌───────────────────────────────────┐
                                 │  Phi-4-mini (ONNX, CPU) generate  │
                                 │  + answer verification skill      │
                                 └───────────────┬───────────────────┘
                                                 ▼
                                       SSE stream → Cognitus UI
                                       (tokens + citation panel)

   Offline:  Trigger-based ETL  ──(FinCEN FedReg + eCFR change detection)──▶
             incremental parse → chunk → embed → upsert ChromaDB + refresh FAQ
```

Full detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Results

Real numbers, measured on this machine (Python 3.12.10, CPU-only, no GPU) as
part of Phase 5 hardening. Method and full commands are in
[`.build/iter-5/test-results.md`](.build/iter-5/test-results.md); the
measurement script is [`scripts/measure_latency.py`](scripts/measure_latency.py).

### Latency (AC-3)

Measured against the real running app (in-process Flask test client, same
request path a live server takes — no mocking). The **first** request in a
process pays a one-time model-load cost (embedder/reranker/Phi-4 are
`lru_cache`-lazy); cold and warm numbers are reported separately so neither is
mistaken for the other.

| Request class | Cold (first call) | Warm (median of 3) | PRD target | Meets target? |
|---|---|---|---|---|
| FAQ Tier-1 hit | 11.7s (model load) | **0.017s** | < 1s (p50) | ✅ yes |
| Exact-match cache hit (Tier-2) | 26.7s (that call was a cache-populating miss, not a hit) | **0.025s** | — | — |
| Fresh generation (retrieve → generate, CPU) | — | **14.7s – 30.4s** (median 17.7s) | 10–60s | ✅ yes |

Both FAQ and cache hits are effectively instant once warm (single-digit
milliseconds) — the ~1s target is cleared by roughly two orders of magnitude.
Fresh generation lands inside the PRD's 10–60s CPU band; the high end (~30s)
occurred on a longer, multi-part question and is reported honestly rather than
only showing the best case.

### Retrieval & orchestration eval (AC-6)

Re-run 2026-07-23 against a freshly rebuilt **402-chunk** corpus (25-item gold
set, `data/eval/gold.jsonl`), `python -m scripts.eval` / `--compare`:

| Config | hit@5 | term_recall |
|---|---|---|
| `ORCHESTRATION=false` (single default mode=naive) | 1.00 | 0.92 |
| `ORCHESTRATION=true` (per-intent routing, **shipped default**) | 1.00 | 1.00 |
| Delta (on − off) | **+0.00** | **+0.08** |

> **Note — corpus is rebuilt live, so numbers move.** The index is built from
> the eCFR + Federal Register APIs at run/build time and is never committed, so
> its exact size tracks whatever those APIs return. This run indexed 402 chunks
> vs. the 475 recorded in [CHANGELOG](CHANGELOG.md) Phase 3. On this corpus the
> earlier `hit@5` gap on FinCEN's 2022 beneficial-ownership final rule (doc
> `2022-21020`) is **gone** — that document is indexed and now retrieves at rank
> 4 for both gold questions, so `hit@5` is a perfect 1.00 for both configs.
> Orchestration's measured win here is on `term_recall` (+0.08).

**`ORCHESTRATION` now ships on by default.** On the current corpus `hit@5` is
already saturated, and orchestration's per-intent routing still adds a real
`term_recall` gain (1.00 vs 0.92, +0.08); the AC-3 fresh-generation latency
(median ~18s) leaves headroom inside the 10–60s CPU band even with the extra
frame→classify→route→verify step. So the default was flipped to
`ORCHESTRATION=true` (config default in `src/rag/config.py`). It is a fully
reversible env-var change — set `ORCHESTRATION=false` to fall back to the
single-mode iter-2 path (which still collapses to the byte-identical iter-2
behavior when `FAQ_CACHE=false` as well, per AC-2).

### hybrid_rerank (measured in iteration 1, unchanged this release)

`hybrid_rerank` was added because the expanded gold set exposed a real hybrid
(BM25+dense RRF) ranking regression — near-synonym eCFR sections outranking
the controlling one. The cross-encoder rerank fixes every regressed case
(avg rank 1.12 vs. hybrid's 1.28, naive's 1.44); `naive` still ships as the
default per the project's "ties → simplest mode wins" rule. Full numbers in
CHANGELOG's Iteration 1 entry.

---

## Screenshots (Cognitus UI)

The front end (`src/app/static/`) is restyled with the **Cognitus** design
system — Jefferson-Blue structural color, Bronze eyebrow kickers / source
badges, a single Cyan accent (streaming caret), hairline rules, no
shadows/gradients. See [`docs/UIUX_COGNITUS.md`](docs/UIUX_COGNITUS.md) for
the full design spec.

> **Note (re-verified 2026-07-23 against the running Docker container, pixel
> capture still deferred):** the UI was re-checked live at `http://localhost:8001`
> (containerized app). The accessibility-tree and page-text snapshots confirm
> correct rendering end to end: the Cognitus banner + health dot, hero (eyebrow
> "AML / KYC · RAG", heading, subtitle), the corpus-status strip (`Corpus as of
> 2026-07-21`, sections indexed, `Sources: ecfr · fedreg_proposed · fedreg_rule
> · fincen_advisory`), the ask form, a populated **Answer** ("...more than
> $10,000 (31 CFR 1010.311)") with the **from FAQ** marker, the **Citations**
> panel (`31 CFR 1010.311`, View source, `as of: 2026-06-30`), and the footer
> disclaimer. No console errors. Pixel PNG capture still could not be produced:
> the headless browser pane does not composite frames, so the screenshot call
> times out — the same tooling limitation seen before, not a page defect. (One
> visible side effect of that same limitation: the corpus-count animation, which
> uses `requestAnimationFrame`, does not tick in the non-displayed pane and reads
> `0`; setting it directly yields `402`, confirming it animates normally in a
> real, displayed browser.) To capture the three screenshots manually, run the
> container (`docker compose -f docker/docker-compose.yml up --build`) or
> `python -m src.app.asgi`, then visit the app in a normal browser.

---

## Why this project (portfolio note)

AML/KYC is one of the largest, most durable spend and hiring areas inside banks —
exactly the institutions this work targets. This build demonstrates, end to end:
modern **RAG engineering** (hybrid + graph retrieval, reranking, citations),
**data engineering** (event-driven incremental ETL against live government APIs),
**applied LLM orchestration** (intent routing and answer verification on a local
model), and **product/design** sensibility (a coherent, branded UX). It is
deliberately reproducible on a laptop so the engineering — not a cloud bill —
carries the story.

---

## License & attribution

- **31 CFR / Federal Register / FFIEC manual text** are U.S. Government works in
  the public domain.
- **Phi-4-mini-instruct-onnx** (Microsoft) and **embedding/reranker models**
  (HuggingFace) are downloaded at build time under their own licenses; not
  redistributed here.
- Project code released under the **MIT License** (see `LICENSE` once code lands).
