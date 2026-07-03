"""answer_verifier (D10-D12) + the F2 mandatory-element completeness check
(D11) + citation_formatter (small — lives here per the spec's "implementer's
call, keep it one small function").

D12 grounding mechanism: lexical-overlap pre-filter, LLM only on borderline
(NOT built — see module note below). Primary path (no LLM): split the
answer into sentences, compute token-set overlap against the retrieved
context; a claim with strong overlap is grounded. If every claim has
near-zero overlap, grounded=False (decline). Gray-band claims (some but weak
overlap) are the documented LLM-escalation slot; this iteration ships the
lexical-only default posture per §5 ("small prompts, heuristic fast paths"),
so gray-band claims are treated as grounded-with-caveat (labeled via
unsupported_claims, not declined) rather than escalated — see changes.md.

D11/F2: a tiny {topic -> required_elements} table, checked only for
procedural/definitional intents whose framed query matches a known topic.
Heuristic/rule check only — no LLM call."""
from __future__ import annotations

import re

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[a-z0-9$%,.]+")

# Debugger-stage fix: a purely function-word claim/context overlap (e.g.
# "before", "the", "to", "with") was inflating the overlap score of
# substantively fabricated claims into the grounded_with_caveat band purely
# on stopword incidence, with zero real semantic support. Excluded only from
# the overlap denominator/numerator so grounding reflects content-word
# support; sentence text itself (and everything else) is untouched. Small,
# fixed, closed-class list -- not a general NLP stopword library dependency.
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "by", "for",
    "with", "as", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "it", "its", "at", "from", "into",
    "than", "then", "which", "who", "whom", "such", "any", "all", "other",
    "each", "if", "not", "no", "so", "up", "out", "about", "before",
    "after", "over", "under", "more", "most", "must", "shall", "will",
    "may", "can", "does", "do", "did", "has", "have", "had",
})

# Overlap bands (token-set Jaccard-ish containment: fraction of claim tokens
# also present in the context). Tuned loosely — exact values aren't load-
# bearing, the grounded/ungrounded/gray-band ordering is what matters.
_GROUNDED_THRESHOLD = 0.5
_GRAY_LOW_THRESHOLD = 0.2

# F2 (carried-forward debt): CIP is the canonical mandatory-element topic
# named by the debt. SAR-timing / CTR-threshold are added because they were
# cheap (one line each) — kept small and honest per D11.
_MANDATORY_ELEMENTS = {
    "cip": {
        "match": ("customer identification program", "cip minimum", "cip requirements", " cip "),
        "elements": {
            "name": ("name",),
            "date of birth": ("date of birth", "birth date", "dob"),
            "address": ("address",),
            "identification number": ("identification number", "taxpayer identification",
                                       "tin", "ssn", "social security", "passport number"),
        },
    },
    "sar_timing": {
        "match": ("suspicious activity report", "sar filing", "file a sar", "when to file a sar"),
        "elements": {
            "30 calendar days": ("30 calendar days", "30-calendar-day", "30 days"),
        },
    },
    "ctr_threshold": {
        "match": ("currency transaction report", "ctr threshold", "ctr filing"),
        "elements": {
            "$10,000": ("$10,000", "10,000", "ten thousand"),
        },
    },
}


def _sentences(answer: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(answer.strip()) if s.strip()]


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _content_tokens(text: str) -> set[str]:
    """Tokens used for the grounding overlap calculation only — stopwords
    excluded so overlap reflects substantive/content-word support rather
    than incidental function-word matches (see _STOPWORDS note above)."""
    return _tokens(text) - _STOPWORDS


def _overlap(claim: str, context_tokens: set[str]) -> float:
    claim_tokens = _content_tokens(claim)
    if not claim_tokens:
        return 0.0
    return len(claim_tokens & context_tokens) / len(claim_tokens)


def _grounding(answer: str, context: str) -> tuple[bool, dict, list[str]]:
    """Returns (grounded, claim_support_map, unsupported_claims)."""
    claims = _sentences(answer)
    if not claims:
        return False, {}, []

    context_tokens = _content_tokens(context)
    claim_support_map: dict = {}
    unsupported: list[str] = []
    any_grounded = False

    for claim in claims:
        overlap = _overlap(claim, context_tokens)
        if overlap >= _GROUNDED_THRESHOLD:
            claim_support_map[claim] = {"overlap": round(overlap, 3), "status": "grounded"}
            any_grounded = True
        elif overlap >= _GRAY_LOW_THRESHOLD:
            # Gray band: budget-gated LLM escalation is the documented
            # headroom (D12); default posture is lexical-only, so treat as
            # grounded-with-caveat (labeled, not declined).
            claim_support_map[claim] = {"overlap": round(overlap, 3), "status": "grounded_with_caveat"}
            unsupported.append(claim)
            any_grounded = True
        else:
            claim_support_map[claim] = {"overlap": round(overlap, 3), "status": "unsupported"}
            unsupported.append(claim)

    return any_grounded, claim_support_map, unsupported


def _missing_elements(answer: str, intent: str, topic: str | None) -> list[str]:
    if intent not in ("procedural", "definitional"):
        return []

    answer_lower = answer.lower()
    topic_lower = (topic or "").lower()

    candidates = []
    for key, spec in _MANDATORY_ELEMENTS.items():
        if topic_lower == key or any(m in topic_lower or m in answer_lower for m in spec["match"]):
            candidates.append(spec)

    missing: list[str] = []
    for spec in candidates:
        for element_name, synonyms in spec["elements"].items():
            if not any(s in answer_lower for s in synonyms):
                missing.append(element_name)
    return missing


def verify_answer(answer: str, context: str, intent: str, topic: str | None = None) -> dict:
    """D10-D12. Returns {"grounded", "claim_support_map", "unsupported_claims",
    "missing_elements", "declined", "note"}.

    Decline policy (D10): only `grounded is False` (nothing in the answer is
    supported by retrieved text) triggers a hard decline. A non-empty
    `missing_elements` does not by itself decline the answer — it annotates
    a correct-but-incomplete answer."""
    grounded, claim_support_map, unsupported_claims = _grounding(answer, context)
    missing_elements = _missing_elements(answer, intent, topic)

    declined = not grounded
    if declined:
        note = ("No claim in the generated answer is supported by the retrieved "
                "regulatory text. Declining to serve this answer — please rephrase "
                "the question or consult the cited sections directly.")
    elif missing_elements:
        note = f"Answer is grounded but appears to omit: {', '.join(missing_elements)}."
    else:
        note = "Answer is grounded in the retrieved context."

    return {
        "grounded": grounded,
        "claim_support_map": claim_support_map,
        "unsupported_claims": unsupported_claims,
        "missing_elements": missing_elements,
        "declined": declined,
        "note": note,
    }


def format_citations(chunks: list[dict]) -> list[dict]:
    """citation_formatter — assemble a de-duplicated, ordered citation list
    from retrieved chunks. Small pure function; chunks already carry the
    citation/heading/url/source/as_of shape produced by
    src/rag/retrieval/factory.py::_format."""
    seen: set[str] = set()
    out: list[dict] = []
    for c in chunks:
        key = c.get("citation", "")
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "citation": c.get("citation", ""),
            "heading": c.get("heading", ""),
            "url": c.get("url", ""),
            "source": c.get("source", ""),
            "as_of": c.get("as_of", ""),
        })
    return out
