"""R5 staleness flag + suppression (AC-10, D14). Simulates a successful ETL
upsert of a citation referenced by a seeded FAQ entry via
src/etl/pipeline._flag_faq_stale (the real production code path pipeline.py
calls after an R1/R4 upsert), asserts the entry is flagged stale in faq.db
plus an R5/flag_stale provenance row, and asserts the Tier-1 matcher then
suppresses that entry under FAQ_STALE_POLICY=suppress.

Each test uses its own tempdir-backed faq.db + etl_state.db so nothing here
touches the real data/*.db.
Run:  python -m pytest tests/test_faq_staleness_r5.py -q"""
from __future__ import annotations

import sqlite3
import tempfile
from dataclasses import replace
from pathlib import Path

from src.etl import pipeline
from src.etl import rules as etl_rules
from src.rag.config import CONFIG
from src.rag.faq import matcher, store
from src.rag.faq.embed import embed_queries
from src.rag.orchestration.intents import frame_query

_ENTRY = {
    "id": "faq-ctr-threshold",
    "canonical_question": "What is the CTR filing threshold?",
    "paraphrases": ["when do I file a CTR"],
    "answer": "It is $10,000 (31 CFR 1010.311).",
    "citations": [{"source": "ecfr", "citation": "31 CFR 1010.311",
                    "url": "https://www.ecfr.gov/x", "as_of": "2026-06-15"}],
    "topic_keys": ["1010.311", "CTR"],
    "verified_by": "curator",
    "as_of": "2026-06-15",
}


def _tmp_cfg(d: str, **kw):
    return replace(
        CONFIG,
        faq_db_path=str(Path(d) / "faq.db"),
        etl_state_path=str(Path(d) / "etl_state.db"),
        **kw,
    )


def _seed(cfg):
    strings = [_ENTRY["canonical_question"], *_ENTRY["paraphrases"]]
    embeddings = embed_queries(strings, cfg.embed_model)
    store.upsert_entry(cfg, _ENTRY, embeddings)


def _match(cfg, question: str):
    framed = frame_query(question)
    hints = {"citation_hint": framed["citation_hint"], "numeric_hint": framed["numeric_hint"]}
    return matcher.match(cfg, framed["framed_query"], hints)


def test_classify_faq_staleness_stamps_r5_flag_stale():
    result = etl_rules.classify_faq_staleness("31 CFR 1010.311")
    assert result == {"rule_id": "R5", "action": "flag_stale", "citation": "31 CFR 1010.311"}


def test_successful_upsert_flags_referencing_faq_entry_stale():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d)
        _seed(cfg)

        # sanity: entry hits before the ETL upsert
        assert _match(cfg, "when do I file a CTR") is not None

        pipeline._flag_faq_stale(cfg, source="ecfr", document_ref="31 CFR 1010.311",
                                  citation="31 CFR 1010.311", as_of="2026-07-01")

        assert store.is_stale(cfg, "faq-ctr-threshold") is True


def test_flag_stale_writes_r5_provenance_row():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d)
        _seed(cfg)

        pipeline._flag_faq_stale(cfg, source="ecfr", document_ref="31 CFR 1010.311",
                                  citation="31 CFR 1010.311", as_of="2026-07-01")

        conn = sqlite3.connect(cfg.etl_state_path)
        try:
            rows = conn.execute(
                "SELECT rule_id, action, citation, status FROM provenance WHERE rule_id = 'R5'"
            ).fetchall()
        finally:
            conn.close()
        assert rows == [("R5", "flag_stale", "31 CFR 1010.311", "success")]


def test_stale_entry_is_suppressed_by_matcher_under_suppress_policy():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, faq_stale_policy="suppress")
        _seed(cfg)

        pipeline._flag_faq_stale(cfg, source="ecfr", document_ref="31 CFR 1010.311",
                                  citation="31 CFR 1010.311", as_of="2026-07-01")

        # a query that previously hit the entry must now miss
        assert _match(cfg, "when do I file a CTR") is None


def test_non_suppress_policy_is_still_treated_as_suppress():
    """D14: reverify_inline is NOT built this iteration — any non-`suppress`
    policy value is accepted but treated as suppress."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, faq_stale_policy="reverify_inline")
        _seed(cfg)

        pipeline._flag_faq_stale(cfg, source="ecfr", document_ref="31 CFR 1010.311",
                                  citation="31 CFR 1010.311", as_of="2026-07-01")

        assert _match(cfg, "when do I file a CTR") is None


def test_flag_faq_stale_is_a_noop_when_faq_db_absent():
    """Best-effort posture: an absent faq.db must not raise or block ETL."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d)  # faq.db never created
        pipeline._flag_faq_stale(cfg, source="ecfr", document_ref="31 CFR 1010.311",
                                  citation="31 CFR 1010.311", as_of="2026-07-01")
        # no exception raised is the assertion


if __name__ == "__main__":
    test_classify_faq_staleness_stamps_r5_flag_stale()
    test_successful_upsert_flags_referencing_faq_entry_stale()
    test_flag_stale_writes_r5_provenance_row()
    test_stale_entry_is_suppressed_by_matcher_under_suppress_policy()
    test_non_suppress_policy_is_still_treated_as_suppress()
    test_flag_faq_stale_is_a_noop_when_faq_db_absent()
    print("faq staleness R5 ok")
