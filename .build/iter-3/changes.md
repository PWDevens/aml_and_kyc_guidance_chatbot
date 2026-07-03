# Iteration 3 — Implementation summary

**Scope:** Phase 3 — local-first orchestration layer (frame → classify →
route → retrieve → verify) + semantic FAQ Tier-1 cache, wired in front of the
existing exact-match Tier-2 cache and the iter-2 single-mode retrieve/generate
path. Implements every D1–D15 decision from `.build/iter-3/spec.md` as
written; no re-planning was done.

---

## Files created

- `src/rag/faq/__init__.py` — empty package marker.
- `src/rag/faq/embed.py` — `embed_query`/`embed_queries` (D1). `@lru_cache(maxsize=1)`-loaded
  `SentenceTransformer` singleton keyed on model name, `normalize_embeddings=True`
  so cosine similarity reduces to a dot product. Same lazy-singleton pattern as
  `factory.py::_reranker` / `models.py::_load`.
- `src/rag/faq/store.py` — SQLite FAQ store, mirrors `cache.py`/`state.py` exactly
  (one `_conn()`, `CREATE TABLE IF NOT EXISTS`, parameterized SQL, connection
  closed in `finally`, no ORM). One `faq_entries` table: id, canonical_question,
  paraphrases_json, answer, citations_json, topic_keys_json, embeddings BLOB
  (float32, reshaped via a stored `n_vectors` count), verified_by, as_of, stale,
  stale_reason. `upsert_entry`, `iter_entries`, `flag_stale`, `is_stale`.
- `src/rag/faq/matcher.py` — `match(cfg, framed_query, hints) -> FaqHit | None`.
  Max-over-paraphrases cosine (D2), `FAQ_SIM_THRESHOLD` (D3), topic-key
  cross-check (D4). Defensive: absent/unreadable `faq.db` or embedding-model
  failure both degrade to a graceful miss (never raises), matching
  `models.available()`'s posture. Gray-band near-misses get a best-effort
  `log.info` line (swallowed if logging is misconfigured).
- `src/rag/orchestration/__init__.py` — empty package marker.
- `src/rag/orchestration/intents.py` — `frame_query` + `classify_intent` (D13),
  the acronym glossary (15 entries: CTR, SAR, CDD, CIP, BSA, UBO, MSB, EDD,
  PEP, FBAR, AML, KYC, FinCEN, OFAC, SDN), citation-hint regex
  (`\d{1,3}\s*CFR\s*\d+\.\d+`, normalized to `"31 CFR 1010.311"` form),
  numeric-hint regex, and chit-chat stripping. Pure heuristic, zero LLM calls.
- `src/rag/orchestration/router.py` — `route(intent, hints) -> {rag_mode, top_k,
  top_n, filters}` (D8/D8a/D8b). Dict-dispatch table over the 6 intents, all
  mapping to `{"naive","hybrid","hybrid_rerank"}` only; an `assert` guards the
  D8 hard constraint at the source. citation-lookup emits `filters={"citation":
  ...}` when a citation_hint is present.
- `src/rag/orchestration/verify.py` — `verify_answer` (D10–D12) +
  `format_citations` (citation_formatter). Lexical-overlap-only grounding
  (token-set containment per claim/sentence vs. context tokens); no LLM call
  (see "D12" section below for why). F2 mandatory-element completeness table
  (D11) covers CIP (name/DOB/address/ID number — the debt's canonical
  example), plus SAR-timing and CTR-threshold (added because they were cheap,
  one line each, per the spec's "only if cheap" allowance).
- `src/rag/orchestration/planner.py` — `plan(cfg, question) -> {cfg, intent,
  hints, confidence, filters, framed_query, budget}` (D8b), `frame_query_hints`
  (framing-only, used by the FAQ fast-path), `citation_fetch` (D8a's new
  direct-Chroma-`get` helper — does **not** change `factory.retrieve`'s
  signature), and a small `Budget` class enforcing
  `ORCHESTRATION_MAX_LLM_CALLS`.
- `scripts/seed_faq.py` — builds `data/faq.db` from `data/faq_seed.yaml` using
  the same `embed_queries` helper the matcher uses (D1 reuse — required for
  cosine to be meaningful). Idempotent via `INSERT OR REPLACE` on entry id.
- `data/faq_seed.yaml` — 29 curated FAQ entries (see "FAQ seed" section below).
- `tests/test_faq_embed.py`, `tests/test_faq_matcher.py`,
  `tests/test_orchestration_skills.py`, `tests/test_chat_stream_orchestration.py`,
  `tests/test_faq_staleness_r5.py` — new test coverage, 57 tests total.

## Files modified (surgical)

- `src/rag/config.py` — added `orchestration` (default **false**, D6),
  `faq_cache` (default true, D7), `faq_db_path`, `faq_sim_threshold` (default
  **0.83**, D3), `faq_topic_crosscheck` (default true, D4),
  `faq_stale_policy` (default `suppress`, D14), `verify_answers` (default
  true, D7), `orchestration_max_llm_calls` (default `2`). Exact `_b()`/
  `os.getenv` pattern as the existing fields; pre-existing `ponytail:`
  docstring line untouched.
- `src/app/api.py` — added the Tier-1 FAQ fast-path (before Tier-2, D9 step 1)
  and an orchestrated branch (D9 steps 2–6). The **entire iter-2 function body
  is preserved verbatim** as `_gen_iter2_path()`, called from the `else`
  branch of `if CONFIG.orchestration`. Added `verification` SSE event
  (orchestrated + `verify_answers` only). Pre-existing `ponytail:` comment
  (line 98, extractive-fallback note) untouched, not moved, not reworded.
- `src/etl/rules.py` — added `classify_faq_staleness(citation) -> {"rule_id":
  "R5", "action": "flag_stale", "citation": ...}` (D14). Pure classification
  stamp, mirrors `classify_ecfr_section`'s split of "what rule applies" vs.
  "what gets written."
- `src/etl/pipeline.py` — added `_flag_faq_stale()` (best-effort, never
  raises) called after a successful R1 (fedreg rule) upsert in `_run_fedreg`
  and after every R4 (ecfr section) upsert in `_run_ecfr`. R8 atomicity/
  watermark semantics and the existing happy path are untouched — this is a
  pure addition after the existing `state.record(...action="upsert"...)`
  calls, isolated in its own try/except.
- `scripts/eval.py` — added `run_comparison()` / `--compare` CLI flag for
  AC-9 (on-vs-off orchestration comparison). Original `run()` (plain-mode
  baseline) is unchanged in behavior; only its summary line was generalized
  from a hardcoded `"naive baseline"` label to `f"{CONFIG.rag_mode} baseline"`
  since the function was touched anyway (iter-1's noted tech-debt wart,
  explicitly "optional" — fixed opportunistically, not a scope expansion).
- `tests/test_chat_stream_cache.py` — `_tmp_cfg()` now also points
  `faq_db_path` at a tempdir path (previously only `cache_path`). **Required**
  fix, not a weakening: the real, now-seeded `data/faq.db` (AC-11) was
  intercepting these tests' questions (e.g. "What is the CTR dollar
  threshold?") via the new Tier-1 FAQ fast-path, since `CONFIG.faq_cache`
  defaults to `true` (D7) and these tests only ever patched `cache_path`.
  Pointing `faq_db_path` at an empty tempdir path restores the original
  "Tier-1 absent → graceful miss → exercise the Tier-2 path under test"
  behavior these tests were written for. All 6 tests pass unchanged in
  assertions/logic; only the fixture's DB isolation was extended to cover the
  new DB Phase 3 introduces — consistent with the file's own stated
  "each test uses its own tempdir-backed DB" convention.

---

## Decisions implemented as specified (confirmed, with divergence notes)

- **D1 (embed_query):** implemented exactly as specified — `bge-small-en-v1.5`,
  `normalize_embeddings=True`, `@lru_cache(maxsize=1)`. Verified locally:
  first call loads the model (~13s observed), subsequent `encode()` calls are
  sub-100ms, vectors are 384-dim float32 with norm ≈ 1.0 (tested in
  `test_faq_embed.py`).
- **D2 (max-over-paraphrases matching):** implemented exactly — `matcher.py`
  embeds every stored canonical+paraphrase string per entry and scores a query
  as `max(cosine(query, e) for e in entry_vectors)`. Verified: a genuine
  (non-verbatim) paraphrase like "How much cash triggers a CTR filing
  requirement at a bank?" scores 0.86+ against `faq-ctr-threshold`'s vector
  set, correctly above threshold.
- **D3 (threshold = 0.83, not 0.92):** shipped as specified.
  `RagConfig.faq_sim_threshold` defaults to `0.83`, overridable via
  `FAQ_SIM_THRESHOLD`. Confirmed the doc's proposed `0.92` would indeed miss
  real paraphrases: spot-checking against the shipped seed, several genuine
  paraphrases score in the 0.83–0.90 band (e.g. "what info do I need to give
  the bank to open an account" → `faq-cip-identifying-info` at 0.891), which
  `0.92` would have missed entirely. **This is the doc-vs-shipped divergence
  the spec required recording: docs/FAQ_CACHE.md proposes 0.92; shipped is
  0.83, per D3's explicit instruction.**
- **D4 (topic-key cross-check, mandatory, default ON):** implemented exactly.
  `FAQ_TOPIC_CROSSCHECK` defaults `true`. Verified: a query wording close to
  the CTR entry's paraphrases but carrying an explicit, contradicting citation
  hint (`"31 CFR 1010.230 currency transaction report dollar limit"`) is
  correctly rejected even though raw cosine similarity might otherwise pass —
  see `test_citation_hint_mismatch_forces_miss_even_above_threshold`. When
  crosscheck is disabled, the same query with no contradicting hint hits
  correctly on threshold alone (`test_crosscheck_disabled_allows_threshold_alone_to_decide`).
- **D5 (change_resolver deferred):** not built. The `change` intent is
  classified (keyword: "changed"/"latest"/"new rule"/"amended"/"recently"/
  "updated") and routed to `hybrid_rerank`, same as the doc's fallback
  intent. No temporal-diff assembly of any kind exists in this codebase.
  Deferral reason recorded here, in `test_orchestration_skills.py`'s module
  docstring, and in `.build/progress.md`.
- **D6 (ORCHESTRATION default false):** shipped `false`. See the "AC-9" section
  below for the real numbers and the explicit reasoning for not flipping the
  default despite a positive measured delta.
- **D7 (FAQ_CACHE=true, VERIFY_ANSWERS=true-but-orchestration-gated):**
  implemented exactly. `api.py`'s FAQ fast-path check is `if CONFIG.faq_cache`
  with no dependency on `CONFIG.orchestration`; the `verification` SSE event
  only fires inside `_gen_orchestrated_path`, so `verify_answers` is only ever
  consulted when orchestration is also on — confirmed by
  `test_orchestrated_path_off_skips_verification_event`.
- **D8/D8a/D8b (routing matrix, citation direct-fetch, advisory-only router):**
  implemented exactly. `router.py`'s table maps all 6 intents to
  `{"naive","hybrid","hybrid_rerank"}` only (asserted in code, tested in
  `test_router_never_emits_a_mode_outside_real_modes` across all 6 intents,
  including the cross-reference → hybrid_rerank and change → hybrid_rerank
  fallbacks). `planner.citation_fetch` is a **new** function — `factory.py`'s
  `retrieve()` signature is untouched. The orchestrated path in `api.py` tries
  the direct fetch first when a citation filter exists, falls back to
  `retrieve()` on an empty fetch (D8a edge case) — tested in
  `test_citation_lookup_falls_back_to_semantic_mode_when_fetch_empty`.
  `planner.plan()` only *returns* a per-request cfg; `api.py` calls the real
  `retrieve()` itself — no forked serving path.
- **D9 (wiring order, byte-identical collapse):** implemented exactly as the
  6-step sequence. The literal iter-2 function body is preserved as
  `_gen_iter2_path()` (a straight cut-paste, zero edits) and is the only code
  path reached when `orchestration=False`. AC-2 tests
  (`test_collapse_*` in `test_chat_stream_orchestration.py`) assert
  event-shape and event-order equality against the iter-2 behavior for
  cache-hit replay, generated-answer, extractive-fallback, no-citation, and
  empty-question-400 cases; the original `test_chat_stream_cache.py` suite
  (6 tests) also still passes unmodified in assertions.
- **D10 (buffer-then-verify, decline semantics):** implemented exactly.
  Tokens still stream live; verification runs only after the full answer is
  buffered; the `verification` SSE event is emitted **before** `citations`
  (asserted in `test_orchestrated_path_emits_verification_event_before_citations`).
  A `grounded=False` answer is not written to Tier-2
  (`test_orchestrated_path_declined_answer_not_cached`); a non-empty
  `missing_elements` alone does **not** decline
  (`test_missing_elements_does_not_by_itself_decline`) — this policy choice
  (only ungrounded triggers hard decline; incompleteness only annotates) is
  the D10-specified behavior, implemented as specified, not altered.
- **D11 (F2 completeness table):** implemented. CIP's four elements (name,
  date of birth, address, identification number) per 31 CFR 1020.220, plus
  SAR-timing (30 calendar days) and CTR-threshold ($10,000) added because
  each was a single dict entry (cheap, per the spec's allowance). No LLM
  call — pure substring/synonym-set check. `test_verifier_f2_completeness_*`
  in `test_orchestration_skills.py` directly closes F2 per AC-5.
- **D12 (lexical-overlap grounding, LLM-escalation not built):** implemented
  the primary lexical-only mechanism as specified (token-set containment
  per claim vs. context). **The optional LLM-escalation path for gray-band
  claims is NOT implemented this iteration** — gray-band claims (weak but
  nonzero overlap) are treated as "grounded-with-caveat" (labeled in
  `unsupported_claims`, not declined), which is exactly the documented
  over-budget fallback behavior (D12: "Over budget → treat gray-band claims
  as grounded-with-caveat"). Since no LLM call is ever attempted, this is
  effectively always the "over budget" branch — a deliberate simplification:
  building a real Phi-4 entailment-prompt escalation path was judged
  unnecessary scope for this iteration given §5's "default posture is
  lexical-only" framing and D13's explicit allowance to stub/minimize the
  LLM fallback if time-constrained. `planner.Budget` still exists and is
  real, tested infrastructure (`test_budget_tracks_spend_and_refuses_over_limit`)
  so a future LLM-escalation path has a correct place to check spend against.
  **Ceiling:** if verifier recall/precision on real generated answers proves
  inadequate in practice, wire `Budget.spend()` into a Phi-4 entailment call
  in `verify.py`'s gray-band branch — the budget plumbing is already there.
- **D13 (heuristic-first framer/classifier):** implemented as the *only* path
  — no LLM fallback exists at all (fully stubbed/absent, stated honestly here
  per the spec's allowance). The heuristic path is complete: acronym
  glossary (15 entries), citation/numeric hint regexes, chit-chat stripping,
  and a 6-way keyword classifier with `definitional` as the default. All
  tested in `test_orchestration_skills.py` (18 framer/classifier tests).
- **D14 (R5 staleness, suppress-only):** implemented exactly. R5 fires after
  a successful R1 (fedreg final rule) or R4 (ecfr section) upsert in
  `pipeline.py`, flags any FAQ entry whose `topic_keys`/`citations` reference
  the upserted citation (matched on both the full `"31 CFR 1010.311"` form
  and the bare `"1010.311"` section suffix — see the store.py bug-fix note
  below), and writes an `R5`/`flag_stale` provenance row. The matcher honors
  `stale=1` under `FAQ_STALE_POLICY=suppress` (default) and treats any other
  policy value as suppress too — confirmed by
  `test_non_suppress_policy_is_still_treated_as_suppress`. `reverify_inline`
  is not built; this is accepted, bounded tech debt with the stated upgrade
  path (couples ETL to the generate+verify loop — a real scope boundary, not
  an oversight).
- **D15 (R4b deferred):** not built, not touched. Stays open in
  `.build/progress.md`.

---

## Bug found and fixed during implementation

`store.flag_stale()` originally matched the passed `citation` argument only
against stored `topic_keys`/`citations` *verbatim*. Since `data/faq_seed.yaml`
conventionally stores the **bare section** (`"1010.311"`) in `topic_keys`
while `pipeline.py`'s R5 call passes the **full citation string**
(`"31 CFR 1010.311"`), the two representations never matched and
`flag_stale` silently flagged 0 entries in the common case. Fixed by also
checking the bare-section suffix (`citation.split()[-1]`) against both
`topic_keys` and the full citation strings. Caught by a manual scratch check
before writing the R5 test suite, not by a failing test — the R5 test suite
was written with `citations` populated (which happened to match verbatim),
so it would not have caught this on its own; the fix and a targeted
verification were done before finalizing `test_faq_staleness_r5.py`.

---

## AC-9 — orchestration on-vs-off eval (real numbers)

Run: `py -3.12 -m scripts.eval --compare` against the real (unmodified,
read-only-queried) `data/chroma` index and the 25-item gold set
(`data/eval/gold.jsonl`).

```
ORCHESTRATION=false (single default mode=naive, top_k=5):  hit@k=0.92  term_recall=0.96
ORCHESTRATION=true  (per-intent routed mode/top_k):         hit@k=0.96  term_recall=1.00

Delta (on - off): hit@k=+0.04  term_recall=+0.04
```

(`py -3.12 -m scripts.eval` alone reproduces the same off-numbers as the
pre-existing plain baseline run: `naive baseline hit@5=0.92 term_recall=0.96`
— consistent, not a fluke of the comparison harness.)

**Recommendation: keep `ORCHESTRATION=false` as the shipped default for now,
despite the positive delta.** Reasoning:
1. The delta is real and unambiguous in the metric it measures (retrieval
   relevance: hit@k and term_recall), and would, on its own, satisfy D6's
   "flip only after a measured win" bar.
2. However, this AC-9 comparison is **retrieval-only** — it calls `retrieve()`
   directly (via `planner.plan()`'s resulting per-request cfg) and never
   exercises generation, buffered verification, or the FAQ tier. It does not
   measure the orchestrated path's added per-request cost: an extra
   frame/classify/route pass (cheap, heuristic-only, sub-millisecond) plus,
   when `VERIFY_ANSWERS=true`, a full answer-buffering + lexical-verification
   pass after every generation on a CPU-slow stack (§5's own framing).
3. D6 explicitly asks for "no latency regression that breaks the demo" as
   part of the flip bar, and this script cannot speak to that — a real flip
   decision needs a comparison that includes end-to-end `/chat_stream`
   latency (generation + verification) on live hardware, not just retrieval
   hit-rate.
4. Given the honest, cautious "off is safe until proven" framing D6 itself
   sets up (mirroring the project's iter-1 naive-vs-hybrid precedent), a
   retrieval-only win is treated as a strong, positive signal but not
   sufficient standalone justification to flip a default that changes every
   answer's code path. **This is a live decision for Iteration 4 to revisit
   with a fuller (latency-inclusive) measurement**, not a closed question —
   flagged explicitly in `.build/progress.md`.

The per-intent routing improvement mostly comes from `numeric`/`definitional`/
`procedural` questions being routed to `hybrid_rerank` (iter-1's own measured
best-ranking mode) instead of always using the process-global `naive`
default — consistent with iter-1's own finding that `hybrid_rerank` wins on
term-recall and average rank, just never promoted to default absent a
deliberate evidence-based decision (which this eval run is evidence *toward*,
for whichever iteration makes that call).

---

## FAQ seed — actual count and quality note

**29 curated entries**, each with a real 31 CFR citation confirmed present
in the built corpus (verified read-only against `data/chroma` — the citation
list was pulled directly via `get_collection(CONFIG).get(include=["metadatas"])`
before writing any seed content, and several entries' answer text was
hand-transcribed from the actual retrieved eCFR section text, not generated
or guessed). This is close to, but modestly under, the spec's "target
~30–50" range. **Honest gap note (per the spec's explicit instruction to
state this honestly rather than pad):** 29 was where curation naturally
stopped after covering every gold-set citation (`data/eval/gold.jsonl`) plus
a reasonable set of adjacent high-value FAQ topics (CIP, SAR, BSA/AML program,
CDD, beneficial ownership, FBAR) with real, verified answer text and correct
citations. All 29 are well above the "≥12 high-quality" floor and every
entry's `citations` field was checked against the live corpus. No filler/
low-quality entries were added to hit a round number.

`scripts/seed_faq.py` was run for real against `data/faq.db` (not a tempdir)
as required by AC-11 — this is the spec-required committed artifact, not a
casual sanity run against protected data. Verified idempotent: two
consecutive runs both produce exactly 29 stored entries.

---

## Deliberate simplifications (with ceilings)

- **No LLM-escalation path for gray-band verifier claims** (see D12 above) —
  ceiling: wire `Budget.spend()` + a Phi-4 entailment prompt into
  `verify.py`'s gray-band branch if lexical-only precision/recall proves
  inadequate on real generated answers.
- **No LLM fallback for `intent_classifier`/`query_framer`** (D13) — fully
  absent, not stubbed. Ceiling: add a Phi-4 few-shot fallback gated on
  `Budget.has_budget()` for the "genuinely ambiguous input" case the spec
  describes, if the heuristic default-to-`definitional` proves too coarse on
  real traffic.
- **`router.py`'s `top_n` field is currently advisory-only** — `RagConfig`
  has no `top_n` field (only `retrieval_top_k`), so `route()`'s `top_n` value
  is computed and returned but not yet consumed by `_hybrid_rerank`'s
  internal pool-size logic (which derives its own pool size from
  `retrieval_top_k * 4`). Not a correctness bug (retrieval still runs
  correctly via `retrieval_top_k`), just unused headroom. Ceiling: thread
  `top_n` into `factory.py`'s `_hybrid`/`_hybrid_rerank` pool-size calculation
  as an explicit override if per-intent pool tuning becomes valuable.
  Left as-is per "do not add unrequested abstractions" / minimal diff — the
  interface contract (`route()` returns `top_n`) is satisfied per the spec's
  signature; wiring it deeper into `factory.py` was not requested and
  `factory.py`'s existing pool-size heuristic already works.
- **R5 provenance row is only written when `flag_stale` actually flags ≥1
  entry** — a successful upsert of a citation with *no* referencing FAQ entry
  writes no R5 row at all (rather than a `chunks_changed=0`/no-op row every
  single time). This keeps the provenance ledger from being flooded with a
  no-op R5 row on every one of the corpus's ~475 chunks' worth of ETL
  upserts when only 29 FAQ entries exist to ever match. Ceiling: if a future
  iteration needs a complete R5 audit trail (including "checked, no match"),
  change the `if n:` guard in `pipeline._flag_faq_stale` to always record.
- **`eval.py`'s naive-baseline label fix** — touched opportunistically since
  the file was modified anyway for AC-9 (iter-1's noted wart, explicitly
  optional per the spec). One-line change (`f"{CONFIG.rag_mode} baseline"`
  instead of a hardcoded `"naive baseline"`), zero behavior change to the
  metrics themselves.

## Tests-worth-flagging for the debugger/tester stage

- `test_chat_stream_orchestration.py`'s AC-2 collapse tests assert **exact
  event-order sequences** (`["token", "citations", "done"]` etc.) in addition
  to token/citation content — worth an adversarial pass to confirm no other
  ordering-sensitive edge case (e.g. multiple citation chunks, multi-chunk
  streamed tokens with unusual boundaries) is missed.
- The FAQ matcher's threshold/cross-check interaction (D3+D4) is inherently
  probabilistic (real embedding model, not a stub) — `test_faq_matcher.py`'s
  assertions were chosen from measured, reproduced scores against the actual
  shipped seed content, but a different local embedding-model cache version
  could shift scores slightly. If a test flakes, check the *actual* printed
  score against `FAQ_SIM_THRESHOLD` before assuming a logic bug.
- `verify.py`'s lexical-overlap thresholds (`_GROUNDED_THRESHOLD=0.5`,
  `_GRAY_LOW_THRESHOLD=0.2`) are tuned loosely, not empirically measured
  against a labeled adversarial set the way D2/D3's cosine thresholds were.
  Worth a dedicated adversarial pass (AGENT_ORCHESTRATION §7) beyond the
  4 grounded/ungrounded/incomplete cases already covered.
- The real `data/faq.db` now exists and is seeded (29 entries) — any test
  that patches `src.app.api.CONFIG` without also overriding `faq_db_path`
  (or setting `faq_cache=False`) will be intercepted by the Tier-1 fast-path
  if the question resembles a seeded FAQ. `test_chat_stream_cache.py` was
  already fixed for this; double-check any *new* test added downstream
  follows the same tempdir-isolation pattern.

---

## Suite status

`py -3.12 -m pytest tests/ -q` → **104 passed** (47 carried unchanged from
iter-2 + 57 new: 4 embed, 6 matcher, 28 orchestration skills incl. planner,
6 R5 staleness, 13 chat_stream orchestration integration). No existing test
was weakened — `test_chat_stream_cache.py`'s one required fixture change
(faq_db_path isolation) is documented above with the reason. No
`ponytail:`/"ponytail" token appears in any new or modified file (verified
by direct grep across every new file and a diff-scope grep of the 6 modified
files, confirming only the pre-existing occurrences remain, unchanged, in
their original 4 locations: `config.py:3`, `api.py:2`, `api.py:98`,
`eval.py:4`).
