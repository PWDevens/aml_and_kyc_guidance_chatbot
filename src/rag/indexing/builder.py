"""ChromaDB index — persistent collection embedded with bge-small.
ponytail: chromadb's own SentenceTransformer embedding fn does the work;
naive dense retrieval needs no orchestration layer on top. LlamaIndex enters
in Phase 1 when hybrid/graph actually need it."""
from __future__ import annotations

import chromadb
from chromadb.utils import embedding_functions

from ..config import RagConfig

# metadata chroma can store (scalars only); keep the citable fields.
_META = ("citation", "heading", "source", "title", "chapter", "part", "section", "url", "as_of")


def _client(cfg: RagConfig):
    return chromadb.PersistentClient(path=cfg.chroma_path)


def _embed_fn(cfg: RagConfig):
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=cfg.embed_model)


def get_collection(cfg: RagConfig):
    return _client(cfg).get_collection(cfg.collection, embedding_function=_embed_fn(cfg))


def build(cfg: RagConfig, records: list[dict]) -> int:
    """(Re)create the collection from records. Returns count indexed."""
    client = _client(cfg)
    try:
        client.delete_collection(cfg.collection)
    except Exception:
        pass  # ponytail: first build, nothing to delete
    col = client.create_collection(cfg.collection, embedding_function=_embed_fn(cfg))
    col.add(
        ids=[r["id"] for r in records],
        documents=[r["text"] for r in records],
        metadatas=[{k: r.get(k, "") for k in _META} for r in records],
    )
    return col.count()
