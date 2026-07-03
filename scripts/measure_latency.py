"""AC-3 latency measurement — real wall-clock timings against the actual
running app/stack (in-process Flask test client, same request path a live
server would take; no mocking of retrieve/generate/cache/faq).

Measures three real request classes named in PRD §6/§8:
  1. FAQ Tier-1 hit  — a seeded FAQ question (target: < 1s p50)
  2. Exact-match cache hit (Tier-2) — a repeated novel question, second call
  3. Fresh generation — a novel question through retrieve -> generate on CPU
     (target band: 10-60s)

Method: the FIRST request in a process pays one-time model-load cost
(embedder + reranker + Phi-4 are `lru_cache`-lazy — iter-1 debt, ARCHITECTURE
notes this). This script issues one warm-up call per subsystem before timing,
then reports the median of a few timed repeats, and separately reports the
observed cold (first-call) time so cold vs warm are never conflated.

Run:  python -m scripts.measure_latency
"""
from __future__ import annotations

import statistics
import time

from src.app.api import app
from src.rag.config import CONFIG

FAQ_QUESTION = "What is the CTR filing threshold?"          # seeded FAQ entry (faq-ctr-threshold)
# Deliberately phrased to avoid both the FAQ tier (verified below at import
# time is not needed — checked manually once, see changes.md) and any
# question already present in data/cache.db from a prior run, so the first
# call is a genuine cache MISS.
CACHE_QUESTION = "What is FinCEN's role under the Bank Secrecy Act examination process?"
# Chosen to be gold-set/corpus-answerable but verified NOT to match any of the
# 29 seeded FAQ entries (checked directly against faq_matcher.match before
# use) — otherwise these would silently short-circuit to the Tier-1 FAQ path
# instead of exercising fresh retrieve->generate, as an earlier draft of this
# script did (see changes.md for that finding).
FRESH_QUESTIONS = [
    "What is the effective date of FinCEN's Customer Due Diligence Final Rule amendments?",
    "What penalties can apply for willful failure to file a Report of Foreign "
    "Bank and Financial Accounts?",
    "What is the purpose of the 314(b) voluntary information sharing safe harbor?",
]


def _time_chat_stream(client, question: str) -> float:
    t0 = time.perf_counter()
    resp = client.post("/chat_stream", json={"question": question})
    # drain the SSE stream fully — "first answer/citations" means the full
    # response is realized, not just headers.
    body = resp.get_data(as_text=True)
    t1 = time.perf_counter()
    assert "event: done" in body, f"no done event in response for {question!r}"
    return t1 - t0


def main() -> None:
    client = app.test_client()

    print(f"RAG_MODE={CONFIG.rag_mode}  GENERATE={CONFIG.generate}  "
          f"FAQ_CACHE={CONFIG.faq_cache}  ANSWER_CACHE={CONFIG.answer_cache}  "
          f"ORCHESTRATION={CONFIG.orchestration}\n")

    # --- 1. FAQ Tier-1 hit ---------------------------------------------
    cold_faq = _time_chat_stream(client, FAQ_QUESTION)
    warm_faq = [_time_chat_stream(client, FAQ_QUESTION) for _ in range(3)]
    print(f"[FAQ hit]    cold(first call)={cold_faq:.3f}s   "
          f"warm repeats={['%.3f' % t for t in warm_faq]}   "
          f"warm median={statistics.median(warm_faq):.3f}s   target: <1s (p50)")

    # --- 2. Exact-match cache hit (Tier-2) ------------------------------
    # first call to a NOVEL question is a cache MISS (goes through
    # retrieve+generate and populates the cache); the second call to the
    # SAME question is the real cache HIT being measured.
    miss_time = _time_chat_stream(client, CACHE_QUESTION)
    cache_hits = [_time_chat_stream(client, CACHE_QUESTION) for _ in range(3)]
    print(f"[Cache hit]  populating miss (not the measured number)={miss_time:.3f}s   "
          f"hit repeats={['%.3f' % t for t in cache_hits]}   "
          f"hit median={statistics.median(cache_hits):.3f}s")

    # --- 3. Fresh generation --------------------------------------------
    fresh_times = []
    for q in FRESH_QUESTIONS:
        t = _time_chat_stream(client, q)
        fresh_times.append(t)
        print(f"[Fresh gen]  {t:.3f}s   {q[:70]}")
    print(f"[Fresh gen]  median={statistics.median(fresh_times):.3f}s   "
          f"min={min(fresh_times):.3f}s  max={max(fresh_times):.3f}s   target band: 10-60s")


if __name__ == "__main__":
    main()
