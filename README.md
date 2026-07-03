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

✅ **Phase 0–4 complete.** Implemented and tested:
- **Phase 0:** eCFR loader, naive retrieval, generation, Flask+SSE app.
- **Phase 1:** Multi-mode retrieval backbone, FinCEN Federal Register corpus, section-aware chunking, exact-match answer cache.
- **Phase 2:** Trigger-based ETL (watchers for FedReg + eCFR, rules engine R1–R4, incremental upsert-by-citation, provenance ledger).
- **Phase 3:** Local orchestration layer (query framing, intent classification, retrieval routing) + semantic FAQ cache (Tier-1, 29 curated entries). Orchestration OFF by default pending latency-inclusive measurement; FAQ cache ON by default.
- **Phase 4:** Cognitus design system UI: Jefferson-Blue structural color, Bronze eyebrow kickers / source badges, Cyan streaming caret accent, hairline rules. All interaction states rendered (streaming, citations, verifier-decline, FAQ-hit marker). Three new static-asset routes for `cognitus.css`, `cognitus.js`, `app.js`.

See [CHANGELOG](CHANGELOG.md) for per-iteration details. Phase 5 (CI/Docker/testing infra) follows the [roadmap](docs/ROADMAP.md).

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

## Screenshots (Cognitus UI)

The front end (`src/app/static/`) is restyled with the **Cognitus** design
system — Jefferson-Blue structural color, Bronze eyebrow kickers / source
badges, a single Cyan accent (streaming caret), hairline rules, no
shadows/gradients. See [`docs/UIUX_COGNITUS.md`](docs/UIUX_COGNITUS.md) for
the full design spec.

> **Note:** the three required screenshots (landing/hero + corpus-status
> strip, answer + citation panel at desktop and mobile widths, and the
> verifier-decline state) could not be captured as image files in the
> environment this iteration was built in — the available headless-preview
> tooling's screenshot capture consistently failed while the page itself
> loaded and ran correctly (confirmed via DOM/computed-style inspection and
> a live end-to-end `/chat_stream` exchange). No placeholder images have
> been added. See `.build/iter-4/changes.md` for the verification that was
> performed in place of pixel screenshots, and capture these three
> screenshots manually (open `python -m src.app.asgi` and visit
> `http://127.0.0.1:8000/`) before/at the next opportunity.

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
