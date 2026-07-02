# Roadmap — AML/KYC RAG Chatbot

**Status:** Draft v1 · **Last updated:** 2026-06-25

End-to-end build plan. Following `fedacq-rag-chatbot`'s convention, each phase ends
in a **browsable tagged snapshot**, so the project reads as a deliberate
progression and every stage is demoable.

---

## 1. Phasing overview (Now / Next / Later)

| Horizon | Phases | Theme |
|---------|--------|-------|
| **Now** | 0–1 | Stand up a citation-backed baseline over the AML/KYC corpus |
| **Next** | 2–3 | The differentiators: trigger-based ETL, orchestration, FAQ cache |
| **Later** | 4–5 | Cognitus UX, hardening, demo polish; optional stretch scope |

---

## 2. Phases

### Phase 0 — Foundation & corpus spike  → tag `v0.1-baseline`
**Build:** repo scaffold (mirroring fedacq); eCFR 31 CFR Chapter X loader; initial
full `build_index.py` over the eCFR snapshot; reuse retrieval factory (`naive`),
Phi-4 ONNX serving, SSE endpoint; minimal UI.
**Also:** assemble the **gold eval set** (~50–100 Q&A pairs with known citations).
**Exit criteria:** ask a question, get a citation-backed answer from 31 CFR X;
`naive` baseline measured on the eval set; runs locally + Docker.

### Phase 1 — Multi-mode retrieval + corpus breadth  → tag `v0.2-multimode`
**Build:** `hybrid` (dense + BM25 RRF) and `graph` (LightRAG) modes + cross-encoder
reranker (all reused from fedacq); add FedReg FinCEN documents and FinCEN advisories
to the corpus as static loaders; section-aware chunking tuned to eCFR XML;
exact-match answer cache (reused).
**Exit criteria:** `RAG_MODE` switchable; hybrid+rerank beats naive on the eval
set; citations resolve to correct sections.

### Phase 2 — Trigger-based ETL (Deviation 1)  → tag `v0.3-live-etl`
**Build:** `src/etl` watchers (FedReg + eCFR), rules engine R1–R4, incremental
upsert-by-citation, watermark + provenance ledger (`etl_state.db`), version history,
`GET /corpus_status`; scheduled GitHub Action that auto-PRs a refreshed LFS index.
**Exit criteria:** a simulated/real FinCEN change is detected and ingested
incrementally; `as_of` advances; provenance ledger explains every change;
re-runs are idempotent. *(See [`ETL_AND_TRIGGERS.md`](ETL_AND_TRIGGERS.md).)*

### Phase 3 — Orchestration + FAQ cache (Deviations 2 & 3)  → tag `v0.4-orchestrated`
**Build:** planner + skills (`query_framer`, `intent_classifier`,
`retrieval_router`, `answer_verifier`, `citation_formatter`, `change_resolver`);
routing matrix; **semantic FAQ cache** (Tier 1) with staleness invalidation tied to
ETL rule R5; FFIEC manual ingest (R7); graph re-sync (R6).
**Exit criteria:** orchestration-on beats orchestration-off on retrieval relevance
+ citation faithfulness; verifier declines on ungrounded questions; FAQ hits return
< 1 s; stale FAQs auto-suppress. *(See
[`AGENT_ORCHESTRATION.md`](AGENT_ORCHESTRATION.md), [`FAQ_CACHE.md`](FAQ_CACHE.md).)*

### Phase 4 — Cognitus UI/UX (Deviation 4)  → tag `v0.5-cognitus-ui`
**Build:** graft `cognitus.css`/`cognitus.js`; rebuild landing + chat + citation
panel + corpus-status strip + "what changed" timeline + persistent disclaimer;
accessibility pass; README screenshots.
**Exit criteria:** UI matches Cognitus tokens; WCAG AA contrast/keyboard/responsive
verified; demo-ready. *(See [`UIUX_COGNITUS.md`](UIUX_COGNITUS.md).)*

### Phase 5 — Hardening & release  → tag `v1.0`
**Build:** full test suite + CI green; latency profiling + tuning; docs finalized
(`README`, runbook, eval results); reproducibility check on a clean machine;
disclaimer/guardrail review.
**Exit criteria:** all PRD acceptance criteria met; CI builds + tests + Docker
artifact; one-command run; eval results published in the README.

### Phase 6 — Stretch (optional, post-v1)
Multi-jurisdiction / FATF scope · feedback-loop FAQ growth from near-miss logs ·
LlamaIndex `QueryPipeline` refactor of the planner · optional remote ChromaDB for
scale · evaluation dashboard.

---

## 3. Milestone ↔ deliverable matrix

| Phase | Tag | Headline deliverable | Maps to doc |
|-------|-----|----------------------|-------------|
| 0 | `v0.1-baseline` | Citation-backed naive RAG over 31 CFR X + eval set | ARCHITECTURE, PRD |
| 1 | `v0.2-multimode` | Hybrid/graph + rerank; FedReg/advisory corpus | ARCHITECTURE |
| 2 | `v0.3-live-etl` | Self-updating corpus from FinCEN/eCFR triggers | ETL_AND_TRIGGERS |
| 3 | `v0.4-orchestrated` | Planner/skills + semantic FAQ cache | AGENT_ORCHESTRATION, FAQ_CACHE |
| 4 | `v0.5-cognitus-ui` | Cognitus-styled UX | UIUX_COGNITUS |
| 5 | `v1.0` | Hardened, tested, documented release | all |

---

## 4. Testing & CI strategy

- **Unit:** loaders/parsers, metadata normalization, retrieval factory dispatch,
  RRF, reranker, ETL rules R1–R8, each orchestration skill, FAQ matcher.
- **Integration:** end-to-end `/chat_stream`; ETL run against recorded API
  fixtures; FAQ staleness on simulated corpus change.
- **Eval harness:** gold Q&A set → retrieval relevance (hit-rate/MRR) + citation
  faithfulness; run per phase to show measured improvement (mirrors how a strong
  portfolio project quantifies its gains).
- **CI (GitHub Actions):** LFS checkout, deps, tests, Docker build/upload — CI does
  **not** rebuild the index (cost/size), matching fedacq. Add the **scheduled ETL
  workflow** (Phase 2) as a separate Action.
- **Model-gated tests:** Phi-4-dependent tests skipped unless `ENABLE_PHI4_TESTS=1`
  (reused convention).

---

## 5. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Source API/schema change (FedReg/eCFR) | Med | High | Adapter loaders + recorded fixtures; validation gate; alert-on-failure (R8) |
| Local model too weak for some answers | Med | Med | Orchestration uses small scoped prompts; verifier declines rather than hallucinate; hybrid stance remains a config option |
| Wrong cached FAQ served | Low | High | High similarity threshold + topic-key cross-check + stale-suppress (FAQ §3–4) |
| Graph build cost on CPU | Med | Med | GPU build / CPU serve (reused); seed a small subset first |
| Currency expectations vs. SLA | Low | Med | Visible `as_of` stamp; documented ETL cadence; `/corpus_status` |
| Scope creep (multi-jurisdiction) | Med | Med | Explicitly out of v1 (PRD §4); parked in Phase 6 |
| **Compliance misread as advice** | Med | High | Persistent disclaimer (UI + API), citation-or-refuse, no decisioning (PRD §7) |

---

## 6. Definition of done (v1)

- All PRD §5 acceptance criteria checked.
- Hybrid+rerank and orchestration show **measured** gains over baseline on the eval
  set, published in the README.
- ETL demonstrably keeps the corpus current with provenance.
- FAQ fast-path < 1 s; verifier declines on ungrounded queries.
- Cognitus UI demo-ready with screenshots.
- Clean-machine reproducibility; CI green; one-command run.

---

## 7. Suggested sequencing notes

- **Land the eval set in Phase 0.** Every later phase justifies itself with numbers
  against it — this is the difference between "I built a RAG app" and "I improved
  retrieval relevance X→Y and citation faithfulness to Z%."
- **Tag every phase.** The browsable progression is itself a portfolio asset.
- **Phase 2 (live ETL) is the signature differentiator** — it is the clearest
  evidence of data-engineering depth beyond a standard RAG demo. Prioritize a clean,
  visible auto-update story (the scheduled-Action auto-PR).
