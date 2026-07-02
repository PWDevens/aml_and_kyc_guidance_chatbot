"""Integration-level test of GET /corpus_status's iteration-2 extension
(AC-6): `last_etl_run` and `counts_by_source` keys, via the real Flask test
client — not just the underlying src/etl/state.py functions (those already
have unit coverage in tests/test_etl_state.py). Mirrors
tests/test_chat_stream_cache.py's pattern: tempdir-backed config patched onto
src.app.api.CONFIG, real Flask test client, no mocking of the handler itself.

Uses a throwaway Chroma collection + tempfile etl_state.db so this test never
touches the real data/chroma or data/etl_state.db.

Run:  python -m pytest tests/test_corpus_status_endpoint.py -q"""
from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from src.app import api
from src.etl import state as etl_state
from src.rag.config import CONFIG
from src.rag.indexing.builder import build

_RECORDS = [
    {"id": "ecfr-31-1010.311", "text": "currency transaction reporting text",
     "citation": "31 CFR 1010.311", "heading": "CTR", "source": "ecfr", "as_of": "2026-01-05"},
    {"id": "fedreg-2025-01374", "text": "a final rule abstract",
     "citation": "2025-01374", "heading": "Final Rule", "source": "fedreg_rule", "as_of": "2025-01-17"},
]


def _tmp_cfg(d: str, **overrides):
    base = replace(
        CONFIG,
        chroma_path=str(Path(d) / "chroma"),
        collection="corpus_status_test",
        etl_state_path=str(Path(d) / "etl_state.db"),
    )
    return replace(base, **overrides) if overrides else base


def test_corpus_status_reports_last_etl_run_and_counts_by_source():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        cfg = _tmp_cfg(d)
        build(cfg, _RECORDS)
        etl_state.record(cfg, rule_id="R1", source="fedreg", document_ref="2025-01374",
                          citation="2025-01374", action="upsert", chunks_changed=1,
                          as_of="2025-01-17", status="success")

        with patch("src.app.api.CONFIG", cfg):
            client = api.app.test_client()
            r = client.get("/corpus_status")

        assert r.status_code == 200
        body = r.get_json()

        # existing keys preserved
        assert body["indexed"] == 2
        assert body["as_of"] is not None
        assert body["rag_mode"] == cfg.rag_mode

        # new AC-6 keys
        assert body["last_etl_run"] is not None
        assert body["counts_by_source"] == {"ecfr": 1, "fedreg_rule": 1}


def test_corpus_status_last_etl_run_is_null_when_etl_state_db_absent():
    """AC-6 edge case: etl_state.db missing entirely (ETL never ran) must
    still yield 200 with last_etl_run=None, not a 500 — ETL is optional
    infra and must not break the endpoint the base app depends on."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        cfg = _tmp_cfg(d, etl_state_path=str(Path(d) / "nonexistent_subdir" / "etl_state.db"))
        build(cfg, _RECORDS)
        # deliberately never call etl_state.record/set_watermark, and use a
        # path inside a subdirectory that was never created, so sqlite3.connect
        # itself fails (a stronger absence-simulation than an empty file).

        with patch("src.app.api.CONFIG", cfg):
            client = api.app.test_client()
            r = client.get("/corpus_status")

        assert r.status_code == 200
        body = r.get_json()
        assert body["last_etl_run"] is None
        assert body["indexed"] == 2


def test_corpus_status_counts_by_source_empty_when_no_provenance_yet():
    """A freshly built collection with no ETL pass run yet: counts_by_source
    still tallies from the collection's own metadata (not from provenance),
    so it is populated even before any ETL pass has run."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        cfg = _tmp_cfg(d)
        build(cfg, _RECORDS)

        with patch("src.app.api.CONFIG", cfg):
            client = api.app.test_client()
            r = client.get("/corpus_status")

        body = r.get_json()
        assert body["last_etl_run"] is None  # no provenance rows recorded
        assert body["counts_by_source"] == {"ecfr": 1, "fedreg_rule": 1}  # from collection metadata


def test_corpus_status_still_503_on_missing_collection():
    """Existing behavior (pre-iteration-2) must be preserved: a missing Chroma
    collection still yields 503, not a crash from the new state read."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        cfg = _tmp_cfg(d, collection="does_not_exist_collection")
        # no build() call — collection was never created

        with patch("src.app.api.CONFIG", cfg):
            client = api.app.test_client()
            r = client.get("/corpus_status")

        assert r.status_code == 503


if __name__ == "__main__":
    test_corpus_status_reports_last_etl_run_and_counts_by_source()
    test_corpus_status_last_etl_run_is_null_when_etl_state_db_absent()
    test_corpus_status_counts_by_source_empty_when_no_provenance_yet()
    test_corpus_status_still_503_on_missing_collection()
    print("corpus_status endpoint ok")
