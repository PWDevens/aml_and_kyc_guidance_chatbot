"""ChromaDB index — persistent collection embedded with bge-small.
Deliberately minimal: chromadb's own SentenceTransformer embedding fn does the
work; naive dense retrieval needs no orchestration layer on top. LlamaIndex
enters in Phase 1 when hybrid/graph actually need it."""
from __future__ import annotations

import chromadb
from chromadb.utils import embedding_functions

from ..config import RagConfig

# metadata chroma can store (scalars only); keep the citable fields.
_META = ("citation", "heading", "source", "title", "chapter", "part", "section", "url", "as_of",
          "fedreg_doc_number", "publication_date")


def _client(cfg: RagConfig):
    return chromadb.PersistentClient(path=cfg.chroma_path)


def _embed_fn(cfg: RagConfig):
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=cfg.embed_model)


def get_collection(cfg: RagConfig):
    return _client(cfg).get_collection(cfg.collection, embedding_function=_embed_fn(cfg))


def collection_exists(cfg: RagConfig) -> bool:
    """True if the Chroma collection is present (get_collection raises if not)."""
    try:
        get_collection(cfg)
        return True
    except Exception:
        return False


def _add_args(records: list[dict]) -> dict:
    """Shared ids/documents/metadatas construction, reused by build() and
    upsert_by_citation() so both write the identical record shape."""
    return {
        "ids": [r["id"] for r in records],
        "documents": [r["text"] for r in records],
        "metadatas": [{k: r.get(k, "") for k in _META} for r in records],
    }


def build(cfg: RagConfig, records: list[dict]) -> int:
    """(Re)create the collection from records. Returns count indexed."""
    client = _client(cfg)
    try:
        client.delete_collection(cfg.collection)
    except Exception:
        pass  # expected on the first build — nothing to delete yet
    col = client.create_collection(cfg.collection, embedding_function=_embed_fn(cfg))
    col.add(**_add_args(records))
    return col.count()


def upsert_by_citation(cfg: RagConfig, citation: str, records: list[dict]) -> int:
    """Incremental upsert against the EXISTING collection (ETL path only —
    never calls build()/delete_collection, which would wipe the whole index).
    Deletes all chunks currently stored under `citation`, then adds `records`.
    Idempotent: re-running with the same records yields the same final state,
    because the citation's old chunks are cleared first every time."""
    client = _client(cfg)
    col = client.get_or_create_collection(cfg.collection, embedding_function=_embed_fn(cfg))
    existing = col.get(where={"citation": citation}, include=[])
    if existing["ids"]:
        col.delete(ids=existing["ids"])
    if records:
        col.add(**_add_args(records))
    return len(records)
