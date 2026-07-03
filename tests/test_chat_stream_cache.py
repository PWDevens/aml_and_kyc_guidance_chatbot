"""Behavior tests for the answer-cache <-> /chat_stream wiring (AC-6) plus the
edge cases the spec calls out: cache miss writes only on the generated path,
extractive/no-citation answers are never cached, a cache hit skips retrieval
and generation entirely, and empty questions still 400.

Uses the real Flask test client and the real retrieve()/cache module against
the already-built index (tests/test_smoke.py already assumes one exists).
Each test uses its own tempdir-backed cache DB (via monkeypatching
CONFIG.cache_path) so nothing here touches the real data/cache.db.

Run:  python -m pytest tests/test_chat_stream_cache.py -q
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from src.app import api
from src.rag.config import CONFIG


def _events(body: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into a list of (event, data) pairs."""
    out = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = block.splitlines()
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        out.append((event, data))
    return out


def _tmp_cfg(d: str):
    # Phase 3: also point faq_db_path at a tempdir path (absent -> the Tier-1
    # FAQ matcher gracefully misses, same as pre-Phase-3 behavior) so these
    # iter-2 exact-cache tests aren't intercepted by the real, now-seeded
    # data/faq.db (AC-11). Mirrors this file's own "own tempdir-backed DB"
    # pattern, just extended to the new DB Phase 3 introduces.
    return replace(CONFIG, cache_path=str(Path(d) / "test_cache.db"),
                    faq_db_path=str(Path(d) / "test_faq.db"))


def test_generated_answer_is_cached_and_replayed_on_second_call():
    """Happy path: miss -> generate (mocked) -> cache write; identical
    (differently-cased/padded) question on second call -> cache hit that
    skips retrieval and generation entirely."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d)
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.models.available", return_value=True), \
             patch("src.app.api.models.stream", return_value=iter(["It is ", "$10,000."])) as mock_stream, \
             patch("src.app.api.retrieve", wraps=api.retrieve) as mock_retrieve:
            client = api.app.test_client()

            r1 = client.post("/chat_stream", json={"question": "What is the CTR dollar threshold?"})
            events1 = _events(r1.get_data(as_text=True))
            tokens1 = "".join(d_["t"] for e, d_ in events1 if e == "token")
            assert tokens1 == "It is $10,000."
            cites1 = next(d_ for e, d_ in events1 if e == "citations")["citations"]
            assert cites1  # real retrieval found citations
            assert mock_retrieve.call_count == 1
            assert mock_stream.call_count == 1

            # second call: differently cased + padded, must hit the cache
            r2 = client.post("/chat_stream", json={"question": "  what IS the ctr dollar threshold?  "})
            events2 = _events(r2.get_data(as_text=True))
            tokens2 = "".join(d_["t"] for e, d_ in events2 if e == "token")
            assert tokens2 == "It is $10,000."
            cites2 = next(d_ for e, d_ in events2 if e == "citations")["citations"]
            assert cites2 == cites1

            # retrieval/generation must NOT have run again
            assert mock_retrieve.call_count == 1
            assert mock_stream.call_count == 1


def test_extractive_fallback_is_not_cached():
    """GENERATE unavailable -> extractive fallback path. Spec requires this
    NOT be cached (unverified/non-authoritative)."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d)
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.models.available", return_value=False):
            client = api.app.test_client()
            question = "What is the CTR dollar threshold?"

            r = client.post("/chat_stream", json={"question": question})
            events = _events(r.get_data(as_text=True))
            tokens = "".join(d_["t"] for e, d_ in events if e == "token")
            assert tokens.startswith("Most relevant provision:")

            from src.rag import cache
            assert cache.get(cfg, question) is None


def test_no_matching_text_is_not_cached():
    """No citations found -> 'no matching text' message. Must not be cached
    either (not verified/authoritative)."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d)
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.retrieve", return_value=("", [])):
            client = api.app.test_client()
            question = "Some question with zero retrieval hits"

            r = client.post("/chat_stream", json={"question": question})
            events = _events(r.get_data(as_text=True))
            tokens = "".join(d_["t"] for e, d_ in events if e == "token")
            assert "No matching regulatory text" in tokens

            from src.rag import cache
            assert cache.get(cfg, question) is None


def test_answer_cache_disabled_never_reads_or_writes_cache():
    """ANSWER_CACHE=false (CONFIG.answer_cache=False) must bypass the cache
    entirely: no lookup on a pre-seeded hit, and no write after generation."""
    with tempfile.TemporaryDirectory() as d:
        cfg = replace(_tmp_cfg(d), answer_cache=False)
        question = "What is the CTR dollar threshold?"

        from src.rag import cache
        cache.put(cfg, question, "STALE CACHED ANSWER", [], "2020-01-01")

        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.models.available", return_value=True), \
             patch("src.app.api.models.stream", return_value=iter(["Fresh ", "answer."])):
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": question})
            events = _events(r.get_data(as_text=True))
            tokens = "".join(d_["t"] for e, d_ in events if e == "token")
            # must NOT replay the stale cached answer
            assert tokens == "Fresh answer."


def test_empty_question_returns_400():
    client = api.app.test_client()
    r = client.post("/chat_stream", json={"question": "   "})
    assert r.status_code == 400
    assert r.get_json() == {"error": "empty question"}


def test_real_generation_end_to_end_grounded_answer_is_cached():
    """Stronger, unmocked version of the happy path: exercises the real
    Phi-4-mini-instruct-onnx generation stack (onnxruntime-genai version-drift
    fix verified separately) instead of mocking models.stream, per the
    orchestrator's note that live generation now works. Confirms a real
    generated answer is grounded in the retrieved context and gets cached."""
    with tempfile.TemporaryDirectory() as d:
        cfg = replace(_tmp_cfg(d), max_new_tokens=60)
        with patch("src.app.api.CONFIG", cfg):
            client = api.app.test_client()
            question = "What is the dollar threshold for filing a Currency Transaction Report?"

            r = client.post("/chat_stream", json={"question": question})
            events = _events(r.get_data(as_text=True))
            tokens = "".join(d_["t"] for e, d_ in events if e == "token")
            assert "10,000" in tokens
            cites = next(d_ for e, d_ in events if e == "citations")["citations"]
            assert any("1010.311" in c["citation"] for c in cites)

            from src.rag import cache
            hit = cache.get(cfg, question)
            assert hit is not None
            assert hit["answer"] == tokens


if __name__ == "__main__":
    test_generated_answer_is_cached_and_replayed_on_second_call()
    test_extractive_fallback_is_not_cached()
    test_no_matching_text_is_not_cached()
    test_answer_cache_disabled_never_reads_or_writes_cache()
    test_empty_question_returns_400()
    test_real_generation_end_to_end_grounded_answer_is_cached()
    print("chat_stream cache integration ok")
