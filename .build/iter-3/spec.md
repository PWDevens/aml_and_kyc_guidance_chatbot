# Iteration 3 — Frozen spec

**Iteration:** N=3 · "Phase 3: orchestration + semantic FAQ cache"
**Target tag concept:** `v0.4-orchestration` (not git-tagged — full-build never tags)
**Written:** 2026-07-02 · **Author role:** PM (this iteration only)

> **Read this file only.** It is self-contained. Do not re-plan from `docs/` — the
> relevant decisions are lifted below, including the **local embedding measurements
> I ran during this spec** (against the already-cached `bge-small-en-v1.5`). Where a
> doc is cited it is for the senior-dev's optional reference, not required reading.

---

## Note on conventions (read first)

- **Operating mode is "full ponytail" (lazy = shortest working diff, YAGNI,
  stdlib/installed-deps first, one runnable check per change).** The user has
  explicitly forbidden the literal convention marker: **do NOT write `ponytail:`
  comments and do NOT use the word "ponytail" anywhere in code, docstrings, tests,
  or commit messages.** Simplifications get recorded in `changes.md` / the tech-debt
  ledger instead. The existing Phase-0/1 files (`api.py`, `models.py`, etc.) contain
  `ponytail:` comments and the word in a couple of places — **leave them exactly as
  they are; do not add new ones and do not do a cleanup/removal pass** (out-of-scope
  churn, and iter-1's gate already treated touching them as a defect).
- Match the existing house style: module docstring stating intent, `from __future__
  import annotations`, small pure functions, dict-dispatch for skill/mode registries
  (mirror `src/rag/retrieval/factory.py`'s `_MODES` and `src/etl/rules.py`), env-driven
  config via `RagConfig`. **Mirror `src/rag/cache.py`** for any new SQLite module
  (stdlib `sqlite3`, one `_conn()` helper, `CREATE TABLE IF NOT EXISTS` on first use,
  no ORM, parameterized SQL only). **Mirror `src/etl/state.py`** for provenance-style
  writes if needed.
- **No new pip dependencies.** Everything this iteration needs is already installed:
  `sentence-transformers`, `numpy`, `PyYAML` (6.0.3, verified importable),
  `chromadb`, `flask`, `onnxruntime-genai`. Do not add a dependency.

---

## Goal

Wrap the existing single retrieve→generate→cite path with a **local-first
orchestration layer** (a thin planner + focused skills) and a **semantic FAQ
fast-path**, so that:

1. Heterogeneous AML/KYC question shapes (definitional / numeric / procedural /
   citation-lookup / change) are **routed** to an appropriate retrieval mode instead
   of always using the single default.
2. Generated answers are **verified against retrieved text** — ungrounded claims are
   labeled/declined rather than streamed as fact (compliance-critical;
   *citation-or-refuse*), and the verifier includes a **mandatory-element completeness
   check** (carried-forward tech-debt **F2**).
3. Common questions get a **sub-second semantic FAQ cache hit** (Tier 1, cosine
   similarity over curated pre-verified answers), sitting **in front of** the existing
   exact-match Tier-2 cache.
4. **`ORCHESTRATION=false` collapses to the exact current (iter-2) `/chat_stream`
   behavior** — the baseline is always recoverable (hard architectural constraint).

Primary doc sources (for optional reference only): `docs/AGENT_ORCHESTRATION.md`,
`docs/FAQ_CACHE.md`, `docs/ARCHITECTURE.md` §3/§10, `docs/ETL_AND_TRIGGERS.md` §2 (R5).

---

## Decisions made (resolved by me during this spec — NOT open questions)

These are **settled**. I verified them against the current code and by running the
already-cached embedding model locally. Recorded here for transparency, not to halt
the loop. The senior-dev follows them.

### D1 — Embedding at request time: add a thin `embed_query()` helper. RESOLVED.
The corpus is embedded only at *build/upsert* time, inside Chroma's
`SentenceTransformerEmbeddingFunction` (`src/rag/indexing/builder.py::_embed_fn`).
There is **no** request-time `embed(text) -> vector` helper today. The FAQ cache needs
one (embed the framed query, cosine-compare to FAQ embeddings). **I verified** that
`sentence_transformers.SentenceTransformer('BAAI/bge-small-en-v1.5')` is already
cached locally and is cheap at request time:
- one-time model load ≈ 13 s (lazy, first call only — cache it in an `lru_cache`
  singleton, same pattern as `factory.py::_reranker` and `models.py::_load`);
- `encode([...], normalize_embeddings=True)` ≈ **0.07 s** per call after load;
- returns **384-dim float32** vectors, L2-normalized (norm = 1.0), so **cosine = dot
  product**.

Add a small module `src/rag/faq/embed.py` exposing:
```python
def embed_query(text: str, model_name: str = ...) -> "np.ndarray":  # 1-D float32, L2-normalized
def embed_queries(texts: list[str], model_name: str = ...) -> "np.ndarray":  # (n, 384), normalized
```
Use `normalize_embeddings=True` and an `@lru_cache(maxsize=1)`-loaded model keyed on
`model_name` (default `RagConfig.embed_model`). This is the *only* new embedding
capability; the seed script (`scripts/seed_faq.py`) reuses the same helper so FAQ
question/paraphrase vectors and the query vector come from the identical model — a
correctness requirement for cosine to be meaningful.

### D2 — Matching strategy: **max-over-paraphrases**, NOT canonical-only. RESOLVED.
I measured raw question↔question cosine on `bge-small-en-v1.5`. Findings:
- Real paraphrases of a canonical question score **0.63–0.84** against the canonical
  question alone (e.g. "when do I file a CTR" ↔ "What is the CTR filing threshold?" =
  0.84; "currency transaction report dollar limit" ↔ same = 0.65).
- Off-topic look-alikes score **0.64–0.66**. **The paraphrase and off-topic bands
  overlap** when matching only against the canonical question — a single global
  cosine threshold on canonical-only embeddings is **not separable**.
- Embedding **every stored `canonical_question` + `paraphrases` string** for an entry
  and taking the **max cosine over that set** separates the bands cleanly: on-topic
  queries land **0.72–0.98**, off-topic land **0.61–0.70**.

Therefore the matcher **must** embed all of an entry's canonical+paraphrase strings
into `data/faq.db` and score a query as `max(cosine(query, e) for e in entry_vectors)`,
selecting the best entry across all entries. Canonical-only matching is **prohibited**
(it fails the paraphrase test set).

### D3 — `FAQ_SIM_THRESHOLD` default: **lower it to `0.83`**, do not ship `0.92`. RESOLVED.
`docs/FAQ_CACHE.md` proposes `0.92`. My measurements show `0.92` would **miss almost
every real paraphrase** even with max-over-paraphrases matching (correct CTR
paraphrases measured at 0.79 and 0.88 — both below 0.92). `0.92` gives near-zero
recall, defeating the cache's purpose. **Set the default to `0.83`**, which sits above
the measured off-topic ceiling (~0.70) with margin and admits genuine paraphrases.
Keep it an env var (`FAQ_SIM_THRESHOLD`) so it stays tunable, and **the topic-key
cross-check (D4) is the real false-positive guard** — the threshold alone is not
relied on to prevent wrong-answer serving. Record the doc's `0.92` vs shipped `0.83`
delta and the measurement in `changes.md` (do not silently diverge from the doc).
The paraphrase/anti-paraphrase test set (see Acceptance) is the empirical basis; if
it later shows a better value, that's a tuning follow-up, not a redesign.

### D4 — Topic-key cross-check is **mandatory and load-bearing**, default ON. RESOLVED.
Because the cosine bands are close (D2), serving the *wrong* cached compliance answer
is the real risk. On a candidate FAQ hit, require the matched entry's `topic_keys` to
be **consistent with any structured hint** `query_framer` extracted (citation hint
like `1010.311`, or a numeric/dollar hint). Concretely: if the query yielded a
`citation_hint` or `numeric_hint`, at least one of those hints must appear in (or be
consistent with) the entry's `topic_keys`; **mismatch → treat as miss, fall through
to Tier-2/retrieval.** If the query yielded *no* structured hint, the cross-check
cannot fire and the cosine threshold alone decides (acceptable — no hint to
contradict). Gated by `FAQ_TOPIC_CROSSCHECK` (default `true`).

### D5 — `change_resolver` is **DEFERRED this iteration** (stated reason). RESOLVED.
The backlog explicitly allows deferring `change_resolver` "with a stated reason." I
defer it because: (a) it depends on a **version-history / valid_from–valid_to ledger**
that iter-2 did **not** build — iter-2's provenance ledger records ingest *actions*
(`action='schedule'` markers, upserts), not a queryable before/after section-version
timeline, and the iter-2 accepted-debt note confirms "R1 schedule is a provenance
marker, not a timer/queue"; (b) building a correct temporal diff answer is itself a
meaningful sub-project and this is already the plan's two headline differentiators
combined; (c) Iteration 4's "What changed timeline view" is explicitly conditional on
`change_resolver` shipping and is designed to degrade. **This iteration builds 5
skills, not 6.** The `change` **intent** is still *classified* and *routed* (to
`hybrid_rerank`, see D8) — we just don't assemble a bespoke temporal timeline. Note
this deferral in `changes.md` and `progress.md` for Iteration 4's awareness.

### D6 — `ORCHESTRATION` default: ship **`false`** this iteration. RESOLVED (judgment call).
`docs/ARCHITECTURE.md` §8 lists default `true`. **Ship `false` instead**, for this
one iteration, then flip to `true` only after the on-vs-off eval (Acceptance AC-9)
shows a win — mirroring the project's own established philosophy from iter-1: *"don't
adopt a mode without a measured win"* (naive stayed default over hybrid on exactly
this reasoning; `hybrid_rerank` was built but **not** promoted to default pending a
deliberate evidence-based decision). Shipping `true` before measuring would silently
change every answer's path on a CPU-slow stack that adds LLM calls, with no A/B
baseline recorded. So: **`ORCHESTRATION=false` is the shipped default; the code path
for `true` is fully built and tested; the eval compares them; the recommendation to
flip the default (or not) is recorded in `changes.md`.** This is the correct PM call
and is consistent with the "off-by-default-safe" framing — the *safe* default is off
until proven. (If the AC-9 eval shows a clear, unambiguous win with no latency
regression that breaks the demo, the senior-dev MAY flip the default to `true` in the
same iteration and record the measured justification — but absence of that evidence
means it ships `false`.)

### D7 — `FAQ_CACHE` and `VERIFY_ANSWERS` defaults. RESOLVED.
- `FAQ_CACHE` default **`true`** — Tier 1 only ever serves **human-curated,
  pre-verified** answers, so a hit is high-trust by construction; it is safe on by
  default and is the feature's whole point. (It is independent of `ORCHESTRATION`: the
  FAQ fast-path may run even when orchestration is off — see D9 wiring.)
- `VERIFY_ANSWERS` default **`true`** *but only consulted when `ORCHESTRATION=true`*.
  Verification is part of the orchestrated path. With `ORCHESTRATION=false` the flow is
  byte-for-byte the iter-2 path (no verify step), satisfying the hard collapse
  constraint. So effectively: verify runs iff `ORCHESTRATION and VERIFY_ANSWERS`.

### D8 — Routing matrix maps to the **3 real modes only** (naive/hybrid/hybrid_rerank). RESOLVED.
The doc's routing matrix references a `graph` mode for cross-reference intent.
**`graph` is NOT built** (factory `_MODES` has only `naive`, `hybrid`, `hybrid_rerank`;
`retrieve()` raises `ValueError` for anything else). The router must **never** emit a
mode outside `{"naive","hybrid","hybrid_rerank"}`. Concrete mapping this iteration:

| Intent | Emitted `rag_mode` | Rationale |
|--------|--------------------|-----------|
| `definitional` | `hybrid_rerank` | iter-1 measured `hybrid_rerank` best on term-recall (1.00 vs naive 0.92) and rank (avg 1.12); definitions benefit from precise section ranking |
| `numeric` / threshold | `hybrid_rerank` | exact-term (BM25) recall on `$10,000`/clause numbers is the whole point; rerank fixes the near-synonym regression iter-1 documented |
| `procedural` | `hybrid_rerank` | multi-section assembly; best ranking wins |
| `cross-reference` | `hybrid_rerank` | doc wanted `graph`; **fall back to `hybrid_rerank`** (graph not built — doc §4 itself specifies this fallback) |
| `change` / temporal | `hybrid_rerank` | `change_resolver` deferred (D5); still retrieve+generate+verify normally |
| `citation-lookup` | `naive` **+ citation filter** | see D8a |

**D8a — citation-lookup:** when `query_framer` extracts a `citation_hint` (regex
`\b\d{2}\s*CFR\s*\d+\.\d+\b`, normalized to `"31 CFR 1010.311"` form), the router
returns `rag_mode="naive"` and a `filters={"citation": <hint>}` field. The
orchestrated retrieve step, when given a citation filter, does a **direct Chroma
`get(where={"citation": hint})`** (exact metadata fetch, minimal/zero generation) —
this is the "direct fetch" row of the matrix. If the filtered fetch returns nothing,
fall back to the intent's normal semantic mode. **Do not** add a new public function
to `factory.py` that changes existing signatures; add the citation-filter fetch as a
**new helper** consumed by the orchestrated path (see Interfaces). The non-orchestrated
path is untouched.

**D8b — router output is advisory selection only.** The router returns a dict of
knobs; the orchestrated planner applies them by constructing a **per-request
`RagConfig`** via `dataclasses.replace(CONFIG, rag_mode=..., retrieval_top_k=...)` and
calling the existing `retrieve(cfg, question)`. It does **not** fork or duplicate
serving code (ARCHITECTURE §3 "one serving path"). `RagConfig` is `frozen=True` —
`dataclasses.replace` is the correct, existing pattern (see `tests/test_chat_stream_cache.py`).

### D9 — `/chat_stream` wiring order. RESOLVED (this is the integration contract).
The new online flow in `src/app/api.py::chat_stream.gen()` becomes, **in order**:

```
1. FAQ fast-path (Tier 1)   — if CONFIG.faq_cache and a hit: stream cached answer +
                              citations + as_of, emit done, RETURN. (Runs BEFORE Tier-2,
                              per FAQ_CACHE §1 diagram — a semantic hit short-circuits
                              everything.) Independent of ORCHESTRATION.
2. Tier-2 exact cache       — UNCHANGED from iter-2 (cache.get -> replay -> return).
3. Orchestrated retrieve    — if CONFIG.orchestration: frame -> classify -> route ->
                              build per-request cfg -> retrieve. else: retrieve(CONFIG, q)
                              EXACTLY as iter-2 (single default path).
4. Generate                 — UNCHANGED streaming loop (models.stream).
5. Verify                   — if CONFIG.orchestration and CONFIG.verify_answers:
                              run answer_verifier on (answer, context) AFTER generation
                              completes; see D10 for streaming semantics.
6. Tier-2 write + citations — UNCHANGED (write generated answer to Tier-2; emit
                              citations + as_of; emit done).
```

**Hard constraint:** when `ORCHESTRATION=false` **and** `FAQ_CACHE=false`, `gen()` must
produce **byte-identical** SSE output to iter-2's current `gen()` for the same inputs.
Verify this with a test (AC-2). The cleanest way to guarantee it: keep the existing
iter-2 body as the literal `else` branch and add the orchestrated branch alongside —
do **not** rewrite the shared generate/cache/citation tail.

### D10 — Verifier streaming semantics: **buffer-then-verify, label in a trailer**. RESOLVED.
Generation currently streams token-by-token; a verifier that must see the *whole*
answer cannot run mid-stream without buffering. To keep the compliance guarantee
without a heavy rewrite:
- **Still stream tokens live** (UX unchanged — the user sees the answer generate).
- Accumulate the full answer (already done: `answer_parts`).
- After the stream completes, run `answer_verifier(answer, context)`. Emit a **new SSE
  event** `verification` carrying `{grounded: bool, unsupported_claims: [...],
  missing_elements: [...], note: <str>}` **before** the `citations` event.
- **Decline path:** if `grounded is False` (nothing in the answer is supported by
  retrieved text), do **not** write the answer to the Tier-2 cache, and emit the
  `verification` event with a `declined: true` flag and a rephrase suggestion so the UI
  can render the decline state (Iteration 4 renders it; this iteration just emits it).
- The **completeness result** (F2, D11) rides in the same `verification` event as
  `missing_elements`. A non-empty `missing_elements` does **not** by itself decline the
  answer (the answer may be correct-but-incomplete); it annotates. Only *ungrounded*
  (nothing supported) triggers the hard decline. Record this policy choice in `changes.md`.
- Only a **grounded, non-declined** generated answer is Tier-2-cache-eligible (tightens
  iter-2's existing "only generated path is cacheable" rule with "…and verified").

### D11 — F2 completeness check lives in `answer_verifier`. RESOLVED (carried-forward debt).
The pre-loop **F2** item ("Phase 3's `answer_verifier` should include a
mandatory-element completeness check") is **in scope and assigned here**. Implement a
**rule/keyword completeness check** for a small set of known mandatory-element
questions (CIP is the canonical one). Concretely: maintain a tiny table of
`{topic -> required_elements}` in `src/rag/orchestration/verify.py`, e.g. CIP's four
required identifying elements per 31 CFR 1020.220 — **name, date of birth, address,
identification number** (the customer identification program minimum data elements).
When the classified intent is `procedural`/`definitional` **and** the query/topic
matches a known mandatory-element topic, check the generated answer text for the
presence of each required element (case-insensitive substring / simple synonym set);
report any absent ones in `missing_elements`. This directly closes F2 (the earlier
missing-element case was a `MAX_NEW_TOKENS` cap artifact; the verifier now *detects*
omission rather than silently passing it). Keep the table small and honest — CIP is
the one the debt names; add SAR-timing and CTR-threshold element checks **only if
cheap**, else leave a `changes.md` note. **This is a heuristic/rule check — no LLM
call** (§5 "heuristic fast paths").

### D12 — Verifier grounding mechanism: **lexical-overlap pre-filter, LLM only on borderline**. RESOLVED.
`docs/AGENT_ORCHESTRATION.md` §8 lists this as open. I resolve it toward the **cheapest
adequate** mechanism consistent with §5 ("small prompts, heuristic fast paths",
CPU-slow generation):
- **Primary (no LLM):** split the answer into sentences/claims; for each, compute
  lexical overlap (token-set / simple n-gram containment) against the retrieved
  `context`. A claim with strong overlap to some retrieved passage is **grounded**.
  If **every** claim has near-zero overlap → `grounded=False` (decline).
- **Optional LLM escalation (budgeted):** only claims in a "gray band" (some but weak
  overlap) *may* be sent to a single small Phi-4 entailment prompt
  ("Does CONTEXT support CLAIM? yes/no"), and **only if** `ORCHESTRATION_MAX_LLM_CALLS`
  budget remains. Over budget → treat gray-band claims as grounded-with-caveat (label,
  don't decline) rather than pay latency. Generation is seconds-per-call on CPU, so the
  default posture is **lexical-only**; the LLM path is opt-in headroom, not the norm.
This keeps the verifier fast and deterministic for tests. Record the mechanism choice
in `changes.md` (closes AGENT_ORCHESTRATION §8 open item #1).

### D13 — `intent_classifier` and `query_framer` are heuristic-first. RESOLVED.
Per §5, both must have rule/regex fast paths that let most queries **skip LLM calls**:
- `query_framer`: pure rule/dictionary. Acronym glossary expansion (CTR, SAR, CDD, CIP,
  BSA, UBO, MSB, EDD, PEP — start from this set, ≤ ~15 entries, sourced from the
  intents in the routing table); citation-hint regex; dollar/numeric-hint regex; strip
  leading chit-chat. **No LLM call** in the default path.
- `intent_classifier`: **keyword/heuristic zero-shot first** (e.g. presence of a
  citation hint → `citation-lookup`; `$`/"threshold"/"how much" → `numeric`; "what is
  a"/"define"/"definition of" → `definitional`; "steps"/"requirements"/"how do
  I"/"minimum" → `procedural`; "changed"/"latest"/"new rule"/"amended" → `change`;
  default → `definitional`). The optional Phi-4 few-shot classifier is a fallback only
  for genuinely ambiguous input and only within the LLM-call budget. Ship the heuristic
  path as the default; the LLM fallback may be stubbed/minimal if time-constrained
  (state honestly in `changes.md`) — the heuristic path must be complete and tested.

### D14 — R5 (FAQ staleness) scope. RESOLVED — implement the **flagging trigger**, default policy **suppress**.
The backlog lists "staleness tied to ETL rule R5 (suppress-then-reverify)" as **in
scope**. Implement R5 as a **new rule + a sync step in the ETL pipeline**, minimally
and correctly:
- Add an R5 classifier/helper to `src/etl/rules.py` (or a small `faq_sync` step in
  `src/etl/pipeline.py`) that, **after a successful R1/R4 upsert** of a `citation`,
  checks whether any FAQ entry references that citation in its `topic_keys`/`citations`
  and, if so, **flags that FAQ entry stale** (writes a `stale=1` / `stale_reason` marker
  into `data/faq.db` and a provenance row `rule_id='R5', action='flag_stale'`).
- The FAQ matcher (Tier 1) **honors the stale flag**: a stale entry is **suppressed**
  from Tier 1 (falls through to Tier-2/live retrieval) when `FAQ_STALE_POLICY=suppress`
  (the shipped default). `reverify_inline` is **NOT built** this iteration — leave the
  policy value accepted but treat any non-`suppress` value as `suppress` with a
  `changes.md` note (re-verify-inline requires running the full retrieve+verify loop
  from ETL, which couples ETL to generation; defer as bounded tech-debt with that
  stated upgrade path). This satisfies "never serve a known-stale cached compliance
  answer" (the doc's hard requirement) with the minimum mechanism.
- **Do not** build R6 (graph rebuild) or R7 (FFIEC ingest) — see Out of scope.

### D15 — eCFR removed-section deletion (R4b) is **DEFERRED**. RESOLVED.
The iter-2 accepted-debt R4b item (upsert empty record list to delete a repealed
section's chunks) is a natural neighbor but is **not required by any Iteration 3
acceptance criterion**. Deferring keeps this large iteration scoped. Note it stays open
in `progress.md`. (Do not build it; do not let it expand FAQ/verify scope.)

---

## Acceptance criteria (testable)

Each maps to a test in `tests/`. Deterministic tests must not require network or live
generation; mirror the mocking style of `tests/test_chat_stream_cache.py`
(monkeypatch `CONFIG`, `models.stream`, `retrieve`).

- **AC-1 — Skills exist and are unit-tested.** `query_framer`, `intent_classifier`,
  `retrieval_router`, `answer_verifier`, `citation_formatter` each have an
  independently-testable function contract (below) and passing unit tests over fixtures
  (intent labels; framing expectations incl. acronym expansion + citation/numeric hint
  extraction; router selections; verifier grounded/ungrounded/incomplete cases;
  citation-list assembly). `change_resolver` is **absent by design** (D5) — a test/README
  note states the deferral reason.
- **AC-2 — `ORCHESTRATION=false` collapse is byte-identical.** A test asserts that with
  `orchestration=False` **and** `faq_cache=False`, `/chat_stream` SSE output equals the
  iter-2 behavior for representative inputs (cache-hit replay; cache-miss generate;
  extractive fallback; no-citation; empty-question 400). (Reuse/extend
  `tests/test_chat_stream_cache.py` cases — they must all still pass unchanged.)
- **AC-3 — Router only emits real modes.** A test asserts `retrieval_router` never
  returns a `rag_mode` outside `{"naive","hybrid","hybrid_rerank"}` across all six
  intents (including `cross-reference` → `hybrid_rerank` fallback, and `change` →
  `hybrid_rerank`), and that a citation-lookup intent yields a `filters` citation.
- **AC-4 — Verifier declines ungrounded answers.** Given an answer whose claims have
  no lexical support in the provided context, `answer_verifier` returns
  `grounded=False`; the `/chat_stream` path emits a `verification` event with
  `declined: true` and does **not** write the answer to Tier-2. Given a grounded answer,
  `grounded=True` and the answer is cache-eligible. (AGENT_ORCHESTRATION §7 adversarial.)
- **AC-5 — F2 completeness check works.** A test feeds a CIP-minimum-requirements
  question with an answer omitting one required element (e.g. missing "date of birth")
  and asserts `answer_verifier` reports it in `missing_elements`; a complete answer
  reports `missing_elements == []`. (Directly closes carried-forward F2.)
- **AC-6 — FAQ semantic hit on a paraphrase.** With a seeded `data/faq.db`, a paraphrase
  of a seeded canonical question (not an exact string match) produces a Tier-1 hit that
  streams the pre-verified answer + citations + `as_of` and **skips retrieval and
  generation entirely** (assert `retrieve`/`models.stream` not called), when
  `cos ≥ FAQ_SIM_THRESHOLD` and topic-key cross-check passes.
- **AC-7 — FAQ false-positive guard.** An off-topic look-alike query that is below
  threshold, **or** whose extracted citation/numeric hint contradicts the best entry's
  `topic_keys`, produces a **miss** (falls through to Tier-2/retrieval) — verified on a
  small paraphrase/anti-paraphrase fixture set. (FAQ_CACHE §7 false-positive metric.)
- **AC-8 — FAQ ordering + independence.** Tier-1 runs **before** Tier-2 (a query that
  would hit both proves Tier-1 answers it); `FAQ_CACHE=false` fully bypasses Tier 1
  (no `faq.db` read, no embed call).
- **AC-9 — Orchestration on-vs-off eval.** Extend `scripts/eval.py` (or add a sibling
  script) to run the existing ~25-item gold set through `ORCHESTRATION=true` vs
  `=false`, reporting retrieval relevance / citation faithfulness for each, and record
  the comparison + the default-flip recommendation (D6) in `changes.md`. This need not
  be a pytest; a runnable script whose output is captured in `changes.md` satisfies it.
- **AC-10 — R5 staleness flag + suppression.** A test simulates a successful ETL upsert
  of a citation referenced by a seeded FAQ entry, asserts the entry is flagged stale in
  `faq.db` (+ an `R5`/`flag_stale` provenance row), and asserts the Tier-1 matcher then
  **suppresses** that entry (returns a miss for a query that previously hit it) under
  `FAQ_STALE_POLICY=suppress`.
- **AC-11 — Seed script + committed seed.** `scripts/seed_faq.py` builds `data/faq.db`
  from a committed `data/faq_seed.yaml`; running it is idempotent (re-run yields the same
  store). The seed contains **quality curated entries with real citations** — target
  ~30–50 per FAQ_CACHE §8; **if curation time is short, ship fewer (e.g. ≥ 12) high-
  quality entries and state the gap honestly in `changes.md` — do NOT pad to hit a
  number** (backlog directive). Every entry's `citations` must reference a real 31 CFR
  section present in the corpus.
- **AC-12 — Full suite green.** The existing 47-test suite plus the new tests pass:
  `py -3.12 -m pytest tests/ -q`. No existing test is weakened to accommodate new code.

---

## Files to create / modify

**Create (new — the visible Phase-3 surface):**
- `src/rag/faq/__init__.py`
- `src/rag/faq/embed.py` — `embed_query` / `embed_queries` (D1); `@lru_cache` model.
- `src/rag/faq/store.py` — `data/faq.db` read/write (SQLite, mirror `cache.py`/`state.py`
  style): schema for entries (id, canonical_question, paraphrases_json, answer,
  citations_json, topic_keys_json, embeddings BLOB, verified_by, as_of, stale, stale_reason);
  functions `upsert_entry`, `all_entries` (or `iter_entries`), `flag_stale(citation)`,
  `is_stale(id)`.
- `src/rag/faq/matcher.py` — `match(cfg, framed_query, hints) -> FaqHit | None`:
  embed query (D1), max-over-paraphrases cosine (D2) across non-stale entries, apply
  `FAQ_SIM_THRESHOLD` (D3) + topic-key cross-check (D4); returns the pre-verified
  answer/citations/as_of on hit, else `None`. Log gray-band near-misses (FAQ_CACHE §3)
  — a simple logging call is sufficient, no new store.
- `src/rag/orchestration/__init__.py`
- `src/rag/orchestration/planner.py` — thin state machine: `plan(cfg, question) ->` runs
  frame → classify → route, returns the per-request retrieval config + hints + intent;
  used by `api.py`. Also exposes the verify step invocation. Enforces
  `ORCHESTRATION_MAX_LLM_CALLS` budget.
- `src/rag/orchestration/intents.py` — `frame_query` + `classify_intent` (D13) and the
  acronym glossary + hint regexes.
- `src/rag/orchestration/router.py` — `route(intent, hints) -> {rag_mode, top_k, top_n,
  filters}` (D8). Maps only to real modes.
- `src/rag/orchestration/verify.py` — `verify_answer(answer, context, intent, topic) ->
  {grounded, claim_support_map, unsupported_claims, missing_elements, declined, note}`
  (D10–D12) + the mandatory-element table (F2/D11) + `format_citations(chunks)`
  (`citation_formatter`, D... — small; may live here or in its own module — implementer's
  call, keep it one small function).
- `scripts/seed_faq.py` — build `data/faq.db` from `data/faq_seed.yaml` (D1 embed reuse;
  idempotent; PyYAML).
- `data/faq_seed.yaml` — committed curated FAQ set (AC-11).
- `tests/test_faq_embed.py`, `tests/test_faq_matcher.py`, `tests/test_orchestration_skills.py`,
  `tests/test_chat_stream_orchestration.py`, `tests/test_faq_staleness_r5.py`
  (split as convenient; cover AC-1,3,4,5,6,7,8,10).

**Modify (surgical — do not rewrite shared paths):**
- `src/rag/config.py` — add env-driven fields: `orchestration` (`ORCHESTRATION`, default
  **false**, D6), `faq_cache` (`FAQ_CACHE`, default true), `faq_sim_threshold`
  (`FAQ_SIM_THRESHOLD`, default **0.83**, D3), `faq_topic_crosscheck`
  (`FAQ_TOPIC_CROSSCHECK`, default true), `faq_stale_policy` (`FAQ_STALE_POLICY`, default
  `suppress`), `verify_answers` (`VERIFY_ANSWERS`, default true), `faq_db_path`
  (default `data/faq.db`), `orchestration_max_llm_calls` (`ORCHESTRATION_MAX_LLM_CALLS`,
  default e.g. `2`). Follow the existing `_b()`/`os.getenv` pattern exactly.
- `src/app/api.py::chat_stream.gen()` — insert Tier-1 FAQ fast-path before Tier-2;
  branch the retrieve step on `CONFIG.orchestration`; add the buffered verify + new
  `verification` SSE event; keep the iter-2 body as the untouched `else`/tail (D9, D10).
  **Do not** touch the pre-existing `ponytail:` comments/text in this file.
- `src/etl/rules.py` and/or `src/etl/pipeline.py` — add R5 flagging after a successful
  R1/R4 upsert (D14): flag matching FAQ entries stale + write an `R5`/`flag_stale`
  provenance row. Keep it a small, isolated addition; the ETL happy path and watermark
  semantics (R8) must be unchanged.
- `scripts/eval.py` — extend for the on-vs-off comparison (AC-9). (Also acceptable: a new
  `scripts/eval_orchestration.py` that imports the gold set.) Fix the hardcoded "naive
  baseline" label wart only if you touch that line anyway (iter-1 tech-debt) — optional.

---

## Interfaces / signatures (contracts the senior-dev implements to)

```python
# src/rag/faq/embed.py
def embed_query(text: str, model_name: str | None = None) -> "np.ndarray":  # (384,), float32, L2-normalized
def embed_queries(texts: list[str], model_name: str | None = None) -> "np.ndarray":  # (n,384)

# src/rag/faq/matcher.py
class FaqHit(TypedDict):  # or a small dataclass
    id: str; answer: str; citations: list[dict]; as_of: str | None; score: float
def match(cfg: RagConfig, framed_query: str, hints: dict) -> "FaqHit | None"
    # hints = {"citation_hint": str|None, "numeric_hint": str|None, "glossary_expansions": [...]}

# src/rag/orchestration/intents.py
def frame_query(question: str) -> dict
    # -> {"framed_query": str, "citation_hint": str|None, "numeric_hint": str|None,
    #     "glossary_expansions": list[str]}
def classify_intent(framed: dict) -> dict
    # -> {"intent": str, "confidence": float}   intent ∈ {definitional,numeric,procedural,
    #                                            cross-reference,change,citation-lookup}

# src/rag/orchestration/router.py
def route(intent: str, hints: dict) -> dict
    # -> {"rag_mode": str, "top_k": int, "top_n": int, "filters": dict}
    #    rag_mode ∈ {"naive","hybrid","hybrid_rerank"} ONLY

# src/rag/orchestration/verify.py
def verify_answer(answer: str, context: str, intent: str, topic: str | None = None) -> dict
    # -> {"grounded": bool, "claim_support_map": dict, "unsupported_claims": list[str],
    #     "missing_elements": list[str], "declined": bool, "note": str}
def format_citations(chunks: list[dict]) -> list[dict]   # citation_formatter

# src/rag/orchestration/planner.py
def plan(cfg: RagConfig, question: str) -> dict
    # -> {"cfg": RagConfig (per-request, via dataclasses.replace), "intent": str,
    #     "hints": dict}   # the retrieve step calls retrieve(result["cfg"], question)

# src/rag/faq/store.py  (mirror cache.py/state.py: stdlib sqlite3, CREATE TABLE IF NOT EXISTS)
def upsert_entry(cfg, entry: dict, embeddings: "np.ndarray") -> None
def iter_entries(cfg) -> list[dict]           # includes deserialized embeddings + stale flag
def flag_stale(cfg, citation: str) -> int     # returns # entries flagged
def is_stale(cfg, entry_id: str) -> bool
```

New SSE event emitted by `/chat_stream` (orchestrated path only):
`event: verification` · `data: {"grounded": bool, "declined": bool,
"unsupported_claims": [...], "missing_elements": [...], "note": "..."}`.
Existing `token` / `citations` / `done` events and their shapes are **unchanged**.

FAQ `faq_seed.yaml` entry shape (mirror FAQ_CACHE §2):
```yaml
- id: faq-ctr-threshold
  canonical_question: "What is the CTR filing threshold?"
  paraphrases: ["when do I file a CTR", "currency transaction report dollar limit"]
  answer: "<pre-verified answer text with an inline 31 CFR cite>"
  citations: [{source: ecfr, citation: "31 CFR 1010.311", url: "...", as_of: "2026-06-15"}]
  topic_keys: ["1010.311", "CTR"]
  verified_by: curator
  as_of: "2026-06-15"
```

---

## Edge cases (must be handled)

- **FAQ `faq.db` absent** (fresh checkout, seed not run): matcher returns `None`
  gracefully (no crash), flow falls through to Tier-2/retrieval. `/corpus_status` and
  `/chat_stream` must not 500 because `faq.db` is missing.
- **Empty question** → still 400 (unchanged), before any FAQ/embed work.
- **FAQ hit whose stored citation was invalidated** (R5 stale) → suppressed, not served.
- **Embedding model unavailable / offline** (no cached weights): matcher must degrade to
  a miss (wrap the embed call; on failure, log + return `None`) so the app still answers
  via retrieval. Same defensive posture as `models.available()`.
- **Router filter fetch returns nothing** (citation-lookup for a citation not in corpus)
  → fall back to the intent's semantic mode (D8a), don't emit an empty answer.
- **Verifier on a legitimately-empty context** (no citations retrieved): the existing
  "No matching regulatory text" branch already handles this **before** generation —
  verify is not reached; keep that branch first (unchanged).
- **`ORCHESTRATION=true` but LLM budget exhausted**: planner degrades to heuristic-only
  framing/classification and lexical-only verification (no decline-on-budget); never
  blocks the answer (§5 graceful degradation).
- **Per-request `RagConfig`**: use `dataclasses.replace` (config is `frozen=True`); do
  not mutate `CONFIG`. Do not let an orchestrated `top_k`/`top_n` change leak into the
  process-global `CONFIG`.
- **`glass`/gray-band near-miss logging** must not throw if logging is misconfigured —
  best-effort only.

---

## Patterns to follow (mirror existing code)

- **Dict-dispatch registries** like `factory.py::_MODES` and `rules.py` for the
  intent→route table and any skill registry.
- **Lazy `@lru_cache(maxsize=1)` singletons** for expensive loads (embedding model,
  reranker) — exactly like `factory.py::_reranker` and `models.py::_load`.
- **SQLite modules** mirror `src/rag/cache.py` and `src/etl/state.py`: one `_conn()`,
  `CREATE TABLE IF NOT EXISTS` on first use, parameterized SQL only, no ORM, connection
  closed in `finally`.
- **Per-request config** via `dataclasses.replace(CONFIG, ...)` — as in
  `tests/test_chat_stream_cache.py::_tmp_cfg`.
- **Tests**: real Flask test client + SSE parsing helper (`_events`) from
  `tests/test_chat_stream_cache.py`; monkeypatch `CONFIG`/`models`/`retrieve`; each test
  uses its own tempdir-backed DB so nothing touches real `data/*.db`.
- **Retrieval never forks the serving path** — the orchestrator only *selects*; it calls
  the same `retrieve()` (ARCHITECTURE §3).
- **No `ponytail:` comments / no "ponytail" token** anywhere new (see conventions note).

---

## Out of scope (do NOT build this iteration)

- **`change_resolver` skill** and any temporal/"what changed" timeline assembly —
  deferred with reason (D5). The `change` **intent** is still classified/routed, but no
  bespoke timeline is produced. (Iteration 4's timeline view is conditional on this.)
- **`graph` retrieval mode / LightRAG / `graph_lightrag.py`** — not built; router falls
  back to `hybrid_rerank` for cross-reference (D8). No `build_graph*.py`.
- **R6 (graph rebuild sync)** and **R7 (FFIEC ingest / `loaders/ffiec.py`)** — backlog
  Out-of-scope for iter-3 (only pull in if iter-1 built the graph loader, which it did
  not). No FFIEC.
- **R5 `reverify_inline` policy** — only `suppress` is built (D14); non-`suppress`
  values accepted but treated as `suppress` with a tech-debt note.
- **R4b eCFR removed-section deletion** — deferred (D15).
- **Cognitus UI work** (rendering the `verification`/decline state, `as_of` styling) —
  Iteration 4. This iteration only **emits** the `verification` SSE event; it does not
  restyle `src/app/static/`.
- **Promoting `hybrid_rerank` (or `ORCHESTRATION=true`) to the shipped default without
  the AC-9 measurement** — the default ships as decided in D6; a flip requires recorded
  evidence.
- **New pip dependencies**, requirements pinning, Dockerfile, CI workflow files — Phase 5.
- **Answer-cache eviction/TTL**, FedReg XML full-text fetch, count-index — carried
  tech-debt, not this iteration.

---

## Definition of done for this iteration

All of AC-1…AC-12 pass; `data/faq_seed.yaml` is committed and `scripts/seed_faq.py`
builds `data/faq.db` from it idempotently; `ORCHESTRATION=false` + `FAQ_CACHE=false`
reproduces iter-2 behavior byte-for-byte (AC-2); the on-vs-off eval and every "Decision
made" divergence from the docs (threshold 0.83 vs 0.92, ORCHESTRATION default false,
change_resolver/reverify_inline/R6/R7/R4b deferrals, verifier mechanism) are recorded in
`.build/iter-3/changes.md`; `progress.md` notes the carried-forward deferrals. No
`ponytail:` marker or the literal word "ponytail" appears in any new or modified file.
