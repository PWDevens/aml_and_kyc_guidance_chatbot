"""One runnable check: cache a write then replay it on an exact (normalized)
match, using a throwaway sqlite file so this test never touches the real
answer_cache.db.
Run:  python -m pytest tests/test_cache.py -q
Uses a tempfile-backed RagConfig, no fixtures/framework."""
import tempfile
from dataclasses import replace
from pathlib import Path

from src.rag import cache
from src.rag.config import CONFIG


def test_cache_round_trip_and_normalization():
    with tempfile.TemporaryDirectory() as d:
        cfg = replace(CONFIG, cache_path=str(Path(d) / "test_cache.db"))
        assert cache.get(cfg, "What is the CTR threshold?") is None

        citations = [{"citation": "31 CFR 1010.311", "heading": "", "url": "", "source": "ecfr", "as_of": "2026-01-01"}]
        cache.put(cfg, "What is the CTR threshold?", "It is $10,000.", citations, "2026-01-01")

        # exact-match replay, case/whitespace-insensitive (normalized key)
        hit = cache.get(cfg, "  what is the ctr threshold?  ")
        assert hit is not None
        assert hit["answer"] == "It is $10,000."
        assert hit["citations"] == citations
        assert hit["as_of"] == "2026-01-01"


if __name__ == "__main__":
    test_cache_round_trip_and_normalization()
    print("cache round-trip ok")
