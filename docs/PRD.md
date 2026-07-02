# PRD — AML/KYC RAG Chatbot

**Status:** Draft v1 · **Owner:** Patrick W. Devens · **Last updated:** 2026-06-25

---

## 1. Problem

Bank Secrecy Act / AML / KYC obligations are large, fragmented, and constantly
moving. The in-force rules live in **31 CFR Chapter X**; the change stream lives in
the **Federal Register** (FinCEN rulemakings, advisories); practical interpretation
lives in the **FFIEC BSA/AML Examination Manual**; and edge cases live in **FinCEN
advisories and FAQs**. Compliance analysts, BSA officers, onboarding/QC teams, and
auditors spend hours cross-referencing these to answer recurring questions —
*"What's the CTR aggregation rule for multiple same-day transactions?"*, *"When is
a beneficial-ownership refresh required?"*, *"What changed in the latest FinCEN
rule on X?"* — and getting it wrong carries regulatory and financial risk.

A general-purpose LLM answers these confidently but **without citations and
without currency**, which is unusable in a regulated function. This project closes
that gap with retrieval grounded in primary sources, inline citations, and an ETL
pipeline that keeps the corpus current as FinCEN publishes.

## 2. Target users

| Persona | Need | Primary query types |
|---------|------|---------------------|
| **BSA/AML analyst** | Fast, citation-backed answers during case work | Definitional, threshold/numeric, procedural |
| **Compliance officer / BSA officer** | Defensible references for policy and exams | Regulatory-citation, "what changed" |
| **Onboarding / KYC / CDD reviewer** | CIP/CDD/beneficial-ownership requirements | Procedural, applicability |
| **Internal audit / QC** | Trace an answer back to authoritative text | Citation, cross-reference |
| **(Portfolio) hiring reviewers** | Evidence of RAG + data-eng + LLM-orchestration skill | n/a — they read the repo |

## 3. User stories

> **Primary:** *As a BSA/AML compliance professional, I need quick, accurate,
> citation-backed answers about U.S. AML/KYC requirements so I can make defensible
> decisions and respond to examiners without manually searching thousands of pages.*

Supporting stories:

- *As an analyst*, I ask a question in plain English and get an answer with inline
  citations to the exact 31 CFR section / FFIEC manual passage / FinCEN advisory.
- *As a BSA officer*, I ask "what changed" about a topic and the system tells me
  which recent Federal Register actions touched it, with dates and links.
- *As a KYC reviewer*, I ask a procedural question (CIP/CDD/beneficial ownership)
  and get a step-grounded answer pointing at the governing rule.
- *As an auditor*, every answer lets me click through to the underlying source so
  I can verify it independently.
- *As the maintainer*, the corpus updates itself when FinCEN publishes — I don't
  hand-rebuild the index.

## 4. Scope

### In scope (v1 → v1.x)
- Natural-language Q&A over the four-source corpus (§Knowledge base in README).
- Inline, clickable citations to primary sources with section/part identifiers.
- Selectable retrieval (`naive` / `hybrid` / `graph`) + cross-encoder reranker.
- Trigger-based incremental ETL keyed off FinCEN Federal Register + eCFR changes.
- Agent/skill orchestration: query framing, intent classification, retrieval-mode
  routing, answer verification against retrieved text.
- Semantic FAQ cache for common questions.
- Cognitus-styled web UI with streaming responses and a citation panel.
- Local-first: CPU-only, no external LLM API, Dockerized.

### Out of scope (v1)
- Filing/decisioning (no SAR/CTR generation, no case-management writes).
- Access to a financial institution's internal policies or customer data.
- Authoritative legal interpretation — research aid only.
- Multi-jurisdiction / FATF / non-US regimes (candidate for a later version).
- Real-time transaction monitoring.

## 5. Acceptance criteria

- [ ] Natural-language question interface (web UI + HTTP endpoint).
- [ ] Retrieval of relevant 31 CFR / FFIEC / FinCEN passages for a question.
- [ ] Accurate, **citation-backed** responses (section-level identifiers).
- [ ] **Currency:** corpus reflects FinCEN/eCFR changes within the ETL SLA
      (default: next scheduled run after publication; see ETL doc).
- [ ] **Provenance:** every chunk carries source, citation, and `as_of` version.
- [ ] Reproducible end-to-end pipeline; deployable locally and via Docker.
- [ ] Answer-verification step flags answers not supported by retrieved context.
- [ ] FAQ fast-path returns a cached answer for seeded common questions in <1 s.
- [ ] Visible, persistent compliance disclaimer in UI and API responses.

## 6. Non-functional requirements

| Area | Target |
|------|--------|
| **Hardware** | CPU-only; 16 GB RAM laptop floor (mirrors fedacq) |
| **Latency** | Cache/FAQ hit < 1 s; fresh generation 10–60 s on CPU |
| **Currency (ETL SLA)** | Detect + ingest new FinCEN/eCFR changes on the next scheduled trigger run (configurable; default daily) |
| **Reproducibility** | Pinned deps (`requirements.lock`); committed index via Git LFS; deterministic build scripts |
| **Privacy** | No PII ingested; no user-query logging beyond opt-in eval set; fully offline at inference |
| **Traceability** | 100% of factual claims map to a retrieved, cited source |

## 7. Compliance & disclaimers

This is a **research and reference aid**, not legal or compliance advice, and not a
regulated system of record. Specific guardrails baked into the product:

1. **Persistent disclaimer** in the UI footer and in every API/SSE response payload.
2. **Citation-or-refuse:** the answer-verification skill suppresses/labels claims
   not grounded in retrieved text rather than letting the model free-generate.
3. **Currency stamp:** answers display the corpus `as_of` date so users know how
   fresh the underlying text is.
4. **No decisioning:** the system never recommends filing/not-filing a SAR/CTR or
   making a customer-risk determination; it surfaces the governing text.
5. **Public-domain sourcing only:** no proprietary or institution-internal data.

## 8. Success metrics

| Metric | How measured | Target |
|--------|--------------|--------|
| **Retrieval relevance** | Hit-rate / MRR on a curated AML/KYC eval Q&A set | Establish baseline → beat naive with hybrid+rerank |
| **Citation faithfulness** | % answers whose claims trace to cited text (manual + automated check) | ≥ 95% |
| **Currency lag** | Time from FinCEN publication → reflected in corpus | ≤ 1 ETL cycle |
| **FAQ hit latency** | p50 latency on seeded FAQ questions | < 1 s |
| **Cache hit rate** | Share of traffic served from FAQ/answer cache | Track; optimize seed set |
| **Portfolio signal** | Repo readability, test coverage, demo quality | Reviewer-ready |

## 9. Open questions / decisions log

- **Graph corpus subset:** which Part(s) of 31 CFR X to seed the GraphRAG build
  first (candidate: CDD / beneficial-ownership cluster). → ARCHITECTURE/ROADMAP.
- **FFIEC manual format:** confirm best machine-readable source for the exam
  manual sections. → ETL doc, Phase 2.
- **Eval set authorship:** assemble ~50–100 gold Q&A pairs with known citations.
  → ROADMAP, Phase 1.
