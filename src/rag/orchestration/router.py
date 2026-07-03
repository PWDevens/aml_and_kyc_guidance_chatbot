"""retrieval_router (D8) — maps a classified intent + hints to retrieval
knobs. Dict-dispatch table like src/rag/retrieval/factory.py::_MODES and
src/etl/rules.py. Emits ONLY the 3 real modes ({"naive","hybrid",
"hybrid_rerank"}) — `graph` is not built (D8), so `cross-reference` falls
back to `hybrid_rerank` per the doc's own §4 fallback note.

D8b: this module only *selects* knobs; it never calls retrieve() itself and
never forks the serving path. The planner applies the returned dict via
dataclasses.replace(CONFIG, ...)."""
from __future__ import annotations

# Intent -> (rag_mode, top_k, top_n). top_n is only meaningful for
# hybrid_rerank (rerank pool size before truncation to top_k); harmless to
# carry for the other modes since RagConfig doesn't have a top_n field yet —
# callers only use top_k against retrieval_top_k.
_ROUTES: dict[str, dict] = {
    "definitional":     {"rag_mode": "hybrid_rerank", "top_k": 5, "top_n": 20},
    "numeric":          {"rag_mode": "hybrid_rerank", "top_k": 5, "top_n": 20},
    "procedural":       {"rag_mode": "hybrid_rerank", "top_k": 6, "top_n": 24},
    "cross-reference":  {"rag_mode": "hybrid_rerank", "top_k": 6, "top_n": 24},
    "change":           {"rag_mode": "hybrid_rerank", "top_k": 5, "top_n": 20},
    "citation-lookup":  {"rag_mode": "naive", "top_k": 5, "top_n": 5},
}

_REAL_MODES = {"naive", "hybrid", "hybrid_rerank"}


def route(intent: str, hints: dict) -> dict:
    """Return {"rag_mode", "top_k", "top_n", "filters"}. `rag_mode` is always
    one of _REAL_MODES. citation-lookup additionally carries a `filters`
    dict with the normalized citation hint (D8a); other intents get {}."""
    route_cfg = _ROUTES.get(intent, _ROUTES["definitional"])
    assert route_cfg["rag_mode"] in _REAL_MODES  # D8 hard constraint

    filters: dict = {}
    if intent == "citation-lookup" and hints.get("citation_hint"):
        filters = {"citation": hints["citation_hint"]}

    return {
        "rag_mode": route_cfg["rag_mode"],
        "top_k": route_cfg["top_k"],
        "top_n": route_cfg["top_n"],
        "filters": filters,
    }
