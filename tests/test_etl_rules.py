"""One runnable check: R1-R4 classification on inline event fixtures — no
network. Includes the D3 chapter:null intersection case (the single most
likely silent bug per the spec's edge cases).
Run:  python -m pytest tests/test_etl_rules.py -q"""
from src.etl import rules

_PARTS = {"1010", "1020"}

_RULE_DOC = {
    "type": "Rule",
    "title": "Some Final Rule",
    "abstract": "Adjusts civil monetary penalties.",
    "effective_on": "2025-02-01",
    "cfr_references": [{"chapter": None, "citation_url": None, "part": "1010", "title": 31}],
}
_PROPOSED_DOC = {**_RULE_DOC, "type": "Proposed Rule"}
_NOTICE_MATCH_DOC = {
    "type": "Notice",
    "title": "FinCEN Advisory on Suspicious Activity",
    "abstract": "This advisory concerns beneficial owner reporting.",
    "cfr_references": [],
}
_NOTICE_NOMATCH_DOC = {
    "type": "Notice",
    "title": "Agency Information Collection Activities",
    "abstract": "Renewal without change of a form.",
    "cfr_references": [],
}
_RULE_UNRELATED_PART_DOC = {
    **_RULE_DOC,
    "cfr_references": [{"chapter": None, "citation_url": None, "part": "9999", "title": 31}],
}
_RULE_CHAPTER_NULL_DOC = {
    **_RULE_DOC,
    "cfr_references": [{"chapter": None, "citation_url": None, "part": "1020", "title": "31"}],
}


def test_touches_watched_cfr_ignores_null_chapter():
    # D3: chapter comes back null in the live API; the intersection test must
    # not check it, or every doc would be wrongly rejected.
    assert rules.touches_watched_cfr(
        [{"chapter": None, "part": "1010", "title": 31}], _PARTS
    )


def test_touches_watched_cfr_title_str_or_int():
    assert rules.touches_watched_cfr([{"chapter": None, "part": "1020", "title": "31"}], _PARTS)
    assert rules.touches_watched_cfr([{"chapter": None, "part": "1020", "title": 31}], _PARTS)


def test_touches_watched_cfr_false_when_part_unwatched():
    assert not rules.touches_watched_cfr([{"chapter": None, "part": "9999", "title": 31}], _PARTS)


def test_r1_final_rule_touching_watched_cfr():
    result = rules.classify_fedreg(_RULE_DOC, _PARTS, rules.TOPIC_TERMS)
    assert result is not None
    assert result["rule_id"] == "R1"
    assert result["action"] == "upsert"
    assert result["source"] == "fedreg_rule"
    assert result["effective_on"] == "2025-02-01"
    assert result["schedule"] is True


def test_r1_chapter_null_does_not_block_match():
    result = rules.classify_fedreg(_RULE_CHAPTER_NULL_DOC, _PARTS, rules.TOPIC_TERMS)
    assert result is not None and result["rule_id"] == "R1"


def test_r2_proposed_rule_touching_watched_cfr():
    result = rules.classify_fedreg(_PROPOSED_DOC, _PARTS, rules.TOPIC_TERMS)
    assert result == {"rule_id": "R2", "action": "upsert", "source": "fedreg_proposed"}


def test_r3_notice_matching_topic_filter():
    result = rules.classify_fedreg(_NOTICE_MATCH_DOC, _PARTS, rules.TOPIC_TERMS)
    assert result == {"rule_id": "R3", "action": "upsert", "source": "fincen_advisory"}


def test_notice_not_matching_topic_filter_is_skipped():
    assert rules.classify_fedreg(_NOTICE_NOMATCH_DOC, _PARTS, rules.TOPIC_TERMS) is None


def test_rule_touching_unrelated_part_is_skipped():
    assert rules.classify_fedreg(_RULE_UNRELATED_PART_DOC, _PARTS, rules.TOPIC_TERMS) is None


def test_r4_ecfr_section_from_versions_query():
    result = rules.classify_ecfr_section("1010.311", "2026-01-05", "2024-12-31")
    assert result == {"rule_id": "R4", "action": "upsert"}


if __name__ == "__main__":
    test_touches_watched_cfr_ignores_null_chapter()
    test_touches_watched_cfr_title_str_or_int()
    test_touches_watched_cfr_false_when_part_unwatched()
    test_r1_final_rule_touching_watched_cfr()
    test_r1_chapter_null_does_not_block_match()
    test_r2_proposed_rule_touching_watched_cfr()
    test_r3_notice_matching_topic_filter()
    test_notice_not_matching_topic_filter_is_skipped()
    test_rule_touching_unrelated_part_is_skipped()
    test_r4_ecfr_section_from_versions_query()
    print("etl rules ok")
