# Pipeline status — the loop

Roles 1–6 from the build request map to artifacts, not ceremony:

| # | Role | Artifact / output |
|---|------|-------------------|
| 1 | PM | `docs/PRD.md` (exists) |
| 2 | Dev Manager | `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` (exist) |
| 3 | Sr. Dev | `src/**` code |
| 4 | Tester | `tests/**` + `python -m scripts.build_index` / eval run |
| 5 | Distributed Systems Eng | `.pipeline/DEPLOYMENTIDEAS.md` |
| 6 | AML & KYC SME | line-by-line review of live answers for regulatory correctness → feedback → restart |

## Loop log

### Iteration 1 — 2026-06-29 — Phase 0 (`v0.1-baseline`)
**Sr. Dev built** the smallest end-to-end slice that the ROADMAP Phase 0 demands:
- eCFR loader (31 CFR Chapter X, live API) → `src/rag/indexing/loaders/ecfr.py`
- index builder (chunk + bge-small embed + ChromaDB) → `scripts/build_index.py`
- naive dense retrieval → `src/rag/retrieval/factory.py`
- Phi-4-mini ONNX generation wrapper (optional, degrades to extractive) → `src/rag/llm/models.py`
- Flask + SSE `/chat_stream`, `/healthz`, `/corpus_status` → `src/app/api.py`
- minimal UI → `src/app/static/index.html`
- gold eval seed → `data/eval/gold.jsonl`

**Scoped down (ponytail):** no LlamaIndex yet (raw chromadb does naive dense), no
Docker yet, eval seed is small. Add in the phase that needs them.

### Iteration 2 — 2026-06-29 — eval baseline + AML/KYC SME review
**Role change:** GovCon SME → **AML & KYC SME** (domain-correctness reviewer).

**Tester/eval** (`scripts/eval.py`, naive baseline): **hit@5 = 0.80, term_recall = 1.00** over 5 gold items.

**AML & KYC SME findings (evidence-backed, not from memory):**
- **F1 — precision (real).** "CTR threshold" paraphrases surface a *cluster* of
  near-synonymous currency-report sections — 1010.310/.311/.330, 1020.310 — with
  different filers/forms (e.g. 1010.330 = trade-or-business / Form 8300, not the FI
  CTR). Naive dense doesn't reliably rank the *controlling* filing section first.
  Risk: answer cites a secondary/adjacent authority.
- **F2 — completeness (resolved, not a data defect).** CIP-retrieved context
  contains all four 1020.220 elements *including identification number*. The earlier
  answer's omission was a `MAX_NEW_TOKENS=80` test-cap artifact. Action: keep token
  budget adequate; add a mandatory-element completeness check to the Phase-3 verifier.
- **F3 — recall (real).** Gold expects bank-specific **1020.410** for credit-extension
  recordkeeping; naive dense returns the near-identically-titled general **1010.410**
  and misses 1020.410 (the 0.80 miss). Classic exact-section/clause-number weakness.

**SME correction (highest-value catch):** F3 was a **gold-set defect, not a retrieval
miss.** The phrase "extension of credit" appears verbatim in **1010.410** (records by
financial institutions, §(c) the >$10k extension-of-credit rule) and is *absent* from
1020.410 (records by banks). Gold label fixed 1020.410 → 1010.410. Retrieval had been
returning the correct section all along.

**Measured result (built `_hybrid` BM25-RRF, ran both modes on corrected set):**
| Mode | hit@5 | controlling-section ranks |
|------|-------|---------------------------|
| naive  | **1.00** | all @1 |
| hybrid | 1.00 | CTR @2, CIP @1, credit @4 (**demoted**) |

**Verdict — do NOT adopt hybrid yet.** No measured gain; a measurable *ranking
regression* (BM25 overlap pulls near-synonym sections up via RRF). The 5-item set is
also saturated at 1.00 — too small/easy to discriminate modes. Adding hybrid+rerank now
would be complexity we can't justify with numbers. `RAG_MODE=hybrid` stays available,
unproven; **naive remains default.**

**PM restart recommendation (revised by data):** before re-judging hybrid —
1. **Expand the gold set** to ~20–30 harder items (clause-number lookups, dollar
   thresholds, "what changed") where BM25 *should* win if it's going to.
2. **Add corpus breadth** (Phase-1 FedReg + advisory static loaders).
3. Then re-measure naive vs hybrid; add the **cross-encoder reranker** only if it fixes
   hybrid's ranking regression on the bigger set.
4. F2 (CIP completeness) → Phase-3 verifier backlog.

**Next loop:** bigger gold set + FedReg/advisory loaders, then re-run this comparison.
