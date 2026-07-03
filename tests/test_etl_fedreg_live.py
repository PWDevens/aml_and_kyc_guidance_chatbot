"""AC-7: seeded-past-watermark FedReg detection against the REAL live API —
mirrors iteration 1's live-fetch-at-build-time stance (no fake API server).
Seeds a watermark artificially in the past (2024-12-31), runs the fedreg
watcher + pipeline for real, and asserts a non-empty delta is detected,
upserted, and the watermark advances; a second run is idempotent (nothing
new, count unchanged). Uses a tempdir Chroma collection + tempfile
etl_state.db so the committed data/chroma index and data/etl_state.db are
never mutated.

Network-tolerant: skips (not fails) on requests.exceptions.RequestException,
so an offline run doesn't fail the suite.

Run:  python -m pytest tests/test_etl_fedreg_live.py -q -s"""
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
import requests

from src.etl import pipeline, state
from src.rag.config import CONFIG
from src.rag.indexing.builder import get_collection


def test_seeded_watermark_detects_and_ingests_live_fedreg_changes():
    # ignore_cleanup_errors: Chroma's PersistentClient keeps its sqlite/HNSW
    # files open for the life of the process, which trips Windows' delete-
    # while-open rule during tempdir teardown (see also test_etl_upsert.py).
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        cfg = replace(
            CONFIG,
            chroma_path=str(Path(d) / "chroma"),
            collection="etl_live_test",
            etl_state_path=str(Path(d) / "etl_state.db"),
            faq_db_path=str(Path(d) / "faq.db"),
        )
        state.set_watermark(cfg, "fedreg", "2024-12-31", None)

        try:
            summary1 = pipeline.run_once(cfg)
        except requests.exceptions.RequestException:
            pytest.skip("live FedReg API unreachable")

        fedreg_summary = summary1["fedreg"]
        assert "error" not in fedreg_summary, f"pipeline reported an error: {fedreg_summary}"
        assert fedreg_summary["detected"] >= 1, "expected >=1 FinCEN doc since 2024-12-31"

        col = get_collection(cfg)
        count_after_first_run = col.count()
        assert count_after_first_run >= 1

        wm_after_first = state.get_watermark(cfg, "fedreg")
        assert wm_after_first is not None
        assert wm_after_first[0] > "2024-12-31"

        # second identical run: nothing new, watermark/count unchanged
        try:
            summary2 = pipeline.run_once(cfg)
        except requests.exceptions.RequestException:
            pytest.skip("live FedReg API unreachable on second run")

        assert summary2["fedreg"]["detected"] == 0
        assert get_collection(cfg).count() == count_after_first_run
        assert state.get_watermark(cfg, "fedreg") == wm_after_first


if __name__ == "__main__":
    test_seeded_watermark_detects_and_ingests_live_fedreg_changes()
    print("etl fedreg live ok")
