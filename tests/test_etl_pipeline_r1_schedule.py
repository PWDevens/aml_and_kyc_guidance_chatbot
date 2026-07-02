"""One runnable check: R1's "schedule" provenance semantics as actually
IMPLEMENTED BY pipeline.py, not just rules.classify_fedreg's classification
output. changes.md documents that when classify_fedreg returns an R1 match,
pipeline._run_fedreg is supposed to write TWO provenance rows for that same
document: one action='upsert' row (the corpus write) and one action='schedule'
row (as_of=effective_on, marking "an eCFR re-pull is due on this date" per the
spec's R1-scheduling-note, since no timer/queue is built this iteration).
Neither test_etl_rules.py (classifier only) nor test_etl_state.py (state.py
only) exercises this pipeline-level behavior — this test does, against a
tempdir Chroma collection + tempfile etl_state.db, no network (the watcher's
poll() is mocked with an inline raw FedReg doc fixture; everything downstream
— classify_fedreg, _record_from_doc, upsert_by_citation, state.record,
set_watermark — is the real production code path).

Run:  python -m pytest tests/test_etl_pipeline_r1_schedule.py -q"""
from __future__ import annotations

import sqlite3
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from src.etl import pipeline, state
from src.rag.config import CONFIG
from src.rag.indexing.builder import get_collection

_R1_DOC = {
    "document_number": "2025-01374",
    "type": "Rule",
    "title": "Some Final Rule Amending 31 CFR 1010",
    "abstract": "Adjusts civil monetary penalties under the Bank Secrecy Act.",
    "publication_date": "2025-01-17",
    "effective_on": "2025-02-16",
    # D3: chapter is null in the live API; part 1010 is watched by default cfg.parts.
    "cfr_references": [{"chapter": None, "citation_url": None, "part": "1010", "title": 31}],
    "html_url": "https://www.federalregister.gov/documents/2025/01/17/2025-01374",
}


def _tmp_cfg(d: str):
    return replace(
        CONFIG,
        chroma_path=str(Path(d) / "chroma"),
        collection="etl_pipeline_r1_test",
        etl_state_path=str(Path(d) / "etl_state.db"),
    )


def _provenance_rows(cfg, document_ref: str) -> list[tuple]:
    conn = sqlite3.connect(cfg.etl_state_path)
    try:
        return conn.execute(
            "SELECT rule_id, action, as_of, status, chunks_changed FROM provenance "
            "WHERE document_ref = ? ORDER BY id",
            (document_ref,),
        ).fetchall()
    finally:
        conn.close()


def test_r1_final_rule_writes_both_upsert_and_schedule_provenance_rows():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        cfg = _tmp_cfg(d)
        with patch("src.etl.pipeline.fedreg_watcher.poll", return_value=[_R1_DOC]):
            summary = pipeline._run_fedreg(cfg)

        assert summary == {"detected": 1, "upserted": 1, "skipped": 0, "errors": 0}

        rows = _provenance_rows(cfg, "2025-01374")
        actions = [r[1] for r in rows]
        assert "upsert" in actions, f"expected an upsert provenance row, got {rows}"
        assert "schedule" in actions, f"expected a schedule provenance row (R1), got {rows}"

        upsert_row = next(r for r in rows if r[1] == "upsert")
        schedule_row = next(r for r in rows if r[1] == "schedule")

        # both rows are tagged R1, both success
        assert upsert_row[0] == "R1" and upsert_row[3] == "success"
        assert schedule_row[0] == "R1" and schedule_row[3] == "success"

        # upsert row's as_of is the publication_date; schedule row's as_of is
        # the FedReg doc's effective_on (the "due date" for the eCFR re-pull)
        assert upsert_row[2] == "2025-01-17"
        assert schedule_row[2] == "2025-02-16"

        # schedule row records no chunk writes of its own (it's a marker, not a write)
        assert schedule_row[4] == 0
        # upsert row recorded the actual chunk count written
        assert upsert_row[4] == 1

        # the corpus actually has the upserted chunk
        col = get_collection(cfg)
        assert col.count() == 1


def test_r2_proposed_rule_writes_upsert_only_no_schedule_row():
    """Contrast case: R2 (Proposed Rule) must NOT get a schedule row — only R1
    (final Rule) schedules an eCFR re-pull per rules.classify_fedreg."""
    proposed_doc = {**_R1_DOC, "type": "Proposed Rule", "document_number": "2025-01375"}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        cfg = _tmp_cfg(d)
        with patch("src.etl.pipeline.fedreg_watcher.poll", return_value=[proposed_doc]):
            pipeline._run_fedreg(cfg)

        rows = _provenance_rows(cfg, "2025-01375")
        actions = [r[1] for r in rows]
        assert actions == ["upsert"], f"R2 must not write a schedule row, got {rows}"


def test_r1_schedule_row_survives_watermark_advance():
    """The watermark still advances normally on a fully-successful R1 batch
    (the extra schedule row is not treated as a second/failing item)."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        cfg = _tmp_cfg(d)
        with patch("src.etl.pipeline.fedreg_watcher.poll", return_value=[_R1_DOC]):
            pipeline._run_fedreg(cfg)

        wm = state.get_watermark(cfg, "fedreg")
        assert wm == ("2025-01-17", "2025-01374")


if __name__ == "__main__":
    test_r1_final_rule_writes_both_upsert_and_schedule_provenance_rows()
    test_r2_proposed_rule_writes_upsert_only_no_schedule_row()
    test_r1_schedule_row_survives_watermark_advance()
    print("etl pipeline R1 schedule ok")
