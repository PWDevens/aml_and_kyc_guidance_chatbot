"""FedReg loader — pulls FinCEN Federal Register documents (rules, proposed
rules, notices/advisories) from the public Federal Register API.

One document = one citable, retrievable unit, keyed on its FedReg document
number. This is the single loader for both FinCEN rules/notices and the
Federal-Register-published advisories (ETL doc §1: FinCEN advisories surface
as FedReg `Notice`-type documents) — see the record's `source` field for the
type-derived tag. A distinct FinCEN.gov-advisory scraper is a later phase.
Uses requests (already a dep); abstract-only text — full_text_xml_url
fetch/parsing is deferred, abstracts are sufficient for corpus breadth."""
from __future__ import annotations

import requests

API = "https://www.federalregister.gov/api/v1/documents.json"
UA = {"User-Agent": "aml-kyc-rag-chatbot/0.1 (portfolio project)"}
FIELDS = ["document_number", "type", "title", "abstract", "publication_date",
          "effective_on", "cfr_references", "html_url", "full_text_xml_url"]

_SOURCE_BY_TYPE = {
    "Rule": "fedreg_rule",
    "Proposed Rule": "fedreg_proposed",
    "Notice": "fincen_advisory",
}


def _record_from_doc(doc: dict) -> dict | None:
    """Pure parser: one FedReg API result dict -> one builder record, or None
    to skip (e.g. no retrievable text). No network call — unit-testable."""
    text = (doc.get("abstract") or "").strip()
    if not text:
        return None
    number = doc.get("document_number", "")
    return {
        "id": f"fedreg-{number}",
        "text": text,
        "citation": number,
        "heading": doc.get("title", ""),
        "source": _SOURCE_BY_TYPE.get(doc.get("type", ""), "fedreg"),
        "title": "", "chapter": "", "part": "", "section": "",
        "url": doc.get("html_url", ""),
        "as_of": doc.get("publication_date", ""),
        "fedreg_doc_number": number,
        "publication_date": doc.get("publication_date", ""),
    }


def fetch_documents(agency: str, since: str, max_docs: int) -> list[dict]:
    """Fetch FinCEN FedReg documents (oldest first), paginating up to
    max_docs, and return the RAW API result dicts — type/cfr_references/
    effective_on intact (D5). Callers that only need corpus records should
    shape each via _record_from_doc; the ETL watcher also classifies on the
    raw fields, which _record_from_doc drops."""
    docs: list[dict] = []
    page = 1
    per_page = min(max_docs, 100)
    while len(docs) < max_docs:
        params = {
            "conditions[agencies][]": agency,
            "conditions[publication_date][gte]": since,
            "order": "oldest",
            "per_page": per_page,
            "page": page,
            "fields[]": FIELDS,
        }
        r = requests.get(API, params=params, headers=UA, timeout=60)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        if not results:
            break
        docs.extend(results)
        if not data.get("next_page_url") or len(docs) >= max_docs:
            break
        page += 1
    return docs[:max_docs]


def load_documents(agency: str, since: str, max_docs: int) -> list[dict]:
    """Fetch FinCEN FedReg documents (oldest first), paginating up to
    max_docs, and return one record per document with retrievable text."""
    return [rec for doc in fetch_documents(agency, since, max_docs)
            if (rec := _record_from_doc(doc)) is not None]
