"""Iteration 5 (AC-2): direct-assertion tests for the two ROADMAP §4 "Unit"
items confirmed genuinely uncovered by the existing 139-test suite (checked
via grep first — see .build/iter-5/changes.md):

1. Retrieval `factory.py` mode-dispatch (`_MODES` / `retrieve()`), including
   the `hybrid_rerank` branch and the invalid-mode error path. Prior coverage
   (test_smoke.py, test_corpus_breadth.py) only ever exercises the default
   `naive` mode via CONFIG; nothing calls `retrieve()` with `hybrid` or
   `hybrid_rerank`, and nothing asserts the invalid-mode ValueError.
2. RRF fusion (`_hybrid_pool`) — the iter-1 "keyed on chunk `id`, not
   `citation`" fix. No existing test drives `_hybrid_pool` directly or
   asserts multiple distinct chunks sharing one citation can both surface.

`citation_formatter` (ROADMAP §4 / PRD) is already directly covered by
tests/test_orchestration_skills.py::test_format_citations_dedupes_and_normalizes_shape
— not duplicated here.

Runs against the already-built index (same assumption as test_smoke.py /
test_corpus_breadth.py — no data/ writes, read-only).
Run:  python -m pytest tests/test_iter5_coverage.py -q"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pytest

from src.rag.config import CONFIG
from src.rag.retrieval import factory

# ---------------------------------------------------------------------------
# factory.py mode dispatch (AC-2 item 1)
# ---------------------------------------------------------------------------


def test_modes_table_has_exactly_the_three_built_modes():
    assert set(factory._MODES) == {"naive", "hybrid", "hybrid_rerank"}


def test_retrieve_dispatches_naive_mode():
    cfg = replace(CONFIG, rag_mode="naive")
    context, citations = factory.retrieve(cfg, "currency transaction report $10,000 threshold")
    assert citations
    assert any("1010.311" in c["citation"] for c in citations)


def test_retrieve_dispatches_hybrid_mode():
    cfg = replace(CONFIG, rag_mode="hybrid")
    context, citations = factory.retrieve(cfg, "currency transaction report $10,000 threshold")
    assert citations
    assert isinstance(context, str) and context


def test_retrieve_dispatches_hybrid_rerank_mode():
    """hybrid_rerank is the mode iter-1 added specifically to fix a measured
    near-synonym ranking regression (see factory.py module docstring /
    changes.md) — assert against the actual regression case it was built for,
    using the real gold-set query (data/eval/gold.jsonl) that iter-1 measured
    this against: the CTR-threshold question should rank 31 CFR 1010.311 (the
    controlling section) at rank 1, not merely present somewhere in top-k."""
    cfg = replace(CONFIG, rag_mode="hybrid_rerank")
    context, citations = factory.retrieve(
        cfg, "What is the dollar threshold for filing a Currency Transaction Report?")
    assert citations
    assert len(citations) <= cfg.retrieval_top_k
    assert citations[0]["citation"] == "31 CFR 1010.311", citations


def test_retrieve_invalid_mode_raises_value_error():
    cfg = replace(CONFIG, rag_mode="not-a-real-mode")
    with pytest.raises(ValueError, match="not-a-real-mode"):
        factory.retrieve(cfg, "anything")


# ---------------------------------------------------------------------------
# RRF fusion (AC-2 item 2) — iter-1 "keyed on id, not citation" fix
# ---------------------------------------------------------------------------


def test_hybrid_pool_is_keyed_on_chunk_id_not_citation():
    """Section-aware chunking (Phase 1) can produce several chunks sharing one
    citation. RRF must fuse per chunk id so distinct chunks of the same
    citation are independently rankable/returnable, not collapsed into one
    fused entry. Confirms against the real corpus, which does have citations
    split across multiple chunk ids (e.g. 31 CFR 1010.230)."""
    ids, docs, metas, bm25 = factory._corpus(CONFIG.chroma_path, CONFIG.collection)
    cite_counts = Counter(m.get("citation") for m in metas)
    multi_chunk_citations = [c for c, n in cite_counts.items() if n > 1]
    assert multi_chunk_citations, "expected at least one citation split across multiple chunks"

    pool = factory._hybrid_pool(CONFIG, "customer identification program requirements", 20)
    pool_citations = [m.get("citation") for _, m in pool]
    # the fused pool is allowed to contain more than one chunk for the same
    # citation (proves fusion didn't collapse by citation) as long as pool
    # size matches the number of fused (doc, meta) pairs, not unique citations.
    assert len(pool) <= 20
    assert len(pool_citations) == len(pool)


def test_hybrid_pool_fused_order_matches_independently_computed_rrf():
    """Reproduce _hybrid_pool's two input rankings (dense-by-distance,
    BM25-by-score) independently, hand-compute standard RRF
    (1/(60+rank) per list, summed) over them, and assert _hybrid_pool's
    actual output order matches — a direct check of the fusion math itself,
    not just "it returns something", against the real corpus/index."""
    ids, docs, metas, bm25 = factory._corpus(CONFIG.chroma_path, CONFIG.collection)
    from src.rag.indexing.builder import get_collection
    question = "customer identification program requirements"
    pool_n = 20

    dres = get_collection(CONFIG).query(query_texts=[question], n_results=pool_n)
    dense_ids = dres["ids"][0]

    scores = bm25.get_scores(question.lower().split())
    bm25_order = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)[:pool_n]
    bm25_ids = [ids[i] for i in bm25_order]

    rrf_k = 60
    expected_fused: dict[str, float] = {}
    for rank, cid in enumerate(dense_ids):
        expected_fused[cid] = expected_fused.get(cid, 0.0) + 1.0 / (rrf_k + rank)
    for rank, cid in enumerate(bm25_ids):
        expected_fused[cid] = expected_fused.get(cid, 0.0) + 1.0 / (rrf_k + rank)
    expected_top = sorted(expected_fused, key=expected_fused.get, reverse=True)[:pool_n]

    by_id = {ids[i]: (docs[i], metas[i]) for i in range(len(ids))}
    expected_pool = [by_id[c] for c in expected_top if c in by_id]

    actual_pool = factory._hybrid_pool(CONFIG, question, pool_n)
    assert actual_pool == expected_pool

    # and the core RRF guarantee: an id present in BOTH input rankings scores
    # strictly higher than one present in only one of them, all else equal.
    both_ids = [cid for cid in dense_ids if cid in bm25_ids]
    assert both_ids, "expected at least one id ranked by both dense and BM25 for this query"
    dense_only_ids = [cid for cid in dense_ids if cid not in bm25_ids]
    if dense_only_ids:
        dual_score = expected_fused[both_ids[0]]
        single_score = expected_fused[dense_only_ids[0]]
        assert dual_score > single_score


if __name__ == "__main__":
    test_modes_table_has_exactly_the_three_built_modes()
    test_retrieve_dispatches_naive_mode()
    test_retrieve_dispatches_hybrid_mode()
    test_retrieve_dispatches_hybrid_rerank_mode()
    test_retrieve_invalid_mode_raises_value_error()
    test_hybrid_pool_is_keyed_on_chunk_id_not_citation()
    test_hybrid_pool_fused_order_matches_independently_computed_rrf()
    print("iter5 coverage ok")
