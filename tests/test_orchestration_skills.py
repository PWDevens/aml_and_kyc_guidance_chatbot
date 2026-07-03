"""Unit tests for the orchestration skills (AC-1, AC-3, AC-4, AC-5):
query_framer + intent_classifier (src/rag/orchestration/intents.py),
retrieval_router (src/rag/orchestration/router.py), answer_verifier +
citation_formatter (src/rag/orchestration/verify.py).

change_resolver is intentionally absent — deferred with a stated reason
(D5): it depends on a version-history/valid_from-valid_to ledger that iter-2
did not build (iter-2's provenance ledger records ingest *actions*, not a
queryable before/after timeline). The `change` intent is still classified
and routed (to hybrid_rerank); no bespoke temporal timeline is assembled
this iteration. See .build/iter-3/changes.md.

Run:  python -m pytest tests/test_orchestration_skills.py -q"""
from __future__ import annotations

from dataclasses import replace

from src.rag.config import CONFIG
from src.rag.orchestration.intents import classify_intent, frame_query
from src.rag.orchestration.planner import Budget, plan
from src.rag.orchestration.router import route
from src.rag.orchestration.verify import format_citations, verify_answer

# ---------------------------------------------------------------------------
# query_framer (AC-1)
# ---------------------------------------------------------------------------

def test_frame_query_extracts_citation_hint():
    framed = frame_query("What does 31 CFR 1010.311 require?")
    assert framed["citation_hint"] == "31 CFR 1010.311"


def test_frame_query_normalizes_citation_hint_spacing():
    framed = frame_query("what is 31CFR1010.311 about")
    assert framed["citation_hint"] == "31 CFR 1010.311"


def test_frame_query_extracts_numeric_hint():
    framed = frame_query("What happens above $10,000?")
    assert framed["numeric_hint"] == "$10,000"


def test_frame_query_no_hints_on_plain_definitional_question():
    framed = frame_query("What is a Suspicious Activity Report?")
    assert framed["citation_hint"] is None
    assert framed["numeric_hint"] is None


def test_frame_query_expands_glossary_acronyms():
    framed = frame_query("What is the CIP requirement under BSA?")
    expansions = " ".join(framed["glossary_expansions"])
    assert "Customer Identification Program" in expansions
    assert "Bank Secrecy Act" in expansions


def test_frame_query_strips_leading_chitchat():
    framed = frame_query("Hi, what is a CTR?")
    assert framed["framed_query"].lower().startswith("what is a ctr")


# ---------------------------------------------------------------------------
# intent_classifier (AC-1)
# ---------------------------------------------------------------------------

def test_classify_citation_lookup_when_citation_hint_present():
    framed = frame_query("What does 31 CFR 1010.311 say?")
    result = classify_intent(framed)
    assert result["intent"] == "citation-lookup"


def test_classify_numeric_on_dollar_amount():
    framed = frame_query("What is the dollar threshold for a CTR?")
    result = classify_intent(framed)
    assert result["intent"] == "numeric"


def test_classify_definitional_on_what_is_a():
    framed = frame_query("What is a Suspicious Activity Report?")
    result = classify_intent(framed)
    assert result["intent"] == "definitional"


def test_classify_procedural_on_steps_requirements():
    framed = frame_query("What are the steps to open an account under CIP requirements?")
    result = classify_intent(framed)
    assert result["intent"] == "procedural"


def test_classify_change_on_amended_keyword():
    framed = frame_query("What changed in the latest amended CTR rule?")
    result = classify_intent(framed)
    assert result["intent"] == "change"


def test_classify_default_is_definitional():
    framed = frame_query("Tell me about beneficial ownership")
    result = classify_intent(framed)
    assert result["intent"] == "definitional"


# ---------------------------------------------------------------------------
# retrieval_router (AC-3)
# ---------------------------------------------------------------------------

_REAL_MODES = {"naive", "hybrid", "hybrid_rerank"}
_ALL_INTENTS = ["definitional", "numeric", "procedural", "cross-reference", "change", "citation-lookup"]


def test_router_never_emits_a_mode_outside_real_modes():
    for intent in _ALL_INTENTS:
        result = route(intent, {})
        assert result["rag_mode"] in _REAL_MODES, f"{intent} -> {result['rag_mode']}"


def test_router_cross_reference_falls_back_to_hybrid_rerank():
    result = route("cross-reference", {})
    assert result["rag_mode"] == "hybrid_rerank"


def test_router_change_routes_to_hybrid_rerank():
    result = route("change", {})
    assert result["rag_mode"] == "hybrid_rerank"


def test_router_citation_lookup_yields_naive_and_citation_filter():
    hints = {"citation_hint": "31 CFR 1010.311", "numeric_hint": None}
    result = route("citation-lookup", hints)
    assert result["rag_mode"] == "naive"
    assert result["filters"] == {"citation": "31 CFR 1010.311"}


def test_router_citation_lookup_without_hint_has_no_filter():
    result = route("citation-lookup", {})
    assert result["filters"] == {}


def test_router_unknown_intent_defaults_safely():
    result = route("bogus-intent", {})
    assert result["rag_mode"] in _REAL_MODES


# ---------------------------------------------------------------------------
# answer_verifier (AC-4, AC-5)
# ---------------------------------------------------------------------------

_CONTEXT = (
    "[31 CFR 1010.311] Filing obligations for reports of transactions in currency.\n"
    "Each financial institution other than a casino shall file a report of each "
    "deposit, withdrawal, exchange of currency or other payment or transfer, by, "
    "through, or to such financial institution which involves a transaction in "
    "currency of more than $10,000, except as otherwise provided in this section."
)


def test_verifier_declines_ungrounded_answer():
    """AC-4: an answer whose claims have no lexical support in context ->
    grounded=False, declined=True."""
    answer = "The moon landing occurred in 1969 and Jupiter has 95 known moons."
    result = verify_answer(answer, _CONTEXT, intent="definitional")
    assert result["grounded"] is False
    assert result["declined"] is True


def test_verifier_accepts_grounded_answer():
    """AC-4: a grounded answer -> grounded=True, cache-eligible (not declined)."""
    answer = "Each financial institution must file a report of a transaction in currency of more than $10,000."
    result = verify_answer(answer, _CONTEXT, intent="numeric")
    assert result["grounded"] is True
    assert result["declined"] is False


def test_verifier_f2_completeness_flags_missing_element():
    """AC-5: CIP-minimum-requirements answer omitting date of birth ->
    reported in missing_elements."""
    answer = (
        "The bank must obtain the customer's name, address, and identification "
        "number before opening an account under the customer identification program."
    )
    result = verify_answer(answer, answer, intent="procedural", topic="cip")
    assert "date of birth" in result["missing_elements"]


def test_verifier_f2_completeness_empty_when_answer_is_complete():
    """AC-5: a complete CIP answer -> missing_elements == []."""
    answer = (
        "Under the customer identification program (CIP), a bank must obtain the "
        "customer's name, date of birth, address, and identification number "
        "before opening an account."
    )
    result = verify_answer(answer, answer, intent="procedural", topic="cip")
    assert result["missing_elements"] == []


def test_missing_elements_does_not_by_itself_decline():
    """D10 policy: a correct-but-incomplete answer (grounded, but missing an
    element) is NOT declined — only ungrounded triggers a hard decline."""
    answer = "The bank must obtain the customer's name, address, and identification number."
    context = answer  # fully self-supporting -> grounded
    result = verify_answer(answer, context, intent="procedural", topic="cip")
    assert result["grounded"] is True
    assert result["declined"] is False
    assert result["missing_elements"] != []


# ---------------------------------------------------------------------------
# citation_formatter (AC-1)
# ---------------------------------------------------------------------------

def test_format_citations_dedupes_and_normalizes_shape():
    chunks = [
        {"citation": "31 CFR 1010.311", "heading": "Filing obligations", "url": "u1",
         "source": "ecfr", "as_of": "2026-06-30"},
        {"citation": "31 CFR 1010.311", "heading": "Filing obligations", "url": "u1",
         "source": "ecfr", "as_of": "2026-06-30"},
        {"citation": "31 CFR 1010.312", "heading": "Identification required", "url": "u2",
         "source": "ecfr", "as_of": "2026-06-30"},
    ]
    result = format_citations(chunks)
    assert len(result) == 2
    assert result[0]["citation"] == "31 CFR 1010.311"
    assert result[1]["citation"] == "31 CFR 1010.312"


# ---------------------------------------------------------------------------
# planner (AC-1): plan() ties frame -> classify -> route together; Budget
# tracks ORCHESTRATION_MAX_LLM_CALLS.
# ---------------------------------------------------------------------------

def test_budget_tracks_spend_and_refuses_over_limit():
    budget = Budget(2)
    assert budget.has_budget() is True
    assert budget.spend() is True
    assert budget.spend() is True
    assert budget.has_budget() is False
    assert budget.spend() is False  # over budget -> refuses, never raises


def test_plan_builds_per_request_cfg_without_mutating_global_config():
    original_mode = CONFIG.rag_mode
    original_top_k = CONFIG.retrieval_top_k

    result = plan(CONFIG, "What is a Suspicious Activity Report?")

    assert result["intent"] == "definitional"
    assert result["cfg"].rag_mode == "hybrid_rerank"  # definitional -> hybrid_rerank (D8)
    assert isinstance(result["budget"], Budget)

    # the process-global CONFIG must be untouched (frozen + dataclasses.replace only)
    assert CONFIG.rag_mode == original_mode
    assert CONFIG.retrieval_top_k == original_top_k


def test_plan_citation_lookup_carries_filters():
    result = plan(CONFIG, "What does 31 CFR 1010.311 require?")
    assert result["intent"] == "citation-lookup"
    assert result["filters"] == {"citation": "31 CFR 1010.311"}
    assert result["cfg"].rag_mode == "naive"


def test_plan_per_request_cfg_is_a_distinct_replace_not_the_same_object():
    cfg = replace(CONFIG, retrieval_top_k=99)
    result = plan(cfg, "What is a Suspicious Activity Report?")
    assert result["cfg"] is not cfg
    assert result["cfg"].chroma_path == cfg.chroma_path  # other fields carried over


if __name__ == "__main__":
    test_frame_query_extracts_citation_hint()
    test_frame_query_normalizes_citation_hint_spacing()
    test_frame_query_extracts_numeric_hint()
    test_frame_query_no_hints_on_plain_definitional_question()
    test_frame_query_expands_glossary_acronyms()
    test_frame_query_strips_leading_chitchat()
    test_classify_citation_lookup_when_citation_hint_present()
    test_classify_numeric_on_dollar_amount()
    test_classify_definitional_on_what_is_a()
    test_classify_procedural_on_steps_requirements()
    test_classify_change_on_amended_keyword()
    test_classify_default_is_definitional()
    test_router_never_emits_a_mode_outside_real_modes()
    test_router_cross_reference_falls_back_to_hybrid_rerank()
    test_router_change_routes_to_hybrid_rerank()
    test_router_citation_lookup_yields_naive_and_citation_filter()
    test_router_citation_lookup_without_hint_has_no_filter()
    test_router_unknown_intent_defaults_safely()
    test_verifier_declines_ungrounded_answer()
    test_verifier_accepts_grounded_answer()
    test_verifier_f2_completeness_flags_missing_element()
    test_verifier_f2_completeness_empty_when_answer_is_complete()
    test_missing_elements_does_not_by_itself_decline()
    test_format_citations_dedupes_and_normalizes_shape()
    test_budget_tracks_spend_and_refuses_over_limit()
    test_plan_builds_per_request_cfg_without_mutating_global_config()
    test_plan_citation_lookup_carries_filters()
    test_plan_per_request_cfg_is_a_distinct_replace_not_the_same_object()
    print("orchestration skills ok")
