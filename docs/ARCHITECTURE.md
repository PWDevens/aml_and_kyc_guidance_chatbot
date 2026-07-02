# Architecture — AML/KYC RAG Chatbot

**Status:** Draft v1 · **Last updated:** 2026-06-25

This document describes the target system. It mirrors the proven
[`fedacq-rag-chatbot`](https://github.com/PWDevens/fedacq-rag-chatbot) design and
adds the four AML/KYC-specific deviations. Where a component is unchanged from
fedacq it is marked **(reused)**; new components are marked **(new)**.

---

## 1. Design principles

1. **Local-first.** CPU-only inference (ONNX Phi-4-mini), on-disk ChromaDB, no
   external LLM API at runtime. Reproducible on a 16 GB laptop. **(reused)**
2. **One serving path.** Every retrieval mode returns `(context, citations)`; the
   cache, generation, and citation-streaming code is written once. **(reused)**
3. **Citation-or-nothing.** Factual claims must trace to retrieved primary-source
   text; the verification skill enforces this. **(new)**
4. **Currency by trigger, not by rebuild.** The corpus updates incrementally when
   FinCEN/eCFR change, not on a manual full re-index. **(new)**
5. **Config over code.** Retrieval mode, reranking, ETL cadence, agent toggles —
   all driven by environment variables. **(reused + extended)**

---

## 2. Component map

```
src/
├── app/                      # Flask + SSE serving + Cognitus static UI   (reused, restyled)
├── rag/
│   ├── config.py             # RagConfig + env vars                        (reused)
│   ├── cache.py              # exact-match answer cache (SQLite)           (reused)
│   ├── faq/                  # semantic FAQ fast-path                       (new)
│   ├── orchestration/        # planner + skills (intent, route, verify)    (new)
│   ├── indexing/             # builder + loaders (multi-source)            (reused, extended)
│   ├── llm/                  # ONNX Phi-4-mini wrapper                      (reused)
│   └── retrieval/            # factory: naive | hybrid | graph + reranker  (reused)
├── etl/                      # trigger-based ETL (FedReg + eCFR watchers)  (new)
└── scripts/                  # build_index, build_graph, seed_faq, etl_run (reused + new)
```

---

## 3. Query (online) path

```
POST /chat_stream  { "question": ... }
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR  (src/rag/orchestration)                       │
│  1. frame_query     normalize, expand acronyms (CTR, CDD…)  │
│  2. classify_intent definitional | numeric | procedural |   │
│                     change | citation-lookup                │
│  3. route           choose RAG_MODE + rerank knobs by intent│
└───────┬─────────────────────────────────┬───────────────────┘
        │ FAQ semantic match (≥ threshold) │ otherwise
        ▼                                  ▼
  FAQ fast-path                     ┌──────────────────────────┐
  cached answer + citations         │ RETRIEVAL FACTORY        │
  (sub-second)                      │  naive  : dense (Chroma) │
        │                           │  hybrid : dense+BM25 RRF │
        │                           │  graph  : LightRAG KG    │
        │                           │  + cross-encoder rerank  │
        │                           └─────────┬────────────────┘
        │                                     │ (context, citations)
        │                                     ▼
        │                           ┌──────────────────────────┐
        │                           │ GENERATE  Phi-4-mini ONNX│
        │                           └─────────┬────────────────┘
        │                                     ▼
        │                           ┌──────────────────────────┐
        │                           │ VERIFY skill: claims ⊆   │
        │                           │ retrieved context?       │
        │                           │  → annotate / down-weight│
        │                           └─────────┬────────────────┘
        ▼                                     ▼
        └──────────────▶  SSE stream: tokens + citation event + as_of stamp
                                              │
                                              ▼
                                   Cognitus UI (citation panel)
```

Like fedacq, **all retrieval modes share the generation + citation path**. The two
additions wrap it: the **FAQ fast-path** can short-circuit before retrieval, and
the **verification skill** gates output after generation.

---

## 4. Retrieval modes (`RAG_MODE`) — reused from fedacq

| Mode | What it does | AML/KYC fit |
|------|--------------|-------------|
| `naive` | Dense vector search over ChromaDB | Baseline; conceptual questions |
| `hybrid` | Dense + BM25 fused with Reciprocal Rank Fusion | **Strong default** — exact-term matches on clause numbers, defined terms, dollar thresholds (e.g., "$10,000", "31 CFR 1010.311") that pure embeddings miss |
| `graph` | GraphRAG via LightRAG over an entity/relation graph | Cross-referenced obligations (e.g., how CIP, CDD, and beneficial-ownership rules interrelate) |

The **cross-encoder reranker** (`RERANK=true`) pulls a larger candidate pool
(`RETRIEVAL_TOP_K`) and re-scores to `RERANK_TOP_N`, improving both injected
context and citations. Defaults inherited from fedacq.

**Why hybrid is the default here:** AML/KYC queries are unusually
identifier-dense — citation numbers, dollar thresholds, defined terms of art.
BM25's exact-term recall materially complements dense retrieval for this corpus.

---

## 5. Generation & embeddings — reused

| Element | Choice | Notes |
|---------|--------|-------|
| LLM | `microsoft/Phi-4-mini-instruct-onnx` (int4, CPU) | Fast on CPU, no API, small footprint |
| Embeddings | `BAAI/bge-small-en-v1.5` | Must match index build; swappable via `EMBED_MODEL_NAME` |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Small, CPU |
| Vector store | ChromaDB (on-disk, Git LFS-committed) | Runtime copy avoids dirtying LFS index |
| Orchestration lib | LlamaIndex | Retrieval + query-engine plumbing |
| Chunking | `SentenceSplitter` | Tune for regulatory structure (see §7) |

The local model is sufficient because **the orchestration does the hard
reasoning** (routing, verification) with small, well-scoped prompts rather than
relying on one giant generation. See [`AGENT_ORCHESTRATION.md`](AGENT_ORCHESTRATION.md).

---

## 6. Offline pipelines

- **Trigger-based ETL** (`src/etl`, `scripts/etl_run.py`) — watches FinCEN's
  Federal Register feed and eCFR change endpoints; incrementally parses, chunks,
  embeds, and upserts only changed material. Full spec:
  [`ETL_AND_TRIGGERS.md`](ETL_AND_TRIGGERS.md). **(new)**
- **Index build** (`scripts/build_index.py`) — initial full build of the corpus
  into ChromaDB. **(reused, multi-source loaders)**
- **Graph build** (`scripts/build_graph.py` / `_gpu.py`) — LightRAG entity/relation
  extraction over a seeded subset; GPU-accelerated build, CPU-served. **(reused)**
- **FAQ seed/refresh** (`scripts/seed_faq.py`) — builds the semantic FAQ cache from
  curated common questions + FinCEN FAQs; refreshed when the corpus changes. Full
  spec: [`FAQ_CACHE.md`](FAQ_CACHE.md). **(new)**

---

## 7. Corpus modeling & metadata

Each source is parsed to a normalized document with retrieval-friendly metadata:

| Field | Example | Purpose |
|-------|---------|---------|
| `source` | `ecfr` / `fedreg` / `ffiec` / `fincen_advisory` | Provenance + UI badges |
| `citation` | `31 CFR 1010.311` | Inline citation + click-through |
| `title` / `chapter` / `part` / `section` | `31 / X / 1010 / 1010.311` | Filtering, graph keys |
| `as_of` | `2026-06-15` | Currency stamp (from eCFR `up_to_date_as_of`) |
| `fedreg_doc_number` / `publication_date` | `2024-12345`, `2024-09-15` | "What changed" answers |
| `url` | canonical eCFR/FedReg/FFIEC URL | Source link in citation panel |

**Chunking note:** regulatory text is hierarchical (part → subpart → section →
paragraph). The chunker should respect section/paragraph boundaries so a chunk
maps cleanly to a citable unit, rather than splitting mid-clause. This is a
deviation in *tuning* from fedacq's DITA parser, adapted to eCFR XML structure.

---

## 8. Application layer — reused, restyled

- Flask app (`src.app`), served as ASGI via Hypercorn (Docker/Linux/macOS) or the
  Flask dev server (Windows).
- `POST /chat_stream` — token streaming via Server-Sent Events; final citation
  event; `as_of` currency stamp.
- `GET /healthz`, `GET /corpus_status` (new) — surfaces corpus `as_of` + last ETL run.
- Static UI from `src/app/static/`, **restyled with the Cognitus design system**
  (see [`UIUX_COGNITUS.md`](UIUX_COGNITUS.md)).

### Configuration (environment variables)

Inherits the fedacq variable set (`RAG_MODE`, `RERANK`, `RETRIEVAL_TOP_K`,
`RERANK_TOP_N`, `MAX_NEW_TOKENS`, `ANSWER_CACHE`, `CHROMA_PATH`, `PHI4_MODEL_DIR`,
`EMBED_MODEL_NAME`, `LIGHTRAG_WORKING_DIR`, …) and adds:

| Variable | Default | Purpose |
|----------|---------|---------|
| `ORCHESTRATION` | `true` | Enable planner/skills layer (off = fedacq-style single path) |
| `FAQ_CACHE` | `true` | Enable semantic FAQ fast-path |
| `FAQ_SIM_THRESHOLD` | `0.92` | Cosine threshold for an FAQ hit |
| `VERIFY_ANSWERS` | `true` | Enable post-generation grounding check |
| `ETL_SCHEDULE` | `daily` | Trigger cadence for the ETL watcher |
| `FEDREG_AGENCY` | `financial-crimes-enforcement-network` | FinCEN agency slug |
| `ECFR_TITLE` / `ECFR_CHAPTER` | `31` / `X` | Watched corpus scope |

---

## 9. Deployment — reused

- Local Python env or Docker Compose (Hypercorn ASGI).
- Model + index mounted read-only into the container; image stays small.
- GitHub Actions CI: LFS checkout, deps, tests, Docker build/upload. CI does **not**
  rebuild the index (cost/size) — index is built locally + ETL-maintained and
  versioned via Git LFS.

---

## 10. Repository structure (target)

```
aml-kyc-rag-chatbot/
├── src/
│   ├── app/
│   │   ├── api.py
│   │   ├── asgi.py
│   │   ├── config.py
│   │   └── static/            # Cognitus-styled UI (index.html, app.js, cognitus.css …)
│   ├── rag/
│   │   ├── config.py
│   │   ├── cache.py
│   │   ├── faq/               # (new) semantic FAQ cache
│   │   │   ├── store.py
│   │   │   └── matcher.py
│   │   ├── orchestration/     # (new) planner + skills
│   │   │   ├── planner.py
│   │   │   ├── intents.py
│   │   │   ├── router.py
│   │   │   └── verify.py
│   │   ├── indexing/
│   │   │   ├── builder.py
│   │   │   └── loaders/       # ecfr.py, fedreg.py, ffiec.py, fincen.py
│   │   ├── llm/models.py
│   │   └── retrieval/
│   │       ├── factory.py
│   │       ├── reranker.py
│   │       ├── graph_lightrag.py
│   │       ├── metadata.py
│   │       └── query_engine.py
│   ├── etl/                   # (new) trigger-based ETL
│   │   ├── watchers/          # fedreg.py, ecfr.py
│   │   ├── rules.py           # trigger rules
│   │   ├── pipeline.py        # parse → chunk → embed → upsert
│   │   └── state.py           # watermarks / provenance ledger
│   └── scripts/
│       ├── build_index.py
│       ├── build_graph.py
│       ├── build_graph_gpu.py
│       ├── seed_faq.py
│       └── etl_run.py
├── data/
│   ├── chroma/                # committed index (Git LFS)
│   ├── chroma_runtime/        # writable runtime copy (gitignored)
│   ├── lightrag/              # graph artifacts
│   ├── faq.db                 # FAQ cache (gitignored or committed seed)
│   ├── cache.db               # answer cache (gitignored)
│   ├── etl_state.db           # ETL watermarks + provenance
│   └── corpus/                # raw pulled sources (ecfr/, fedreg/, ffiec/)
├── tests/
├── docker/
├── docs/                      # this plan
├── Dockerfile · Makefile · pyproject.toml · requirements*.txt
└── README.md
```

This intentionally tracks fedacq's layout so the two projects read as a coherent
body of work, with `etl/`, `orchestration/`, and `faq/` as the visible new surface.
