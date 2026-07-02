"""One runnable check: upsert-by-citation idempotency against a throwaway
Chroma collection in a tempdir (no live index dependency) — AC-3.
Run:  python -m pytest tests/test_etl_upsert.py -q"""
import tempfile
from dataclasses import replace
from pathlib import Path

from src.rag.config import CONFIG
from src.rag.indexing.builder import build, get_collection, upsert_by_citation

_CITATION = "31 CFR 1010.311"

_INITIAL = [
    {"id": "ecfr-31-1010.311", "text": "old text about currency thresholds",
     "citation": _CITATION, "heading": "old heading", "source": "ecfr", "as_of": "2020-01-01"},
]
_UPDATED = [
    {"id": "ecfr-31-1010.311", "text": "new text about currency thresholds v2",
     "citation": _CITATION, "heading": "new heading", "source": "ecfr", "as_of": "2026-01-05"},
]
_OTHER = [
    {"id": "ecfr-31-1010.100", "text": "unrelated section, untouched",
     "citation": "31 CFR 1010.100", "heading": "definitions", "source": "ecfr", "as_of": "2020-01-01"},
]


def test_upsert_by_citation_idempotent_no_stale_duplicates():
    # ignore_cleanup_errors: Chroma's PersistentClient keeps its sqlite/HNSW
    # files open for the life of the process, which trips Windows' delete-
    # while-open rule during tempdir teardown; the assertions above already
    # ran by then, so a cleanup failure here is not a test failure.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        cfg = replace(CONFIG, chroma_path=str(Path(d) / "chroma"), collection="etl_test")
        build(cfg, _INITIAL + _OTHER)
        col = get_collection(cfg)
        assert col.count() == 2

        n = upsert_by_citation(cfg, _CITATION, _UPDATED)
        assert n == 1
        col = get_collection(cfg)
        assert col.count() == 2  # unchanged: 1 for _CITATION + 1 for _OTHER

        got = col.get(where={"citation": _CITATION}, include=["documents"])
        assert got["documents"] == ["new text about currency thresholds v2"]
        assert "old text" not in got["documents"][0]

        # re-run with the SAME updated batch: count stable, no duplicate ids
        upsert_by_citation(cfg, _CITATION, _UPDATED)
        col = get_collection(cfg)
        assert col.count() == 2
        got_again = col.get(where={"citation": _CITATION}, include=["documents"])
        assert got_again["documents"] == ["new text about currency thresholds v2"]


def test_upsert_by_citation_creates_collection_if_absent():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        cfg = replace(CONFIG, chroma_path=str(Path(d) / "chroma"), collection="etl_test_fresh")
        # no build() call — collection does not exist yet
        n = upsert_by_citation(cfg, _CITATION, _INITIAL)
        assert n == 1
        assert get_collection(cfg).count() == 1


if __name__ == "__main__":
    test_upsert_by_citation_idempotent_no_stale_duplicates()
    test_upsert_by_citation_creates_collection_if_absent()
    print("etl upsert ok")
