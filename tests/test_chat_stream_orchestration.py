"""Integration tests for the Phase-3 /chat_stream wiring (D9, D10):
AC-2 (orchestration=False + faq_cache=False collapses to byte-identical
iter-2 SSE output), AC-6/AC-8 (FAQ Tier-1 runs before Tier-2 and skips
retrieval/generation entirely on a hit; FAQ_CACHE=false bypasses Tier-1
entirely), AC-4 (verification SSE event + decline-not-cached), and the
citation-lookup direct-fetch path (D8a).

Real Flask test client + the _events SSE parser from
tests/test_chat_stream_cache.py; monkeypatch CONFIG/models/retrieve/FAQ
matcher per test; each test uses its own tempdir-backed DBs.
Run:  python -m pytest tests/test_chat_stream_orchestration.py -q"""
from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from src.app import api
from src.rag.config import CONFIG


def _events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = block.splitlines()
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        out.append((event, data))
    return out


def _tmp_cfg(d: str, **kw):
    return replace(
        CONFIG,
        cache_path=str(Path(d) / "cache.db"),
        faq_db_path=str(Path(d) / "faq.db"),
        **kw,
    )


# ---------------------------------------------------------------------------
# AC-2: orchestration=False + faq_cache=False collapse
# ---------------------------------------------------------------------------

def test_collapse_generated_answer_matches_iter2_behavior():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=False, faq_cache=False)
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.models.available", return_value=True), \
             patch("src.app.api.models.stream", return_value=iter(["It is ", "$10,000."])) as mock_stream, \
             patch("src.app.api.retrieve", wraps=api.retrieve) as mock_retrieve:
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": "What is the CTR dollar threshold?"})
            events = _events(r.get_data(as_text=True))
            tokens = "".join(d_["t"] for e, d_ in events if e == "token")
            assert tokens == "It is $10,000."
            assert [e for e, _ in events] == ["token", "token", "citations", "done"]
            assert mock_retrieve.call_count == 1
            assert mock_stream.call_count == 1


def test_collapse_cache_hit_replay_matches_iter2():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=False, faq_cache=False)
        from src.rag import cache
        question = "What is the CTR dollar threshold?"
        cache.put(cfg, question, "Cached answer.", [{"citation": "31 CFR 1010.311"}], "2026-01-01")

        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.retrieve") as mock_retrieve, \
             patch("src.app.api.models.stream") as mock_stream:
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": question})
            events = _events(r.get_data(as_text=True))
            assert [e for e, _ in events] == ["token", "citations", "done"]
            tokens = "".join(d_["t"] for e, d_ in events if e == "token")
            assert tokens == "Cached answer."
            mock_retrieve.assert_not_called()
            mock_stream.assert_not_called()


def test_collapse_extractive_fallback_matches_iter2():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=False, faq_cache=False)
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.models.available", return_value=False):
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": "What is the CTR dollar threshold?"})
            events = _events(r.get_data(as_text=True))
            tokens = "".join(d_["t"] for e, d_ in events if e == "token")
            assert tokens.startswith("Most relevant provision:")
            assert [e for e, _ in events] == ["token", "citations", "done"]


def test_collapse_no_citations_matches_iter2():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=False, faq_cache=False)
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.retrieve", return_value=("", [])):
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": "Some zero-hit question"})
            events = _events(r.get_data(as_text=True))
            tokens = "".join(d_["t"] for e, d_ in events if e == "token")
            assert "No matching regulatory text" in tokens
            assert [e for e, _ in events] == ["token", "citations", "done"]


def test_collapse_empty_question_still_400_before_faq_work():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=False, faq_cache=True)  # faq_cache ON here
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.faq_matcher.match") as mock_match:
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": "   "})
            assert r.status_code == 400
            assert r.get_json() == {"error": "empty question"}
            mock_match.assert_not_called()  # no FAQ/embed work before the 400


# ---------------------------------------------------------------------------
# AC-6/AC-8: FAQ Tier-1 ordering + independence
# ---------------------------------------------------------------------------

def test_faq_tier1_hit_skips_retrieval_and_generation_entirely():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=False, faq_cache=True)
        hit = {"id": "faq-x", "answer": "Pre-verified answer.",
               "citations": [{"citation": "31 CFR 1010.311"}], "as_of": "2026-06-15", "score": 0.95}
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.faq_matcher.match", return_value=hit), \
             patch("src.app.api.retrieve") as mock_retrieve, \
             patch("src.app.api.models.stream") as mock_stream:
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": "when do I file a CTR"})
            events = _events(r.get_data(as_text=True))
            tokens = "".join(d_["t"] for e, d_ in events if e == "token")
            assert tokens == "Pre-verified answer."
            cites = next(d_ for e, d_ in events if e == "citations")
            assert cites == {"citations": hit["citations"], "as_of": hit["as_of"]}
            mock_retrieve.assert_not_called()
            mock_stream.assert_not_called()


def test_faq_tier1_runs_before_tier2_exact_cache():
    """A query that would hit both Tier-1 (FAQ) and Tier-2 (exact cache) is
    answered by Tier-1."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=False, faq_cache=True)
        question = "when do I file a CTR"

        from src.rag import cache
        cache.put(cfg, question, "TIER-2 ANSWER", [{"citation": "tier2"}], "2020-01-01")

        faq_hit = {"id": "faq-x", "answer": "TIER-1 ANSWER",
                   "citations": [{"citation": "tier1"}], "as_of": "2026-06-15", "score": 0.95}
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.faq_matcher.match", return_value=faq_hit):
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": question})
            events = _events(r.get_data(as_text=True))
            tokens = "".join(d_["t"] for e, d_ in events if e == "token")
            assert tokens == "TIER-1 ANSWER"


def test_faq_cache_false_bypasses_tier1_no_db_read_no_embed_call():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=False, faq_cache=False)
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.faq_matcher.match") as mock_match, \
             patch("src.app.api.models.available", return_value=False):
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": "when do I file a CTR"})
            _events(r.get_data(as_text=True))
            mock_match.assert_not_called()


# ---------------------------------------------------------------------------
# AC-4: verification SSE event + decline-not-cached (orchestrated path)
# ---------------------------------------------------------------------------

def test_orchestrated_path_emits_verification_event_before_citations():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=True, faq_cache=False, verify_answers=True)
        context = ("[31 CFR 1010.311] Filing obligations\nEach financial institution shall "
                    "file a report of a transaction in currency of more than $10,000.")
        citations = [{"citation": "31 CFR 1010.311", "heading": "Filing obligations",
                      "url": "u", "source": "ecfr", "as_of": "2026-06-30"}]
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.models.available", return_value=True), \
             patch("src.app.api.models.stream",
                   return_value=iter(["Each financial institution shall file a report "
                                       "of a transaction in currency of more than $10,000."])), \
             patch("src.app.api.retrieve", return_value=(context, citations)):
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": "What is the CTR dollar threshold?"})
            events = _events(r.get_data(as_text=True))
            event_order = [e for e, _ in events]
            assert "verification" in event_order
            assert event_order.index("verification") < event_order.index("citations")
            verification = next(d_ for e, d_ in events if e == "verification")
            assert verification["grounded"] is True
            assert verification["declined"] is False

            from src.rag import cache
            assert cache.get(cfg, "What is the CTR dollar threshold?") is not None


def test_orchestrated_path_declined_answer_not_cached():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=True, faq_cache=False, verify_answers=True)
        context = ("[31 CFR 1010.311] Filing obligations\nEach financial institution shall "
                    "file a report of a transaction in currency of more than $10,000.")
        citations = [{"citation": "31 CFR 1010.311", "heading": "Filing obligations",
                      "url": "u", "source": "ecfr", "as_of": "2026-06-30"}]
        question = "What is the CTR dollar threshold?"
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.models.available", return_value=True), \
             patch("src.app.api.models.stream",
                   return_value=iter(["The moon landing occurred in 1969."])), \
             patch("src.app.api.retrieve", return_value=(context, citations)):
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": question})
            events = _events(r.get_data(as_text=True))
            verification = next(d_ for e, d_ in events if e == "verification")
            assert verification["grounded"] is False
            assert verification["declined"] is True

            from src.rag import cache
            assert cache.get(cfg, question) is None


def test_orchestrated_path_off_skips_verification_event():
    """VERIFY_ANSWERS is only consulted when ORCHESTRATION=true (D7); with
    orchestration off, no verification event at all (iter-2 shape)."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=False, faq_cache=False, verify_answers=True)
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.models.available", return_value=True), \
             patch("src.app.api.models.stream", return_value=iter(["answer"])):
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": "What is the CTR dollar threshold?"})
            events = _events(r.get_data(as_text=True))
            assert "verification" not in [e for e, _ in events]


# ---------------------------------------------------------------------------
# D8a: citation-lookup direct fetch + fallback
# ---------------------------------------------------------------------------

def test_citation_lookup_direct_fetch_used_when_available():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=True, faq_cache=False, verify_answers=False)
        fetched = ("[31 CFR 1010.311] direct fetch context",
                   [{"citation": "31 CFR 1010.311", "heading": "h", "url": "u", "source": "ecfr", "as_of": "2026-06-30"}])
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.planner.citation_fetch", return_value=fetched) as mock_fetch, \
             patch("src.app.api.retrieve") as mock_retrieve, \
             patch("src.app.api.models.available", return_value=False):
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": "What does 31 CFR 1010.311 require?"})
            _events(r.get_data(as_text=True))
            mock_fetch.assert_called_once()
            mock_retrieve.assert_not_called()


def test_citation_lookup_falls_back_to_semantic_mode_when_fetch_empty():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=True, faq_cache=False, verify_answers=False)
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.planner.citation_fetch", return_value=None), \
             patch("src.app.api.retrieve", return_value=("fallback context", [{"citation": "x"}])) as mock_retrieve, \
             patch("src.app.api.models.available", return_value=False):
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": "What does 31 CFR 1010.311 require?"})
            events = _events(r.get_data(as_text=True))
            mock_retrieve.assert_called_once()
            tokens = "".join(d_["t"] for e, d_ in events if e == "token")
            assert "fallback context" in tokens


if __name__ == "__main__":
    test_collapse_generated_answer_matches_iter2_behavior()
    test_collapse_cache_hit_replay_matches_iter2()
    test_collapse_extractive_fallback_matches_iter2()
    test_collapse_no_citations_matches_iter2()
    test_collapse_empty_question_still_400_before_faq_work()
    test_faq_tier1_hit_skips_retrieval_and_generation_entirely()
    test_faq_tier1_runs_before_tier2_exact_cache()
    test_faq_cache_false_bypasses_tier1_no_db_read_no_embed_call()
    test_orchestrated_path_emits_verification_event_before_citations()
    test_orchestrated_path_declined_answer_not_cached()
    test_orchestrated_path_off_skips_verification_event()
    test_citation_lookup_direct_fetch_used_when_available()
    test_citation_lookup_falls_back_to_semantic_mode_when_fetch_empty()
    print("chat_stream orchestration ok")
