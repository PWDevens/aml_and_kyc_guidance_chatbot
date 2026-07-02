# Iteration 1 — Test results

RESULT: PASS

Full suite: `py -3.12 -m pytest tests/ -q` → **19 passed** in ~37s (0 failed, 0
skipped), run against the already-built 403-chunk index (eCFR + FedReg). Also
verified each new file both under pytest and standalone via
`py -3.12 -m tests.<module>` (the repo's actual standalone-run convention —
see note under "Observations" below).

No fixes were needed — the suite was green on the first run, so the bounded
self-heal budget (2 attempts) was not used.

---

## What was tested (new files)

### `tests/test_chat_stream_cache.py` — AC-6 (exact-match answer cache) end to end

The senior-dev's `tests/test_cache.py` only unit-tests `src/rag/cache.py` in
isolation. Nothing exercised the actual `/chat_stream` wiring described in
changes.md end to end via the Flask test client, so this file adds that,
plus the spec's explicit edge cases:

- `test_generated_answer_is_cached_and_replayed_on_second_call` — happy path.
  First call (cache miss) retrieves for real and generates via a mocked
  `models.stream`; asserts retrieval + generation each ran exactly once and a
  cache row was written. Second call, same question **differently cased and
  padded with whitespace**, asserts an identical answer/citations stream back
  and that `retrieve`/`models.stream` were **not** called again (call counts
  stay at 1) — i.e. retrieval and generation are genuinely skipped on a hit,
  not just "cache exists somewhere."
- `test_extractive_fallback_is_not_cached` — spec edge case: when
  `models.available()` is false, the extractive fallback answer streams but
  `cache.get(...)` afterward returns `None`.
- `test_no_matching_text_is_not_cached` — spec edge case: when retrieval
  returns zero citations, the "No matching regulatory text..." message
  streams but is not cached either.
- `test_answer_cache_disabled_never_reads_or_writes_cache` — `ANSWER_CACHE`
  gate: with `CONFIG.answer_cache=False`, a pre-seeded stale cache row for the
  same question is ignored (fresh generation streams instead), proving the
  cache is bypassed, not just "empty."
- `test_empty_question_returns_400` — failure case: blank/whitespace-only
  question is rejected before any retrieval/cache/generation work.
- `test_real_generation_end_to_end_grounded_answer_is_cached` — **stronger,
  unmocked** version of the happy path, per the orchestrator's note that live
  generation now genuinely works (the `onnxruntime-genai` `append_tokens()`
  fix in `src/rag/llm/models.py`, made outside this iteration's spec). Runs
  the real Phi-4-mini-instruct-onnx CPU generation stack (~10-15s at
  `max_new_tokens=60`), asserts the real generated answer is grounded
  ("10,000" appears, citation resolves to 1010.311), and that it was written
  to the cache with the exact streamed text. This is a genuinely stronger
  check than a mock: it proves the cache-write path works against real
  generation output shape (a `str`-yielding generator), not an assumed one.
  The mocked tests above are kept too — they isolate cache/retrieval logic
  from generation latency and are what the spec's edge-case guidance
  explicitly allows ("mocking generation to isolate cache logic is fine").

### `tests/test_corpus_breadth.py` — AC-1 (gold set) and AC-2 (corpus breadth)

Neither was covered by an automated test before (changes.md verifies both
manually/by inspection). Added:

- `test_gold_set_size_and_schema` — `data/eval/gold.jsonl` has 20-30 items
  (currently 25) and every item has exactly the three required keys (`q`,
  `expect_citation`, `answer_contains`), all non-empty.
- `test_gold_set_covers_non_ecfr_targets` — at least 3 items target a
  non-eCFR (FedReg/advisory) citation, per AC-1's "at least a few non-eCFR
  targets."
- `test_gold_set_retrieval_runs_clean_naive_mode` — every gold item retrieves
  without raising and hit@k over the full set is >=0.8 (regression guard on
  "`python -m scripts.eval` runs clean," not a re-measurement of AC-4's exact
  numbers — those are already reported with full methodology in changes.md).
- `test_corpus_status_shows_breadth_beyond_ecfr` — `GET /corpus_status`
  reports `indexed` > 105 (the pre-iteration eCFR-only baseline) and the
  Chroma collection's metadata contains at least one non-`ecfr` `source`
  value, matching AC-2's literal wording.
- `test_fedreg_citations_resolve_with_working_url_and_source` — AC-7 check
  specific to the new FedReg corpus slice: at least one non-eCFR gold item's
  retrieved citation has a `url` starting with
  `https://www.federalregister.gov/` and a `source` in the expected set
  (`fedreg_rule`/`fedreg_proposed`/`fincen_advisory`/`fedreg`).

---

## Mapping to acceptance criteria

| AC | Covered by |
|----|------------|
| AC-1 (gold set 20-30, schema, non-eCFR coverage) | `test_corpus_breadth.py` (new) |
| AC-2 (corpus breadth, non-ecfr source present) | `test_corpus_breadth.py` (new) |
| AC-3 (section-aware chunking) | `test_ecfr_chunking.py` (pre-existing, unchanged) |
| AC-4 (naive vs hybrid measured) | Not re-tested here — this is a one-time measurement + decision recorded in changes.md/progress.md, not an ongoing behavioral contract to assert in a unit test. `hybrid`/`hybrid_rerank` modes are exercised indirectly (both are reachable via `_MODES`, same `retrieve()` contract as `naive`, which the other tests call). |
| AC-5 (reranker added only if it fixes a regression) | Same as AC-4 — a one-time measured decision, recorded in changes.md; `hybrid_rerank` mode exists and shares the tested `_format`/`retrieve` contract. |
| AC-6 (exact-match answer cache wired into `/chat_stream`) | `test_cache.py` (pre-existing, unit-level) + `test_chat_stream_cache.py` (new, integration-level, real Flask client) |
| AC-7 (citations resolve correctly, incl. FedReg) | `test_smoke.py` (pre-existing, eCFR/CTR) + `test_fedreg_citations_resolve_with_working_url_and_source` (new, FedReg) |

## Fixes made during self-heal

None. The suite was green on the first run; the 2-attempt self-heal budget
was not needed.

## Anything the senior-PM gate should scrutinize

- **AC-4/AC-5 are not covered by an automated regression test**, by design —
  they're one-time measured decisions (naive vs hybrid; reranker-or-not) that
  changes.md documents with full numbers and methodology. If a future
  iteration wants a standing guard against silently regressing the *decision
  itself* (e.g. someone flips `rag_mode` default without re-measuring), that
  would need a new test asserting `CONFIG.rag_mode == "naive"` — deliberately
  not added here since pinning the default in a test would make the next
  legitimate evidence-based change to it look like a test failure rather than
  a decision to re-evaluate.
- **`test_real_generation_end_to_end_grounded_answer_is_cached` depends on
  the cached Phi-4-mini-instruct-onnx weights being present locally** (same
  dependency `models.available()` already has everywhere else). It's an
  assertion on real model output, so it's marginally less deterministic than
  the rest of the suite in principle (greedy decoding + a fixed prompt makes
  it stable in practice — confirmed twice during this session, same
  grounded answer both times). If this becomes a problem on a CI machine
  without the cached weights, `models.available()` returning `False` would
  make the real generation branch never execute — this test would then fail
  loudly (KeyError on the `citations` event still present, but the "10,000"
  assertion would hit the extractive-fallback text instead) rather than
  silently skip. Worth a `pytest.mark.skipif(not models.available())` guard
  in a future iteration if the test matrix grows to include a
  weights-less environment; not added now since this session's environment
  always has the weights cached and skip-by-default risks masking a real
  regression in exactly the path this test exists to check.
- **Environment note carried forward, not a defect in this iteration**: the
  `onnxruntime-genai` `append_tokens()` fix in `src/rag/llm/models.py` was
  made by the orchestrator outside this iteration's spec/file list (per the
  task's IMPORTANT CONTEXT). It is now exercised for real by the new
  end-to-end generation test above — live generation is confirmed working,
  not just retrieval/cache logic in isolation.
- No `# ponytail:`-style comments were added to any new file, and the word
  does not appear in `tests/test_chat_stream_cache.py` or
  `tests/test_corpus_breadth.py`. Pre-existing `ponytail:` comments in
  `src/**` were left untouched, per the override.

## Files added by this testing pass

- `tests/test_chat_stream_cache.py` (new)
- `tests/test_corpus_breadth.py` (new)

No production code was modified.
