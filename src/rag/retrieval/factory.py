"""Retrieval factory. `naive` (dense) and `hybrid` (dense + BM25, RRF-fused).
Both honour the same (context, citations) contract — ARCHITECTURE §3 "one serving
path". `graph` slots in later behind the same contract.
ponytail: dict dispatch; BM25 built once over the (small) corpus and cached.
Cross-encoder rerank is a thin add-on once hybrid's pool quality is measured."""
from __future__ import annotations

from functools import lru_cache

from ..config import RagConfig
from ..indexing.builder import get_collection

_RRF_K = 60  # standard RRF constant


def _format(docs: list[str], metas: list[dict]) -> tuple[str, list[dict]]:
    citations = [{"citation": m.get("citation", ""), "heading": m.get("heading", ""),
                  "url": m.get("url", ""), "source": m.get("source", ""),
                  "as_of": m.get("as_of", "")} for m in metas]
    context = "\n\n".join(
        f"[{m.get('citation','')}] {m.get('heading','')}\n{d}" for d, m in zip(docs, metas)
    )
    return context, citations


def _naive(cfg: RagConfig, question: str) -> tuple[str, list[dict]]:
    res = get_collection(cfg).query(query_texts=[question], n_results=cfg.retrieval_top_k)
    return _format(res["documents"][0], res["metadatas"][0])


@lru_cache(maxsize=1)
def _corpus(chroma_path: str, collection: str):
    """All (id, doc, meta) + a BM25 index. Cached; corpus is small and static
    between rebuilds. ponytail: in-memory BM25, no separate index store."""
    from rank_bm25 import BM25Okapi
    from ..config import RagConfig
    cfg = RagConfig()  # re-read; only used for client params here
    col = get_collection(cfg)
    got = col.get(include=["documents", "metadatas"])
    docs, metas = got["documents"], got["metadatas"]
    bm25 = BM25Okapi([d.lower().split() for d in docs])
    return docs, metas, bm25


def _hybrid(cfg: RagConfig, question: str) -> tuple[str, list[dict]]:
    docs, metas, bm25 = _corpus(cfg.chroma_path, cfg.collection)
    pool = min(len(docs), max(cfg.retrieval_top_k * 4, 20))

    # dense ranking (by chroma distance, ascending) over a candidate pool
    dres = get_collection(cfg).query(query_texts=[question], n_results=pool)
    dense_ids = [m.get("citation") for m in dres["metadatas"][0]]

    # bm25 ranking over the whole corpus
    scores = bm25.get_scores(question.lower().split())
    bm25_order = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)[:pool]
    bm25_ids = [metas[i].get("citation") for i in bm25_order]

    # Reciprocal Rank Fusion
    fused: dict[str, float] = {}
    for rank, cid in enumerate(dense_ids):
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (_RRF_K + rank)
    for rank, cid in enumerate(bm25_ids):
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (_RRF_K + rank)

    by_cite = {metas[i].get("citation"): (docs[i], metas[i]) for i in range(len(docs))}
    top = sorted(fused, key=fused.get, reverse=True)[:cfg.retrieval_top_k]
    chosen = [by_cite[c] for c in top if c in by_cite]
    return _format([d for d, _ in chosen], [m for _, m in chosen])


_MODES = {"naive": _naive, "hybrid": _hybrid}


def retrieve(cfg: RagConfig, question: str) -> tuple[str, list[dict]]:
    fn = _MODES.get(cfg.rag_mode)
    if fn is None:
        raise ValueError(f"RAG_MODE={cfg.rag_mode!r} not built yet (have: {list(_MODES)})")
    return fn(cfg, question)
