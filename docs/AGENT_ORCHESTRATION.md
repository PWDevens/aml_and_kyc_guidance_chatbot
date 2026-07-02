# Agent / Skill Orchestration — AML/KYC RAG Chatbot

**Deviation 2 of 4.** · **Status:** Draft v1 · **Last updated:** 2026-06-25

> **Goal:** improve query framing and response quality with a lightweight,
> **local-first** orchestration layer — a planner plus a few focused "skills" —
> rather than a single naive retrieve-then-generate pass. Each skill is a small,
> well-scoped prompt or rule that the CPU Phi-4-mini model can run cheaply.

The orchestrator is **off-by-default-safe**: setting `ORCHESTRATION=false`
collapses to the fedacq single-path behavior, so the baseline is always
recoverable for A/B comparison.

---

## 1. Why orchestration (the problem with one path)

AML/KYC questions are not homogeneous. A single retrieval+generation path tuned
for one shape under-serves the others:

| Question shape | Example | What it needs |
|----------------|---------|---------------|
| **Definitional** | "What is a 'covered financial institution'?" | Dense retrieval; precise definition section |
| **Numeric / threshold** | "What's the CTR filing threshold?" | Exact-term (BM25) recall on `$10,000`, clause numbers |
| **Procedural** | "What are the CIP minimum requirements?" | Multi-section assembly; ordered steps |
| **Cross-reference** | "How do CDD and beneficial-ownership rules interact?" | Graph retrieval over related obligations |
| **Change / temporal** | "What changed in the latest FinCEN beneficial-ownership rule?" | FedReg change records + version history |
| **Citation lookup** | "What does 31 CFR 1010.230 say?" | Direct citation fetch, minimal generation |

The orchestrator routes each to the right strategy and verifies the output.

---

## 2. Architecture

```
                       ┌───────────────────────────────────────┐
   question ──────────▶│  PLANNER  (orchestration/planner.py)  │
                       │  sequences skills, holds state        │
                       └──┬───────┬───────┬───────┬───────┬─────┘
                          ▼       ▼       ▼       ▼       ▼
                       frame   intent   route  (retrieve) verify
                       query   classify         + rerank  answer
                          │       │       │        │        │
            ┌─────────────┴───────┴───────┴────────┴────────┴──────────┐
            │  SKILLS (small, independently testable units)            │
            │   • query_framer     • intent_classifier                │
            │   • retrieval_router • answer_verifier                   │
            │   • citation_formatter • (change_resolver)               │
            └──────────────────────────────────────────────────────────┘
```

The planner is a thin state machine. Skills are pure-ish functions with explicit
contracts (below), so each is unit-testable and swappable.

---

## 3. The skills

### 3.1 `query_framer`
- **In:** raw user question.
- **Does:** normalize; **expand domain acronyms** via a curated glossary
  (CTR, SAR, CDD, CIP, BSA, UBO, MSB, EDD, PEP, …); strip chit-chat; extract any
  explicit citation (`31 CFR 1010.x`) or dollar figure as a structured hint.
- **Out:** `{ framed_query, citation_hint?, numeric_hint?, glossary_expansions[] }`.
- **Cost:** mostly rule/dictionary; optional 1 small LLM call for messy input.

### 3.2 `intent_classifier`
- **In:** framed query + hints.
- **Does:** classify into the taxonomy in §1 (definitional | numeric | procedural |
  cross-reference | change | citation-lookup). Few-shot prompt to Phi-4-mini, or a
  cheap zero-shot keyword/heuristic fallback.
- **Out:** `{ intent, confidence }`.

### 3.3 `retrieval_router`
- **In:** intent + hints.
- **Does:** select `RAG_MODE` and rerank knobs per the routing matrix (§4). For
  `citation-lookup`, may bypass semantic retrieval and fetch by exact citation.
- **Out:** `{ rag_mode, top_k, top_n, collection, filters }`.

### 3.4 `answer_verifier`  ⭐ (the compliance-critical skill)
- **In:** generated answer + retrieved context.
- **Does:** check that each factual claim is **supported by retrieved text**
  (grounding / entailment check via a small prompt or NLI-style cross-encoder).
  Unsupported claims are removed or labeled; if nothing is grounded, the system
  **declines and asks to rephrase** rather than hallucinate.
- **Out:** `{ verified_answer, claim_support_map, grounded: bool }`.
- **Why it matters:** in a regulated function, a confident-but-unsupported answer
  is worse than "I don't have that." This skill operationalizes *citation-or-refuse*.

### 3.5 `citation_formatter`
- **In:** retrieved chunks used in the verified answer.
- **Does:** assemble the citation list (source badge, `31 CFR` part/section or
  FedReg doc number, `as_of`, URL) for the SSE citation event + UI panel.
- **Out:** `citations[]`.

### 3.6 `change_resolver` (for `change` intent)
- **In:** topic + version history / FedReg change records.
- **Does:** assemble a temporal answer — which FinCEN actions touched the topic,
  with dates, effective dates, and before/after pointers from the version ledger
  (see [`ETL_AND_TRIGGERS.md`](ETL_AND_TRIGGERS.md) §4).
- **Out:** `{ change_timeline[], citations[] }`.

---

## 4. Routing matrix

| Intent | `RAG_MODE` | Rerank | Notable knobs |
|--------|-----------|--------|---------------|
| Definitional | `hybrid` | on | standard `top_k`/`top_n` |
| Numeric / threshold | `hybrid` | on | boost BM25 weight; keep numeric_hint as a filter |
| Procedural | `hybrid` | on | larger `top_n` (assemble multiple sections) |
| Cross-reference | `graph` | n/a | LightRAG dual-level; fall back to `hybrid` if graph subset lacks topic |
| Change / temporal | `hybrid` + `change_resolver` | on | query the `proposed`/`advisory` + version ledger |
| Citation lookup | direct fetch | off | exact-citation lookup; minimal generation |

All routes converge on the **shared** generation + citation path (ARCHITECTURE §3),
so only *selection* differs — the orchestrator never forks the serving code.

---

## 5. Keeping it local & cheap

- **Small prompts, not a mega-prompt.** Each skill does one job in a short prompt,
  which a CPU int4 Phi-4-mini handles in well under the generation budget.
- **Heuristic fast paths.** Intent and framing have rule-based shortcuts
  (regex for citations/dollar amounts, keyword cues) so most queries skip extra
  LLM calls entirely.
- **Budgeted.** `ORCHESTRATION_MAX_LLM_CALLS` caps added latency; over budget, the
  planner degrades gracefully to the single path.
- **Cache-aware.** The FAQ fast-path (see [`FAQ_CACHE.md`](FAQ_CACHE.md)) runs
  *before* routing, so common questions never pay orchestration cost.

---

## 6. Relationship to Skills/agent frameworks

The orchestration is implemented as plain, testable Python "skills" coordinated by
a planner — not a heavyweight agent framework — to preserve the local-first,
dependency-light ethic. The design is intentionally compatible with LlamaIndex's
query-pipeline / agent abstractions, so a later version could express the same
planner as a LlamaIndex `QueryPipeline` without changing the skill contracts.

---

## 7. Testing

- **Unit:** each skill against fixtures (intent labels, framing expectations,
  verifier grounded/ungrounded cases, router selections).
- **Golden-set eval:** run the curated AML/KYC Q&A set (PRD §9) through
  orchestration-on vs. orchestration-off; compare retrieval relevance and citation
  faithfulness (PRD §8).
- **Adversarial:** ungrounded/oversized questions must trigger the verifier's
  decline path, not a confident hallucination.

---

## 8. Open items

- Choose the verifier mechanism: small entailment prompt vs. NLI cross-encoder vs.
  hybrid (lexical-overlap pre-filter → LLM check on borderline claims).
- Size the acronym/glossary dictionary from FinCEN + FFIEC defined terms.
- Decide default `ORCHESTRATION_MAX_LLM_CALLS` after latency profiling.
