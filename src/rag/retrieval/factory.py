"""Retrieval factory. `naive` (dense), `hybrid` (dense + BM25, RRF-fused), and
`hybrid_rerank` (hybrid pool + cross-encoder rerank). All honour the same
(context, citations) contract — ARCHITECTURE §3 "one serving path". `graph`
slots in later behind the same contract.
Deliberately minimal: plain dict dispatch; BM25 built once over the (small)
corpus and cached. `hybrid_rerank` exists because the expanded gold-set eval (iter-1) measured a
real hybrid ranking regression (near-synonym eCFR sections outranking the
controlling one) that the cross-encoder rerank demonstrably fixes — see
changes.md. `rag_mode` default is unaffected (naive still ties/wins overall);
`hybrid_rerank` is available, evidence-backed infra, not (yet) the default."""
from __future__ import annotations

from functools import lru_cache

from ..config import RagConfig
from ..indexing.builder import get_collection

_RRF_K = 60  # standard RRF constant
_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


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
    between rebuilds. Deliberately minimal: in-memory BM25, no separate index store."""
    from rank_bm25 import BM25Okapi
    from ..config import RagConfig
    cfg = RagConfig()  # re-read; only used for client params here
    col = get_collection(cfg)
    got = col.get(include=["documents", "metadatas"])
    ids, docs, metas = got["ids"], got["documents"], got["metadatas"]
    bm25 = BM25Okapi([d.lower().split() for d in docs])
    return ids, docs, metas, bm25


def _hybrid_pool(cfg: RagConfig, question: str, pool_n: int) -> list[tuple[str, dict]]:
    """RRF-fused (dense + BM25) candidates, best first, as (doc, meta) pairs."""
    ids, docs, metas, bm25 = _corpus(cfg.chroma_path, cfg.collection)
    pool_n = min(len(docs), pool_n)

    # dense ranking (by chroma distance, ascending) over a candidate pool
    # keyed on chunk id, not citation — section-aware chunking (Phase 1) can
    # produce several chunks sharing one citation, and each is a distinct
    # retrievable unit that RRF should rank independently.
    dres = get_collection(cfg).query(query_texts=[question], n_results=pool_n)
    dense_ids = dres["ids"][0]

    # bm25 ranking over the whole corpus
    scores = bm25.get_scores(question.lower().split())
    bm25_order = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)[:pool_n]
    bm25_ids = [ids[i] for i in bm25_order]

    # Reciprocal Rank Fusion
    fused: dict[str, float] = {}
    for rank, cid in enumerate(dense_ids):
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (_RRF_K + rank)
    for rank, cid in enumerate(bm25_ids):
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (_RRF_K + rank)

    by_id = {ids[i]: (docs[i], metas[i]) for i in range(len(docs))}
    top = sorted(fused, key=fused.get, reverse=True)[:pool_n]
    return [by_id[c] for c in top if c in by_id]


def _hybrid(cfg: RagConfig, question: str) -> tuple[str, list[dict]]:
    pool_n = max(cfg.retrieval_top_k * 4, 20)
    chosen = _hybrid_pool(cfg, question, pool_n)[:cfg.retrieval_top_k]
    return _format([d for d, _ in chosen], [m for _, m in chosen])


@lru_cache(maxsize=1)
def _reranker():
    from sentence_transformers import CrossEncoder
    return CrossEncoder(_RERANK_MODEL)


def _hybrid_rerank(cfg: RagConfig, question: str) -> tuple[str, list[dict]]:
    """Hybrid's RRF pool, re-scored by the cross-encoder (question, doc_text)
    pairs and truncated to top_k. Exists because hybrid alone measurably
    demotes controlling sections behind lexically-similar ones — see
    module docstring and changes.md."""
    pool_n = max(cfg.retrieval_top_k * 4, 20)
    pool = _hybrid_pool(cfg, question, pool_n)
    ce = _reranker()
    scores = ce.predict([(question, d) for d, _ in pool])
    ranked = sorted(zip(pool, scores), key=lambda x: x[1], reverse=True)
    chosen = [dm for dm, _ in ranked[:cfg.retrieval_top_k]]
    return _format([d for d, _ in chosen], [m for _, m in chosen])


_MODES = {"naive": _naive, "hybrid": _hybrid, "hybrid_rerank": _hybrid_rerank}


def retrieve(cfg: RagConfig, question: str) -> tuple[str, list[dict]]:
    fn = _MODES.get(cfg.rag_mode)
    if fn is None:
        raise ValueError(f"RAG_MODE={cfg.rag_mode!r} not built yet (have: {list(_MODES)})")
    return fn(cfg, question)
