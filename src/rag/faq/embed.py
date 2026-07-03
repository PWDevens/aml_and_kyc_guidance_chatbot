"""Request-time embedding helper for the semantic FAQ cache (Phase 3, D1).

The corpus itself is only ever embedded at build/upsert time, inside Chroma's
own SentenceTransformerEmbeddingFunction (src/rag/indexing/builder.py). The
FAQ matcher needs a standalone embed(text) -> vector call so it can compare a
live query against pre-computed FAQ entry vectors. Measured locally against
the already-cached bge-small-en-v1.5: one-time model load ~13s (lazy,
first call only), encode() ~0.07s/call after load, 384-dim float32,
L2-normalized (normalize_embeddings=True) so cosine similarity reduces to a
plain dot product.

Lazy @lru_cache(maxsize=1)-per-model-name singleton, same pattern as
src/rag/retrieval/factory.py::_reranker and src/rag/llm/models.py::_load."""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from ..config import CONFIG


@lru_cache(maxsize=1)
def _model(model_name: str):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)


def embed_query(text: str, model_name: str | None = None) -> np.ndarray:
    """Embed a single query string. Returns a (384,) float32 L2-normalized vector."""
    return embed_queries([text], model_name)[0]


def embed_queries(texts: list[str], model_name: str | None = None) -> np.ndarray:
    """Embed a batch of strings. Returns an (n, 384) float32 L2-normalized array."""
    model = _model(model_name or CONFIG.embed_model)
    vecs = model.encode(texts, normalize_embeddings=True)
    return np.asarray(vecs, dtype=np.float32)
