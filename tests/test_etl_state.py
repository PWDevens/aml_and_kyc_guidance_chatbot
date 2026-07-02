"""One runnable check: watermark read/write, provenance row shape, and
advance-only-on-success semantics — against a tempfile etl_state.db.
Run:  python -m pytest tests/test_etl_state.py -q"""
import tempfile
from dataclasses import replace
from pathlib import Path

from src.etl import state
from src.rag.config import CONFIG


def _cfg(tmpdir: str):
    return replace(CONFIG, etl_state_path=str(Path(tmpdir) / "etl_state.db"))


def test_watermark_round_trip():
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg(d)
        assert state.get_watermark(cfg, "fedreg") is None

        state.set_watermark(cfg, "fedreg", "2025-01-17", "2025-01374")
        wm = state.get_watermark(cfg, "fedreg")
        assert wm == ("2025-01-17", "2025-01374")

        # INSERT OR REPLACE: second call overwrites, doesn't duplicate
        state.set_watermark(cfg, "fedreg", "2025-02-01", "2025-02000")
        assert state.get_watermark(cfg, "fedreg") == ("2025-02-01", "2025-02000")


def test_provenance_record_and_last_successful_run():
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg(d)
        assert state.last_successful_run(cfg) is None

        state.record(cfg, rule_id="R1", source="fedreg", document_ref="2025-01374",
                      citation="2025-01374", action="upsert", chunks_changed=1,
                      as_of="2025-01-17", status="success")
        first_run = state.last_successful_run(cfg)
        assert first_run is not None

        # an error row must NOT move last_successful_run
        state.record(cfg, rule_id="R1", source="fedreg", document_ref="2025-99999",
                      citation="2025-99999", action="upsert", chunks_changed=0,
                      as_of=None, status="error")
        assert state.last_successful_run(cfg) == first_run


def test_counts_by_source():
    metas = [{"source": "ecfr"}, {"source": "ecfr"}, {"source": "fedreg_rule"}]
    assert state.counts_by_source(metas) == {"ecfr": 2, "fedreg_rule": 1}


def test_watermark_not_advanced_after_simulated_mid_batch_failure():
    """Simulates the pipeline's own contract: process a 2-item batch, item 2
    raises, so the watermark must stay at its pre-batch value and no
    success provenance row exists for the failed item."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg(d)
        state.set_watermark(cfg, "fedreg", "2024-12-31", None)

        batch = [
            {"document_number": "2025-00001", "publication_date": "2025-01-05"},
            {"document_number": "2025-00002", "publication_date": "2025-01-06"},  # will "fail"
        ]
        newest = None
        try:
            for doc in batch:
                if doc["document_number"] == "2025-00002":
                    raise RuntimeError("simulated extract/transform/load failure")
                state.record(cfg, rule_id="R1", source="fedreg", document_ref=doc["document_number"],
                              citation=doc["document_number"], action="upsert", chunks_changed=1,
                              as_of=doc["publication_date"], status="success")
                newest = doc["publication_date"]
            state.set_watermark(cfg, "fedreg", newest, batch[-1]["document_number"])
        except RuntimeError:
            state.record(cfg, rule_id="R1", source="fedreg", document_ref="2025-00002",
                          citation="2025-00002", action="upsert", chunks_changed=0,
                          as_of="2025-01-06", status="error")

        # watermark unchanged (still the pre-batch value)
        assert state.get_watermark(cfg, "fedreg") == ("2024-12-31", None)
        # no success provenance row for the failed item 2025-00002
        conn = state._conn(cfg)
        try:
            row = conn.execute(
                "SELECT status FROM provenance WHERE document_ref = ?", ("2025-00002",)
            ).fetchone()
        finally:
            conn.close()
        assert row == ("error",)


if __name__ == "__main__":
    test_watermark_round_trip()
    test_provenance_record_and_last_successful_run()
    test_counts_by_source()
    test_watermark_not_advanced_after_simulated_mid_batch_failure()
    print("etl state ok")
