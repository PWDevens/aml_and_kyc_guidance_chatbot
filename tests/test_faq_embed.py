"""Unit tests for src/rag/faq/embed.py (D1). Real model, not mocked — the
whole point of D1 is that this is cheap after the first (lazy, cached) load.
Run:  python -m pytest tests/test_faq_embed.py -q"""
from __future__ import annotations

import numpy as np

from src.rag.faq.embed import embed_queries, embed_query


def test_embed_query_shape_and_normalization():
    v = embed_query("What is the CTR filing threshold?")
    assert v.shape == (384,)
    assert v.dtype == np.float32
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-3


def test_embed_queries_batch_shape():
    vs = embed_queries(["a", "b", "c"])
    assert vs.shape == (3, 384)
    assert vs.dtype == np.float32
    for v in vs:
        assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-3


def test_cosine_via_dot_product_identical_text():
    v1 = embed_query("What is the CTR filing threshold?")
    v2 = embed_query("What is the CTR filing threshold?")
    assert float(np.dot(v1, v2)) > 0.999


def test_cosine_paraphrase_vs_unrelated():
    """Sanity check on the D2 measurement direction: a real paraphrase should
    score meaningfully higher than an unrelated question."""
    canonical = embed_query("What is the CTR filing threshold?")
    paraphrase = embed_query("when do I file a CTR")
    unrelated = embed_query("What is the weather forecast for tomorrow?")
    assert float(np.dot(canonical, paraphrase)) > float(np.dot(canonical, unrelated))


if __name__ == "__main__":
    test_embed_query_shape_and_normalization()
    test_embed_queries_batch_shape()
    test_cosine_via_dot_product_identical_text()
    test_cosine_paraphrase_vs_unrelated()
    print("faq embed ok")
