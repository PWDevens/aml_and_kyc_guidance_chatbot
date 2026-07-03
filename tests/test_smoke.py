"""One runnable check: index a known section, retrieve it, confirm the right
citation surfaces. The eval set (data/eval/gold.jsonl) grows this in later phases.
Run:  python -m pytest tests/ -q   (requires a built index)
Deliberately minimal: a single end-to-end retrieval assertion, no fixtures/framework."""
from src.rag.config import CONFIG
from src.rag.retrieval.factory import retrieve


def test_ctr_threshold_retrieves_1010_311():
    context, citations = retrieve(CONFIG, "currency transaction report $10,000 threshold")
    cites = [c["citation"] for c in citations]
    assert any("1010.311" in c for c in cites), f"expected 1010.311 in {cites}"
    assert "10,000" in context


if __name__ == "__main__":
    test_ctr_threshold_retrieves_1010_311()
    print("smoke ok")
