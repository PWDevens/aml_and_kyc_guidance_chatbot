"""Eval harness — retrieval relevance on the gold set (ROADMAP §4).
Measures the Phase-0 `naive` baseline so later phases prove gains against a number.
Run:  python -m scripts.eval
ponytail: retrieval-only metrics (hit@k + term recall) — fast, no CPU generation.
Generation-quality scoring is the AML/KYC SME's manual line-by-line pass + a
Phase-3 verifier; not worth a metric framework yet."""
from __future__ import annotations

import json
from pathlib import Path

from src.rag.config import CONFIG
from src.rag.retrieval.factory import retrieve

GOLD = Path(__file__).resolve().parents[1] / "data" / "eval" / "gold.jsonl"


def run() -> dict:
    items = [json.loads(l) for l in GOLD.read_text().splitlines() if l.strip()]
    hits = terms = 0
    print(f"Eval: {len(items)} gold items · RAG_MODE={CONFIG.rag_mode} · top_k={CONFIG.retrieval_top_k}\n")
    for it in items:
        context, cites = retrieve(CONFIG, it["q"])
        cited = [c["citation"] for c in cites]
        hit = any(it["expect_citation"] in c for c in cited)          # cite found in top-k?
        term = it.get("answer_contains", "").lower() in context.lower()  # key term retrievable?
        hits += hit
        terms += term
        rank = next((i + 1 for i, c in enumerate(cited) if it["expect_citation"] in c), None)
        print(f"  [{'HIT' if hit else 'MISS'} @{rank}] [{'term' if term else '----'}] "
              f"{it['expect_citation']:18} {it['q'][:60]}")
    n = len(items)
    res = {"n": n, "hit_rate": hits / n, "term_recall": terms / n}
    print(f"\nnaive baseline  hit@{CONFIG.retrieval_top_k}={res['hit_rate']:.2f}  "
          f"term_recall={res['term_recall']:.2f}")
    return res


if __name__ == "__main__":
    run()
