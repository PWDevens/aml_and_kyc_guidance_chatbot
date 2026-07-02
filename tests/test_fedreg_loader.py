"""One runnable check: the FedReg *parser* (`_record_from_doc`) against a
small inline JSON fixture — no live network call (the live `load_documents`
fetch is exercised only by `python -m scripts.build_index`, same pattern as
`ecfr.load_part`).
Run:  python -m pytest tests/test_fedreg_loader.py -q"""
from src.rag.indexing.loaders import fedreg

_NOTICE_DOC = {
    "document_number": "2020-01240",
    "type": "Notice",
    "title": "Agency Information Collection Activities; Renewal Without Change",
    "abstract": "FinCEN invites comments on the proposed renewal of FinCEN Form 107.",
    "publication_date": "2020-01-27",
    "effective_on": None,
    "cfr_references": [],
    "html_url": "https://www.federalregister.gov/documents/2020/01/27/2020-01240/x",
    "full_text_xml_url": "https://www.federalregister.gov/documents/full_text/xml/2020/01/27/2020-01240.xml",
}

_RULE_DOC = {**_NOTICE_DOC, "document_number": "2020-02526", "type": "Rule"}
_PROPOSED_DOC = {**_NOTICE_DOC, "document_number": "2020-99999", "type": "Proposed Rule"}
_OTHER_DOC = {**_NOTICE_DOC, "document_number": "2020-00001", "type": "Presidential Document"}
_NO_ABSTRACT_DOC = {**_NOTICE_DOC, "abstract": ""}


def test_record_from_doc_maps_type_to_source():
    assert fedreg._record_from_doc(_NOTICE_DOC)["source"] == "fincen_advisory"
    assert fedreg._record_from_doc(_RULE_DOC)["source"] == "fedreg_rule"
    assert fedreg._record_from_doc(_PROPOSED_DOC)["source"] == "fedreg_proposed"
    assert fedreg._record_from_doc(_OTHER_DOC)["source"] == "fedreg"


def test_record_from_doc_schema():
    rec = fedreg._record_from_doc(_NOTICE_DOC)
    assert rec["id"] == "fedreg-2020-01240"
    assert rec["citation"] == "2020-01240"
    assert rec["heading"] == _NOTICE_DOC["title"]
    assert rec["text"] == _NOTICE_DOC["abstract"]
    assert rec["url"] == _NOTICE_DOC["html_url"]
    assert rec["as_of"] == "2020-01-27"
    assert rec["fedreg_doc_number"] == "2020-01240"
    assert rec["publication_date"] == "2020-01-27"
    assert rec["title"] == "" and rec["chapter"] == "" and rec["part"] == "" and rec["section"] == ""


def test_record_from_doc_skips_empty_abstract():
    assert fedreg._record_from_doc(_NO_ABSTRACT_DOC) is None


if __name__ == "__main__":
    test_record_from_doc_maps_type_to_source()
    test_record_from_doc_schema()
    test_record_from_doc_skips_empty_abstract()
    print("fedreg parser ok")
