"""Thin orchestration state machine (D8b): plan(cfg, question) runs
frame -> classify -> route and returns the per-request retrieval config +
hints + intent. api.py calls retrieve(result["cfg"], question) itself — the
planner only *selects*, it never forks or duplicates the serving path
(ARCHITECTURE §3 "one serving path").

Also exposes:
  - citation_fetch(cfg, citation): the D8a "direct fetch" row of the routing
    matrix — a direct Chroma get(where={"citation": ...}) for citation-lookup
    intent, added as a new helper (not a change to factory.py's retrieve()
    signature). Falls back to the semantic mode when the filtered fetch
    returns nothing (edge case in the spec).
  - budget bookkeeping for ORCHESTRATION_MAX_LLM_CALLS: this iteration's
    framer/classifier/verifier are all heuristic-only (D13, D12), so no LLM
    calls are actually spent yet, but the counter is real and enforced so a
    future LLM-escalation path (D12's gray-band entailment prompt) has
    somewhere correct to check against."""
from __future__ import annotations

from dataclasses import replace

from ..config import RagConfig
from ..retrieval.factory import _format
from . import router
from .intents import classify_intent, frame_query


class Budget:
    """Tracks LLM calls spent this request against ORCHESTRATION_MAX_LLM_CALLS."""

    def __init__(self, max_calls: int):
        self.max_calls = max_calls
        self.spent = 0

    def has_budget(self) -> bool:
        return self.spent < self.max_calls

    def spend(self) -> bool:
        """Attempt to spend one call; returns False if over budget (caller
        must degrade gracefully rather than block — edge case in the spec)."""
        if not self.has_budget():
            return False
        self.spent += 1
        return True


def frame_query_hints(question: str) -> dict:
    """Framing only (no classify/route) — used by the Tier-1 FAQ fast-path
    (D9 step 1), which runs independently of ORCHESTRATION and doesn't need
    a retrieval-mode decision. Returns {"framed_query", "hints"}."""
    framed = frame_query(question)
    return {
        "framed_query": framed["framed_query"],
        "hints": {
            "citation_hint": framed["citation_hint"],
            "numeric_hint": framed["numeric_hint"],
            "glossary_expansions": framed["glossary_expansions"],
        },
    }


def plan(cfg: RagConfig, question: str) -> dict:
    """frame -> classify -> route -> per-request RagConfig.
    Returns {"cfg", "intent", "hints", "confidence", "budget"}."""
    budget = Budget(cfg.orchestration_max_llm_calls)

    framed = frame_query(question)  # heuristic-only (D13) — no LLM call
    classified = classify_intent(framed)  # heuristic-only (D13) — no LLM call
    intent = classified["intent"]

    hints = {
        "citation_hint": framed["citation_hint"],
        "numeric_hint": framed["numeric_hint"],
        "glossary_expansions": framed["glossary_expansions"],
    }

    route_result = router.route(intent, hints)

    # D8b: dataclasses.replace against the frozen RagConfig — never mutate
    # CONFIG, never let a per-request top_k leak into the process-global cfg.
    per_request_cfg = replace(
        cfg,
        rag_mode=route_result["rag_mode"],
        retrieval_top_k=route_result["top_k"],
    )

    return {
        "cfg": per_request_cfg,
        "intent": intent,
        "hints": hints,
        "confidence": classified["confidence"],
        "filters": route_result["filters"],
        "framed_query": framed["framed_query"],
        "budget": budget,
    }


def citation_fetch(cfg: RagConfig, citation: str) -> tuple[str, list[dict]] | None:
    """D8a direct fetch: exact Chroma metadata get for a citation-lookup
    intent. Returns (context, citations) same shape as factory.retrieve(),
    or None if nothing matched (caller falls back to the intent's normal
    semantic mode)."""
    from ..indexing.builder import get_collection

    col = get_collection(cfg)
    got = col.get(where={"citation": citation}, include=["documents", "metadatas"])
    docs, metas = got.get("documents") or [], got.get("metadatas") or []
    if not docs:
        return None
    return _format(docs, metas)
