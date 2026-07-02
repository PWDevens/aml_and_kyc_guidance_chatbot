# Deployment Ideas — SaaS hosting & data processing scope

**Owner:** Distributed Systems Engineer (role 5) · **Updated:** 2026-06-29 (iter 1)
**Assessed against:** the Phase-0 baseline actually built (`src/`, naive RAG, Flask+SSE,
ChromaDB on disk, Phi-4-mini int4 CPU). Costs are order-of-magnitude monthly, USD.

> The product is deliberately **local-first / CPU-only** (ARCHITECTURE §1). Everything
> below is about offering it as a hosted SaaS *without* abandoning that property. The
> cheapest credible path keeps the local model; the alternatives buy latency/quality.

---

## 1. What the current code needs to run, hosted

| Component | Resource fact (measured/observed) | Hosting implication |
|-----------|-----------------------------------|---------------------|
| Phi-4-mini int4 ONNX (CPU) | Attention OOMs past ~2k-token context (capped at 8k chars). Generation is seconds-per-answer on CPU. | CPU-bound; **generation is the bottleneck**, not retrieval. Needs RAM headroom (8–16 GB/worker) and is slow under concurrency. |
| ChromaDB on disk | 105 sections ≈ a few MB; full 31 CFR X + FedReg + FFIEC → low hundreds of MB | Trivial storage. Fits a single volume; no managed vector DB needed at this scale. |
| bge-small + cross-encoder | CPU embedding/rerank, models cached on disk (~0.5 GB) | Bake into the image; no GPU required. |
| Flask + SSE | Dev server today; long-lived streaming connections | Needs an async server (Hypercorn — already planned Phase 5) + a proxy that doesn't buffer SSE. |
| eCFR / FedReg ETL (Phase 2+) | Outbound HTTPS to gov APIs, scheduled | A cron/worker, not a request-path concern. |

**Headline:** retrieval + corpus are cheap and small. The cost driver is **CPU
inference time per answer** and the SSE concurrency model. The FAQ cache
(Deviation 3) is therefore also the primary *cost* lever, not just latency.

---

## 2. Three deployment tiers

### Tier A — Single container, local model (cheapest, matches design)
- 1× small VM (2–4 vCPU, 16 GB), Docker image with model+index baked in.
- Generation serialized or low-concurrency; FAQ cache absorbs the common ~80%.
- **Cost:** ~$30–80/mo (e.g. a 4 vCPU/16 GB instance + small block volume + egress).
- **Limits:** handful of concurrent generating users before CPU saturates. Fine for
  demo, pilot, single-team internal tool.
- **Verdict:** ship this first. It is literally the current artifact in a box.

### Tier B — Horizontally scaled CPU workers + shared cache
- N stateless app containers behind a load balancer; **shared FAQ + answer cache**
  (Redis or a shared SQLite/Postgres) so a cache hit on one worker serves all.
- Index shipped read-only in the image (or a shared read-only volume); ETL writes a
  new versioned index that workers pull (matches the LFS/auto-PR plan).
- **Cost:** ~$150–500/mo depending on worker count + managed cache (~$15–50) +
  LB (~$20). Scales with concurrent *novel* (cache-miss) queries.
- **Limits:** still CPU generation; throughput ≈ workers × (1 / gen-seconds) for misses.

### Tier C — GPU generation or hosted LLM (quality/latency, breaks local-first)
- Either a GPU inference endpoint for Phi-4 (or larger) **or** swap generation to a
  hosted API. Retrieval/orchestration stay as-is.
- **Cost:** GPU box ~$300–1,500/mo (e.g. one L4/A10 class) *or* per-token API spend
  that scales with cache-miss volume (e.g. low-$ per thousand answers at small-model
  tiers; budget against expected miss rate).
- **When:** only if Tier A/B latency or answer quality blocks adoption. Note this
  abandons the "no cloud API at runtime" principle — keep it a config switch
  (`GENERATE`/model dir already make the LLM pluggable), not a rewrite.

---

## 3. Data processing & compliance cost notes (GovCon-relevant)

- **Source data is public-domain** (31 CFR / FedReg / FFIEC) — no licensing cost,
  redistribution is fine. Egress to gov APIs is negligible.
- **Tenant data = the questions users ask.** For a federal/bank buyer this is the
  sensitive surface, not the corpus. Implications that raise cost:
  - Logging/audit of queries → storage + retention controls.
  - If hosted for federal use: **FedRAMP / data-residency** expectations push toward
    GovCloud-style regions and an authorized CSP — materially higher floor than the
    figures above (authorization is a program cost, not an instance cost).
  - Local-first is a *selling point* here: "no query text leaves the box / no third-party
    LLM sees it" is exactly the Tier A story. Tier C reintroduces a data-flow that a
    GovCon security review will flag.
- **No PII in the corpus**; FAQ cache stores Q→A over public text. Keep it that way —
  don't let cache keys accumulate raw user identifiers.

---

## 4. Recommendation (lazy, defensible)

1. **Tier A now.** One container, model+index baked, Hypercorn, FAQ cache on. It is
   the current build deployed; spend is ~$30–80/mo.
2. **Add the shared cache (Tier B) when concurrency hurts**, not before. The FAQ
   hit-rate is the metric that decides this — instrument it before scaling.
3. **Treat Tier C as a config flag for buyers who demand it**, and document the
   data-flow tradeoff so the GovCon review isn't surprised.

**Open questions for the loop:**
- Target concurrency / expected daily query volume? (decides A vs B)
- Is a federal authorization boundary (FedRAMP/GovCloud) in scope for v1, or is the
  first buyer a commercial bank? (changes the cost floor by an order of magnitude)
- Measured FAQ hit-rate once real traffic exists (role 6 / Phase 3 data).
