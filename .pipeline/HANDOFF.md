# Session Handoff — AML/KYC RAG Chatbot

**Purpose:** full context for starting a fresh Claude Code session. Read this first,
then `.pipeline/STATUS.md` (the loop log) and `docs/` (the plan).
**Last updated:** 2026-06-30 · **State:** Phase 0 built & verified; one eval iteration done.

---

## 0b. Machine migration (old laptop → Alienware Aurora, RTX 5070 8GB / 64GB RAM)

**Decision:** CPU-only stays the **default serving path** (local-first is the product's
identity). The GPU is used only to **accelerate offline builds** (index, eval, LightRAG
graph) — this is the documented "GPU build, CPU serve" pattern and removes the prior
**Runpod dependency** (nothing here needs >8 GB VRAM; Phi-4-mini int4 is ~2 GB).

**What the project folder contains:** all code, docs, gold set, `.pipeline/`, and a small
rebuildable Chroma index. **NOT in the folder:** the ~2 GB models (Phi-4, bge-small,
cross-encoder) — they live in the HF cache and re-download on first run. Deps are in
`requirements.txt` (includes `rank-bm25`, `numpy`).

**Bring-up on the new machine:**
```
git clone <repo>  C:\dev\aml-kyc-rag-chatbot   # clone OUTSIDE OneDrive (avoids .git sync conflicts)
cd C:\dev\aml-kyc-rag-chatbot
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
pip install onnxruntime-genai-cuda             # GPU build; CPU wheel still works if this is fiddly
python -m scripts.build_index                  # rebuilds index from eCFR (seconds)
python -m scripts.eval                          # expect naive hit@5 = 1.00
python -m src.app.asgi                          # http://127.0.0.1:8000
```
⚠️ RTX 5070 is Blackwell — GPU generation needs recent CUDA 12.x + a current
`onnxruntime-genai-cuda` wheel. If it errors, it's a wheel/CUDA mismatch, not the code;
the CPU path is unaffected.

## 0. How to resume in a new session

Open a session in `C:\Users\pwdev\OneDrive\Documents\anaconda_projects\aml-kyc-rag-chatbot`
and paste something like:

> Read `.pipeline/HANDOFF.md`, `.pipeline/STATUS.md`, and `docs/ROADMAP.md`, then continue
> the build loop. Stay in ponytail mode (lazy = efficient, shortest working diff).

Everything needed to run is local/offline (models cached, see §4). The build loop and the
6 roles are described in §2.

---

## 1. What this project is

A **fully local, CPU-only RAG chatbot** answering U.S. AML/KYC regulatory questions
(Bank Secrecy Act / 31 CFR Chapter X, FinCEN, FFIEC) with **citation-backed** answers.
Sibling of `fedacq-rag-chatbot`, reusing its local-first architecture. Four deviations:
trigger-based ETL, agent orchestration, semantic FAQ cache, Cognitus UI. Not legal advice.

Full plan in `docs/`: `PRD.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `ETL_AND_TRIGGERS.md`,
`AGENT_ORCHESTRATION.md`, `FAQ_CACHE.md`, `UIUX_COGNITUS.md`.

---

## 2. The build loop (6 roles)

A loop driven by a PM, with a domain SME closing the feedback cycle. Roles map to
**artifacts, not ceremony** — no separate agents are spawned for them:

| # | Role | Output / artifact |
|---|------|-------------------|
| 1 | PM | `docs/PRD.md` + big-picture plans / recommendations |
| 2 | Dev Manager | `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` |
| 3 | Sr. Dev | `src/**` code |
| 4 | Tester | `tests/**`, `scripts/eval.py`, live runs |
| 5 | Distributed Systems Eng | `.pipeline/DEPLOYMENTIDEAS.md` (SaaS hosting + cost scope) |
| 6 | **AML & KYC SME** | line-by-line review of live answers for regulatory correctness → feedback to PM → restart |

> **Role-6 change (this session):** originally "Federal GovCon BD SME"; user replaced it
> with an **AML & KYC SME** (domain-correctness reviewer).

**Operating mode:** ponytail (lazy senior dev) — YAGNI, stdlib/installed-deps first,
shortest working diff, simplifications marked with `# ponytail:` comments, every
non-trivial change leaves one runnable check. Don't adopt complexity without a measured win.

---

## 3. Roadmap phases (target progression)

- **Phase 0** `v0.1-baseline` — citation-backed naive RAG over 31 CFR X + eval set. **← DONE**
- **Phase 1** `v0.2-multimode` — hybrid (BM25 RRF) + cross-encoder rerank; FedReg/advisory
  loaders; section-aware chunking. **← IN PROGRESS (hybrid built, unproven — see §6)**
- **Phase 2** `v0.3-live-etl` — trigger-based incremental ETL (FedReg + eCFR watchers).
- **Phase 3** `v0.4-orchestrated` — planner/skills + semantic FAQ cache + answer verifier.
- **Phase 4** `v0.5-cognitus-ui` — Cognitus design-system UX.
- **Phase 5** `v1.0` — hardening, CI, docs, reproducibility.

---

## 4. Environment & prerequisites (all present/offline)

- **OS/shell:** Windows 11, Python 3.12.10. Bash + PowerShell tools available.
- **Installed deps:** flask, requests, chromadb, llama_index, onnxruntime,
  onnxruntime-genai 0.5.2, sentence-transformers, numpy, **rank_bm25** (added this session).
- **Cached models (HF cache `~/.cache/huggingface/hub`):**
  - `BAAI/bge-small-en-v1.5` (embeddings)
  - `cross-encoder/ms-marco-MiniLM-L-6-v2` (reranker — for Phase 1)
  - `microsoft/Phi-4-mini-instruct-onnx`, variant `cpu_and_mobile/cpu-int4-rtn-block-32-acc-level-4` (generation)
- **eCFR public API** reachable (used at build time only; runtime is fully local).

---

## 5. How to run

```bash
# from project root
python -m scripts.build_index     # pull 31 CFR X parts (ECFR_PARTS, default 1010,1020) -> ChromaDB
python -m scripts.eval            # retrieval hit@k on data/eval/gold.jsonl
python -m tests.test_smoke        # single retrieval assertion
python -m src.app.asgi            # serve http://127.0.0.1:8000 (Flask dev server)
```

Key env vars: `RAG_MODE` (`naive`|`hybrid`, default `naive`), `EMBED_MODEL_NAME`,
`CHROMA_PATH`, `RETRIEVAL_TOP_K` (5), `MAX_NEW_TOKENS` (400), `GENERATE` (true),
`CONTEXT_CHAR_BUDGET` (8000), `ECFR_PARTS`, `ECFR_TITLE`/`ECFR_CHAPTER` (31/X),
`PHI4_MODEL_DIR` (optional override).

---

## 6. Current measured state (after iteration 2)

- Index: **105 sections** of 31 CFR Ch. X (parts 1010, 1020), `as_of` 2026-06-25.
- Endpoints verified: `/healthz`, `/corpus_status`, `/chat_stream` (SSE), `/` (UI).
  Two live questions returned grounded, cited answers (CTR → $10,000 / 1010.311; CIP → 1020.220).
- **Eval (corrected gold set, 5 items):**
  | Mode | hit@5 | controlling-section rank |
  |------|-------|--------------------------|
  | naive  | **1.00** | all @1 |
  | hybrid | 1.00 | demoted (CTR @2, credit @4) |
- **Decision:** **naive is default.** Hybrid built & available (`RAG_MODE=hybrid`) but
  **unproven** — no gain + ranking regression on a set too small to discriminate.

---

## 7. Files created/changed this session

```
src/rag/config.py                      # env-driven RagConfig
src/rag/indexing/loaders/ecfr.py       # eCFR API loader (resolves up_to_date_as_of)
src/rag/indexing/builder.py            # ChromaDB + bge-small embedding
src/rag/retrieval/factory.py           # naive + hybrid (BM25-RRF), shared (context,citations)
src/rag/llm/models.py                  # Phi-4-mini ONNX streaming wrapper
src/app/api.py                         # Flask + SSE /chat_stream, /healthz, /corpus_status
src/app/asgi.py                        # entry point
src/app/static/index.html              # minimal UI
scripts/build_index.py                 # full index build
scripts/eval.py                        # retrieval hit@k harness
tests/test_smoke.py                    # one runnable retrieval check
data/eval/gold.jsonl                   # gold Q&A (5 items; 1 label corrected)
requirements.txt, .gitignore
.pipeline/STATUS.md                    # loop log (READ THIS for iteration detail)
.pipeline/DEPLOYMENTIDEAS.md           # role-5 SaaS hosting + cost scope
.pipeline/HANDOFF.md                   # this file
```
Plus persistent memory at the session memory dir: `phase0-baseline.md` (+ `MEMORY.md` index).

---

## 8. Gotchas already solved (don't re-discover)

1. **eCFR 404 on un-issued dates** (e.g. "today"). Use the title's `up_to_date_as_of` from
   `/versioner/v1/titles.json` — `ecfr.latest_date()` handles it.
2. **onnxruntime-genai 0.5.2:** `params.input_ids` rejects a Python list — pass
   `np.asarray([tokens], dtype=np.int32)`; loop is `compute_logits()` + `generate_next_token()`.
3. **Phi-4 int4 CPU OOM (~13 GB)** on uncapped multi-section context. Capped to 8000 chars
   (`CONTEXT_CHAR_BUDGET`); ~3.3 GB at run. CPU generation is slow (seconds–minutes/answer).
4. **chromadb telemetry warnings** (`capture() takes 1 positional argument...`) are harmless noise.
5. **Validate the gold set against primary text** — a gold label was wrong (1020.410 vs the
   correct 1010.410). The SME's most valuable job.

---

## 9. Recommended next step (PM, evidence-based)

Before re-judging hybrid/rerank:
1. **Expand the gold set** to ~20–30 harder items (clause-number lookups, dollar thresholds,
   "what changed") where BM25 should win if it ever will.
2. **Add Phase-1 corpus breadth** — FedReg (FinCEN) + advisory static loaders
   (`src/rag/indexing/loaders/fedreg.py`, `fincen.py`).
3. **Re-measure naive vs hybrid** on the bigger/harder set; add the cross-encoder reranker
   only if it fixes hybrid's ranking regression.
4. Backlog: F2 CIP-completeness verifier (Phase 3); section-aware chunking tuned to eCFR XML.
