# FAQ Cache & Fast-Path — AML/KYC RAG Chatbot

**Deviation 3 of 4.** · **Status:** Draft v1 · **Last updated:** 2026-06-25

> **Goal:** answer the most common BSA/AML questions in **under a second** by
> serving pre-built, pre-verified answers from a **semantic** cache — reserving
> CPU generation for genuinely novel queries.

`fedacq-rag-chatbot` already ships an **exact-match** answer cache (SQLite,
~140 ms replay, ~1000× speedup on identical questions). This project keeps that
and adds a higher-value layer in front of it: a **semantic FAQ cache** that hits on
*paraphrases*, not just identical strings.

---

## 1. Two-tier caching

```
question
   │
   ▼
┌────────────────────────────┐  hit (cos ≥ FAQ_SIM_THRESHOLD)
│ TIER 1: Semantic FAQ cache │ ───────────────▶ pre-verified answer + citations
│ curated, pre-verified      │                  (sub-second, high trust)
└──────────┬─────────────────┘
           │ miss
           ▼
┌────────────────────────────┐  hit (exact normalized match)
│ TIER 2: Exact answer cache │ ───────────────▶ replay stored answer
│ (reused from fedacq)       │                  (~140 ms)
└──────────┬─────────────────┘
           │ miss
           ▼
   full orchestration + retrieval + generation  (10–60 s on CPU)
   └─▶ on success, write Tier-2 entry for exact replay
```

| Tier | Match type | Source of answer | Trust | Latency |
|------|-----------|------------------|-------|---------|
| **1 — FAQ** | Semantic (embedding cosine) | **Curated + pre-verified** answers | Highest | < 1 s |
| **2 — Answer cache** | Exact (normalized string) | Prior generated answer | Inherited from a verified run | ~140 ms |

The split matters in a compliance setting: **Tier 1 answers are human-curated and
verified once**, so paraphrase matching is safe. Tier 2 only ever replays an answer
that was already produced (and verified) for an identical question.

---

## 2. What seeds the FAQ set

- **FinCEN official FAQs** (e.g., CDD/beneficial-ownership FAQs) — authoritative
  Q&A that maps directly into the cache.
- **High-frequency analyst questions** — thresholds (CTR `$10,000`, structuring),
  CIP minimums, CDD/EDD triggers, SAR timing, recordkeeping retention, MSB
  definitions.
- **Topic coverage of 31 CFR Chapter X** — at least one canonical FAQ per major
  obligation, each tied to its governing citation.

Each FAQ entry is stored as:

```json
{
  "id": "faq-ctr-threshold",
  "canonical_question": "What is the CTR filing threshold?",
  "paraphrases": ["when do I file a CTR", "currency transaction report dollar limit"],
  "answer": "<pre-verified answer text>",
  "citations": [{"source":"ecfr","citation":"31 CFR 1010.311","url":"...","as_of":"2026-06-15"}],
  "topic_keys": ["1010.311", "CTR"],
  "verified_by": "curator",
  "as_of": "2026-06-15"
}
```

`canonical_question` + `paraphrases` are embedded (same `bge-small-en-v1.5` model
as the corpus) into `data/faq.db` for cosine matching.

---

## 3. Matching & guardrails

- **Match:** embed the framed query (post `query_framer`), cosine-compare to FAQ
  embeddings; hit if best score ≥ `FAQ_SIM_THRESHOLD` (default `0.92`).
- **False-positive guard (critical):** serving the *wrong* cached answer is a
  compliance risk, so the threshold is deliberately **high**, and an optional
  **topic-key cross-check** requires the matched FAQ's `topic_keys` to be
  consistent with any citation/numeric hint extracted by `query_framer`. Mismatch →
  treat as miss, fall through to retrieval.
- **Near-miss logging:** queries in a "gray band" just below threshold are logged
  as **candidate new FAQs** — a feedback loop that grows coverage over time.

---

## 4. Staleness & invalidation (ties to ETL)

FAQ answers reference live regulation, so they must not go stale silently:

- Every FAQ entry stores the `citations[]` and `as_of` it was verified against.
- **ETL rule R5** ([`ETL_AND_TRIGGERS.md`](ETL_AND_TRIGGERS.md) §2): when a corpus
  change touches a citation referenced by any FAQ, that FAQ is **flagged stale**.
- Stale FAQs are either (a) auto-suppressed from Tier 1 (fall through to live
  retrieval) until re-curated, or (b) re-verified by re-running the answer through
  retrieval + `answer_verifier` and updating `as_of`. Default: **suppress, then
  re-verify** — never serve a known-stale cached compliance answer.
- The UI shows the `as_of` stamp on every answer (cached or fresh), so currency is
  always visible.

---

## 5. Config

| Variable | Default | Purpose |
|----------|---------|---------|
| `FAQ_CACHE` | `true` | Enable Tier-1 semantic FAQ fast-path |
| `FAQ_SIM_THRESHOLD` | `0.92` | Cosine threshold for a hit |
| `FAQ_TOPIC_CROSSCHECK` | `true` | Require topic-key consistency on hit |
| `FAQ_STALE_POLICY` | `suppress` | `suppress` \| `reverify_inline` on stale entry |
| `ANSWER_CACHE` | `true` | Tier-2 exact-match cache (reused from fedacq) |

---

## 6. Build & maintenance

- `scripts/seed_faq.py` — build `data/faq.db` from the curated FAQ source file
  (`data/faq_seed.yaml`) + FinCEN FAQ import; embed questions/paraphrases.
- Refreshed automatically on relevant corpus change (R5); manually re-runnable.
- A small committed `faq_seed.yaml` keeps the curated set **versioned and
  reviewable** in Git — curation is auditable.

---

## 7. Metrics

- **FAQ hit rate** and **p50/p95 hit latency** (target < 1 s).
- **False-positive rate** on a held-out paraphrase/anti-paraphrase test set
  (paraphrases must hit; off-topic look-alikes must miss).
- **Coverage** — share of the eval set answerable from Tier 1.

---

## 8. Open items

- Tune `FAQ_SIM_THRESHOLD` empirically against the paraphrase test set.
- Decide initial FAQ seed size (target ~30–50 high-traffic entries for v1).
- Finalize `suppress` vs. `reverify_inline` as the default stale policy after
  measuring re-verify latency.
