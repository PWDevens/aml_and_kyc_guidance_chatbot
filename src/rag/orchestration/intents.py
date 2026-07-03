"""query_framer + intent_classifier (D13) — heuristic/rule-first, no LLM call
in the default path (§5 "heuristic fast paths"). The acronym glossary and hint
regexes here are also reused by the FAQ matcher (D4's topic-key cross-check)
and by scripts/seed_faq.py, so query and FAQ-entry hints come from the same
extraction logic.

Dict-dispatch keyword tables (mirrors src/rag/retrieval/factory.py::_MODES
and src/etl/rules.py's classifier style)."""
from __future__ import annotations

import re

# Acronym glossary — start from the intents in the routing table (D13), a
# small, honest set rather than an exhaustive dictionary.
GLOSSARY = {
    "CTR": "Currency Transaction Report",
    "SAR": "Suspicious Activity Report",
    "CDD": "Customer Due Diligence",
    "CIP": "Customer Identification Program",
    "BSA": "Bank Secrecy Act",
    "UBO": "Ultimate Beneficial Owner",
    "MSB": "Money Services Business",
    "EDD": "Enhanced Due Diligence",
    "PEP": "Politically Exposed Person",
    "FBAR": "Report of Foreign Bank and Financial Accounts",
    "AML": "Anti-Money Laundering",
    "KYC": "Know Your Customer",
    "FinCEN": "Financial Crimes Enforcement Network",
    "OFAC": "Office of Foreign Assets Control",
    "SDN": "Specially Designated Nationals",
}

_CITATION_RE = re.compile(r"\b(\d{1,3})\s*CFR\s*(\d+\.\d+)\b", re.IGNORECASE)
_NUMERIC_RE = re.compile(r"\$\s?[\d,]+(?:\.\d+)?|\b\d{1,3}(?:,\d{3})+\b")
_CHITCHAT_RE = re.compile(
    r"^\s*(hi|hello|hey|please|thanks|thank you|so|well|um|ok|okay)[,.\s]+",
    re.IGNORECASE,
)

_NUMERIC_KEYWORDS = ("$", "threshold", "how much", "how many", "minimum dollar")
_DEFINITIONAL_KEYWORDS = ("what is a", "what is an", "what is the", "define", "definition of", "meaning of")
_PROCEDURAL_KEYWORDS = ("steps", "requirements", "how do i", "how does a bank", "minimum", "process for", "procedure")
_CHANGE_KEYWORDS = ("changed", "change", "latest", "new rule", "amended", "recently", "updated")
_CROSSREF_KEYWORDS = ("relates to", "cross-reference", "cross reference", "compare", "difference between", "versus", " vs ")


def _citation_hint(text: str) -> str | None:
    m = _CITATION_RE.search(text)
    if not m:
        return None
    return f"{m.group(1)} CFR {m.group(2)}"


def _numeric_hint(text: str) -> str | None:
    m = _NUMERIC_RE.search(text)
    return m.group(0) if m else None


def _glossary_expansions(text: str) -> list[str]:
    found = []
    for acronym, expansion in GLOSSARY.items():
        if re.search(rf"\b{re.escape(acronym)}\b", text, re.IGNORECASE):
            found.append(f"{acronym} ({expansion})")
    return found


def frame_query(question: str) -> dict:
    """Pure rule/dictionary framing — no LLM call. Strips leading chit-chat,
    expands known acronyms, and extracts citation/numeric hints."""
    stripped = _CHITCHAT_RE.sub("", question).strip()
    framed = stripped or question.strip()
    return {
        "framed_query": framed,
        "citation_hint": _citation_hint(question),
        "numeric_hint": _numeric_hint(question),
        "glossary_expansions": _glossary_expansions(question),
    }


def classify_intent(framed: dict) -> dict:
    """Keyword/heuristic zero-shot classifier (D13). Order matters: citation
    hint is checked first (most specific signal), then numeric, then the
    remaining keyword buckets; default is `definitional`."""
    text = framed["framed_query"].lower()

    if framed.get("citation_hint"):
        return {"intent": "citation-lookup", "confidence": 0.95}
    if any(k in text for k in _CROSSREF_KEYWORDS):
        return {"intent": "cross-reference", "confidence": 0.7}
    if any(k in text for k in _CHANGE_KEYWORDS):
        return {"intent": "change", "confidence": 0.7}
    if "$" in text or any(k in text for k in _NUMERIC_KEYWORDS):
        return {"intent": "numeric", "confidence": 0.8}
    if any(k in text for k in _PROCEDURAL_KEYWORDS):
        return {"intent": "procedural", "confidence": 0.75}
    if any(k in text for k in _DEFINITIONAL_KEYWORDS):
        return {"intent": "definitional", "confidence": 0.8}
    return {"intent": "definitional", "confidence": 0.5}
