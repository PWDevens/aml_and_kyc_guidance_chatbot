"""eCFR loader — pulls 31 CFR Chapter X sections from the public eCFR API.

One section = one citable, retrievable unit (ARCHITECTURE §7 chunking note:
respect section boundaries, don't split mid-clause). For Phase 0 a section IS
the chunk; finer paragraph-aware splitting is a Phase-1 tuning task.
ponytail: stdlib xml.etree, requests (already a dep). No XML framework."""
from __future__ import annotations
import xml.etree.ElementTree as ET
from functools import lru_cache

import requests

API = "https://www.ecfr.gov/api/versioner/v1"
UA = {"User-Agent": "aml-kyc-rag-chatbot/0.1 (portfolio project)"}


@lru_cache(maxsize=8)
def latest_date(title: str) -> str:
    """eCFR's up_to_date_as_of for a title — the only date `full` accepts."""
    r = requests.get(f"{API}/titles.json", headers=UA, timeout=30)
    r.raise_for_status()
    t = next(x for x in r.json()["titles"] if str(x["number"]) == str(title))
    return t["up_to_date_as_of"]


def _text(elem: ET.Element) -> str:
    """Flattened text of a section element, paragraphs joined on newlines."""
    parts = [t.strip() for t in elem.itertext()]
    return "\n".join(p for p in parts if p)


def load_part(title: str, chapter: str, part: str, as_of: str | None = None) -> list[dict]:
    """Return one record per section (eCFR DIV8) in the given part."""
    as_of = as_of or latest_date(title)
    url = f"{API}/full/{as_of}/title-{title}.xml"
    r = requests.get(url, params={"chapter": chapter, "part": part}, headers=UA, timeout=60)
    r.raise_for_status()
    root = ET.fromstring(r.content)

    records: list[dict] = []
    for sec in root.iter("DIV8"):  # DIV8 = section in eCFR XML
        cite = sec.get("N")        # e.g. "1010.311"
        if not cite:
            continue
        head_el = sec.find("HEAD")
        heading = (head_el.text or "").strip() if head_el is not None else ""
        body = _text(sec)
        if not body:
            continue
        records.append({
            "id": f"ecfr-{title}-{cite}",
            "text": body,
            "citation": f"{title} CFR {cite}",
            "heading": heading,
            "source": "ecfr",
            "title": title,
            "chapter": chapter,
            "part": part,
            "section": cite,
            "url": f"https://www.ecfr.gov/current/title-{title}/chapter-{chapter}/part-{part}/section-{cite}",
            "as_of": as_of,
        })
    return records


def load_parts(title: str, chapter: str, parts: list[str], as_of: str | None = None) -> list[dict]:
    out: list[dict] = []
    for p in parts:
        out.extend(load_part(title, chapter, p, as_of))
    return out
