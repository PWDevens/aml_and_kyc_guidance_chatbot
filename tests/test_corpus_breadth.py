"""Behavior tests for AC-1 (expanded, schema-valid gold set) and AC-2 (corpus
breadth: eCFR + FinCEN FedReg docs indexed, multiple non-ecfr sources present).

Runs against the already-built index (same assumption as tests/test_smoke.py).
Run:  python -m pytest tests/test_corpus_breadth.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from src.app.api import app
from src.rag.config import CONFIG
from src.rag.retrieval.factory import retrieve

GOLD = Path(__file__).resolve().parents[1] / "data" / "eval" / "gold.jsonl"


def _load_gold() -> list[dict]:
    return [json.loads(l) for l in GOLD.read_text().splitlines() if l.strip()]


def test_gold_set_size_and_schema():
    items = _load_gold()
    assert 20 <= len(items) <= 30, f"expected 20-30 gold items, got {len(items)}"
    for it in items:
        assert set(it.keys()) == {"q", "expect_citation", "answer_contains"}
        assert it["q"].strip()
        assert it["expect_citation"].strip()
        assert it["answer_contains"].strip()


def test_gold_set_covers_non_ecfr_targets():
    items = _load_gold()
    non_ecfr = [it for it in items if "CFR" not in it["expect_citation"]]
    assert len(non_ecfr) >= 3, "expected several FedReg/advisory gold targets"


def test_gold_set_retrieval_runs_clean_naive_mode():
    """python -m scripts.eval-equivalent: every gold item is retrievable
    without raising, and hit@k over the set is reasonably high (regression
    guard, not a strict re-measure of AC-4's numbers)."""
    items = _load_gold()
    hits = 0
    for it in items:
        context, citations = retrieve(CONFIG, it["q"])
        cited = [c["citation"] for c in citations]
        if any(it["expect_citation"] in c for c in cited):
            hits += 1
    hit_rate = hits / len(items)
    assert hit_rate >= 0.8, f"hit@{CONFIG.retrieval_top_k} too low: {hit_rate:.2f}"


def test_corpus_status_shows_breadth_beyond_ecfr():
    client = app.test_client()
    r = client.get("/corpus_status")
    assert r.status_code == 200
    body = r.get_json()
    # AC-2: higher indexed count than the pre-iteration-1 105-chunk eCFR-only corpus
    assert body["indexed"] > 105

    col = __import__("src.rag.indexing.builder", fromlist=["get_collection"]).get_collection(CONFIG)
    got = col.get(include=["metadatas"])
    sources = {m.get("source") for m in got["metadatas"]}
    non_ecfr_sources = sources - {"ecfr"}
    assert len(non_ecfr_sources) >= 1, f"expected a non-ecfr source, got {sources}"


def test_fedreg_citations_resolve_with_working_url_and_source():
    """AC-7: FedReg citation objects carry a working url and correct
    source/citation, not just eCFR ones."""
    items = [it for it in _load_gold() if "CFR" not in it["expect_citation"]]
    assert items, "no non-eCFR gold items to check"
    found_any = False
    for it in items:
        _, citations = retrieve(CONFIG, it["q"])
        for c in citations:
            if it["expect_citation"] in c["citation"]:
                found_any = True
                assert c["url"].startswith("https://www.federalregister.gov/")
                assert c["source"] in ("fedreg_rule", "fedreg_proposed", "fincen_advisory", "fedreg")
    assert found_any, "expected at least one non-eCFR gold citation to resolve"


if __name__ == "__main__":
    test_gold_set_size_and_schema()
    test_gold_set_covers_non_ecfr_targets()
    test_gold_set_retrieval_runs_clean_naive_mode()
    test_corpus_status_shows_breadth_beyond_ecfr()
    test_fedreg_citations_resolve_with_working_url_and_source()
    print("corpus breadth ok")
