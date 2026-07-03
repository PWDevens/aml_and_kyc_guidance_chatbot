"""Eval harness — retrieval relevance on the gold set (ROADMAP §4).
Measures the Phase-0 `naive` baseline so later phases prove gains against a number.
Run:  python -m scripts.eval
ponytail: retrieval-only metrics (hit@k + term recall) — fast, no CPU generation.
Generation-quality scoring is the AML/KYC SME's manual line-by-line pass + a
Phase-3 verifier; not worth a metric framework yet.

Phase 3 (AC-9): also runs the on-vs-off orchestration comparison over the
same gold set, since ORCHESTRATION ships false by default (D6) and the flip
decision needs a measured number, not a guess. This reuses retrieve() exactly
as chat_stream's orchestrated path does (frame -> classify -> route -> the
per-request cfg from planner.plan()) — no separate serving path (ARCHITECTURE
§3). `python -m scripts.eval --compare` runs both and prints the comparison;
plain `python -m scripts.eval` keeps the original single-mode baseline run
unchanged."""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from src.rag.config import CONFIG
from src.rag.orchestration.planner import plan
from src.rag.retrieval.factory import retrieve

GOLD = Path(__file__).resolve().parents[1] / "data" / "eval" / "gold.jsonl"


def _load_gold() -> list[dict]:
    return [json.loads(l) for l in GOLD.read_text().splitlines() if l.strip()]


def run() -> dict:
    items = _load_gold()
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
    print(f"\n{CONFIG.rag_mode} baseline  hit@{CONFIG.retrieval_top_k}={res['hit_rate']:.2f}  "
          f"term_recall={res['term_recall']:.2f}")
    return res


def _run_orchestrated(items: list[dict]) -> dict:
    """Same hit@k / term_recall metrics, but through the orchestrated
    frame->classify->route->retrieve path (planner.plan against a per-request
    RagConfig with orchestration=True) instead of the single default mode."""
    cfg = replace(CONFIG, orchestration=True)
    hits = terms = 0
    for it in items:
        result = plan(cfg, it["q"])
        context, cites = retrieve(result["cfg"], it["q"])
        cited = [c["citation"] for c in cites]
        hit = any(it["expect_citation"] in c for c in cited)
        term = it.get("answer_contains", "").lower() in context.lower()
        hits += hit
        terms += term
    n = len(items)
    return {"n": n, "hit_rate": hits / n, "term_recall": terms / n}


def _run_off(items: list[dict]) -> dict:
    """The single-default-mode path, unchanged (ORCHESTRATION=false)."""
    hits = terms = 0
    for it in items:
        context, cites = retrieve(CONFIG, it["q"])
        cited = [c["citation"] for c in cites]
        hit = any(it["expect_citation"] in c for c in cited)
        term = it.get("answer_contains", "").lower() in context.lower()
        hits += hit
        terms += term
    n = len(items)
    return {"n": n, "hit_rate": hits / n, "term_recall": terms / n}


def run_comparison() -> dict:
    """AC-9: ORCHESTRATION=true vs =false over the gold set, retrieval-only
    metrics (same hit@k / term_recall basis as run(), so the numbers are
    directly comparable). Generation/verification quality is out of scope
    for this fast retrieval-relevance comparison — see changes.md for why
    (CPU-slow generation makes a 25-item x 2-pass generation eval expensive;
    the routing decision is a retrieval-relevance question first)."""
    items = _load_gold()
    print(f"Eval comparison: {len(items)} gold items\n")

    off = _run_off(items)
    print(f"ORCHESTRATION=false (single default mode={CONFIG.rag_mode}, top_k={CONFIG.retrieval_top_k}):"
          f"  hit@k={off['hit_rate']:.2f}  term_recall={off['term_recall']:.2f}")

    on = _run_orchestrated(items)
    print(f"ORCHESTRATION=true  (per-intent routed mode/top_k):"
          f"  hit@k={on['hit_rate']:.2f}  term_recall={on['term_recall']:.2f}")

    delta_hit = on["hit_rate"] - off["hit_rate"]
    delta_term = on["term_recall"] - off["term_recall"]
    print(f"\nDelta (on - off): hit@k={delta_hit:+.2f}  term_recall={delta_term:+.2f}")

    return {"off": off, "on": on, "delta_hit_rate": delta_hit, "delta_term_recall": delta_term}


if __name__ == "__main__":
    if "--compare" in sys.argv:
        run_comparison()
    else:
        run()
