"""Unit tests for src/rag/faq/matcher.py (D2-D4). AC-6 (paraphrase hit),
AC-7 (false-positive guard: below-threshold + topic-key mismatch), AC-8
(FAQ absent/empty degrades to a graceful miss).

Each test uses its own tempdir-backed faq.db (mirrors
tests/test_chat_stream_cache.py's _tmp_cfg pattern) so nothing here touches
the real data/faq.db. Uses the real embedding model (cheap after first load,
D1) rather than mocking — the matching behavior IS the thing under test.
Run:  python -m pytest tests/test_faq_matcher.py -q"""
from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

from src.rag.config import CONFIG
from src.rag.faq import matcher, store
from src.rag.faq.embed import embed_queries
from src.rag.orchestration.intents import frame_query

_ENTRY = {
    "id": "faq-ctr-threshold",
    "canonical_question": "What is the CTR filing threshold?",
    "paraphrases": [
        "when do I file a CTR",
        "currency transaction report dollar limit",
    ],
    "answer": "It is $10,000 (31 CFR 1010.311).",
    "citations": [{"source": "ecfr", "citation": "31 CFR 1010.311",
                    "url": "https://www.ecfr.gov/x", "as_of": "2026-06-15"}],
    "topic_keys": ["1010.311", "CTR"],
    "verified_by": "curator",
    "as_of": "2026-06-15",
}

_OTHER_ENTRY = {
    "id": "faq-cip-minimum",
    "canonical_question": "What are the minimum requirements for a customer identification program?",
    "paraphrases": ["CIP minimum requirements"],
    "answer": "Name, date of birth, address, identification number (31 CFR 1020.220).",
    "citations": [{"source": "ecfr", "citation": "31 CFR 1020.220",
                    "url": "https://www.ecfr.gov/y", "as_of": "2023-04-10"}],
    "topic_keys": ["1020.220", "CIP"],
    "verified_by": "curator",
    "as_of": "2023-04-10",
}


def _tmp_cfg(d: str, **kw):
    return replace(CONFIG, faq_db_path=str(Path(d) / "faq.db"), **kw)


def _seed(cfg, entries=(_ENTRY, _OTHER_ENTRY)):
    for entry in entries:
        strings = [entry["canonical_question"], *entry.get("paraphrases", [])]
        embeddings = embed_queries(strings, cfg.embed_model)
        store.upsert_entry(cfg, entry, embeddings)


def _match(cfg, question: str):
    framed = frame_query(question)
    hints = {"citation_hint": framed["citation_hint"], "numeric_hint": framed["numeric_hint"]}
    return matcher.match(cfg, framed["framed_query"], hints)


def test_paraphrase_not_exact_string_hits():
    """AC-6: a genuine paraphrase (not verbatim in canonical/paraphrases)
    still hits when cos >= FAQ_SIM_THRESHOLD and the topic-key cross-check
    passes."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d)
        _seed(cfg)
        hit = _match(cfg, "How much cash triggers a CTR filing requirement at a bank?")
        assert hit is not None
        assert hit["id"] == "faq-ctr-threshold"
        assert hit["answer"] == _ENTRY["answer"]
        assert hit["citations"] == _ENTRY["citations"]
        assert hit["as_of"] == _ENTRY["as_of"]
        assert hit["score"] >= cfg.faq_sim_threshold


def test_below_threshold_query_is_a_miss():
    """AC-7: an off-topic look-alike below threshold produces a miss."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d)
        _seed(cfg)
        hit = _match(cfg, "What is the weather forecast for the Bahamas tomorrow?")
        assert hit is None


def test_citation_hint_mismatch_forces_miss_even_above_threshold():
    """AC-7: D4's topic-key cross-check overrides a raw cosine pass — if the
    query's extracted citation_hint contradicts the best entry's
    topic_keys, treat as miss regardless of score."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d)
        _seed(cfg)
        # Wording strongly resembles the CTR entry but explicitly cites a
        # different, unrelated section — the cross-check must reject it.
        hit = _match(cfg, "31 CFR 1010.230 currency transaction report dollar limit")
        assert hit is None or hit["id"] != "faq-ctr-threshold"


def test_crosscheck_disabled_allows_threshold_alone_to_decide():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, faq_topic_crosscheck=False)
        _seed(cfg)
        hit = _match(cfg, "currency transaction report dollar limit")
        assert hit is not None
        assert hit["id"] == "faq-ctr-threshold"


def test_faq_db_absent_returns_none_gracefully():
    """AC-8 edge case: fresh checkout, seed not run -> matcher must not
    crash; falls through to a miss."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d)  # faq.db never created
        hit = _match(cfg, "What is the CTR filing threshold?")
        assert hit is None


def test_empty_store_returns_none():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d)
        store._conn(cfg).close()  # creates the table, no rows
        hit = _match(cfg, "What is the CTR filing threshold?")
        assert hit is None


if __name__ == "__main__":
    test_paraphrase_not_exact_string_hits()
    test_below_threshold_query_is_a_miss()
    test_citation_hint_mismatch_forces_miss_even_above_threshold()
    test_crosscheck_disabled_allows_threshold_alone_to_decide()
    test_faq_db_absent_returns_none_gracefully()
    test_empty_store_returns_none()
    print("faq matcher ok")
