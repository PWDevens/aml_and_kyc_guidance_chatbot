"""ETL rules engine — R1-R4 (docs/ETL_AND_TRIGGERS.md §2). Pure classification
over already-fetched event dicts; no network here (fetching is the watcher's
job). dict-returning classifiers, dict-dispatch style like
src/rag/retrieval/factory.py's _MODES."""
from __future__ import annotations

WATCHED_TITLE = "31"

# R3 topic filter: a light relevance gate over the FinCEN agency feed, not a
# classifier. A Notice matching none of these terms is skipped. Heuristic,
# not exhaustive.
TOPIC_TERMS = {
    "anti-money laundering", "aml", "bsa", "suspicious activity",
    "currency transaction", "beneficial owner", "customer due diligence",
    "kyc", "fincen",
}


def touches_watched_cfr(cfr_references: list[dict], parts: set[str]) -> bool:
    """True if any ref has title==31 (normalize int/str) and part in parts.
    D3: keys on (title, part); IGNORES chapter (it is null in the live API)."""
    for ref in cfr_references or []:
        if str(ref.get("title")) == WATCHED_TITLE and str(ref.get("part")) in parts:
            return True
    return False


def classify_fedreg(doc: dict, parts: set[str], topic_terms: set[str]) -> dict | None:
    """Map one raw FedReg doc to an action, or None to skip."""
    doc_type = doc.get("type", "")
    cfr_refs = doc.get("cfr_references", [])

    if doc_type == "Rule" and touches_watched_cfr(cfr_refs, parts):
        return {
            "rule_id": "R1",
            "action": "upsert",
            "source": "fedreg_rule",
            "effective_on": doc.get("effective_on"),
            "schedule": True,
        }
    if doc_type == "Proposed Rule" and touches_watched_cfr(cfr_refs, parts):
        return {"rule_id": "R2", "action": "upsert", "source": "fedreg_proposed"}
    if doc_type == "Notice" and _matches_topic_terms(doc, topic_terms):
        return {"rule_id": "R3", "action": "upsert", "source": "fincen_advisory"}
    return None


def _matches_topic_terms(doc: dict, topic_terms: set[str]) -> bool:
    haystack = f"{doc.get('title', '')} {doc.get('abstract', '')}".lower()
    return any(term in haystack for term in topic_terms)


def classify_ecfr_section(section_id: str, issue_date: str, watermark: str | None) -> dict | None:
    """A section returned by the /versions since-watermark query is by
    construction a changed section -> R4 (action='upsert'). The since-
    watermark filter already did the selection; this stamps the rule."""
    return {"rule_id": "R4", "action": "upsert"}


def classify_faq_staleness(citation: str) -> dict:
    """R5 (docs/FAQ_CACHE.md §5, D14): after a successful R1/R4 upsert of
    `citation`, any FAQ entry referencing it must be flagged stale (Tier-1
    must never serve a known-stale cached compliance answer). Pure
    classification stamp — the actual faq.db write + provenance row is
    src/etl/pipeline.py's job (mirrors classify_ecfr_section's split of
    "what rule applies" from "what gets written")."""
    return {"rule_id": "R5", "action": "flag_stale", "citation": citation}


if __name__ == "__main__":
    assert touches_watched_cfr([{"chapter": None, "part": "1010", "title": 31}], {"1010"})
    assert not touches_watched_cfr([{"chapter": None, "part": "9999", "title": 31}], {"1010"})
    print("rules ok")
