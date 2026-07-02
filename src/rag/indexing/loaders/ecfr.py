"""eCFR loader — pulls 31 CFR Chapter X sections from the public eCFR API.

One section = one citable, retrievable unit (ARCHITECTURE §7 chunking note:
respect section boundaries, don't split mid-clause). Sections under the char
budget stay a single chunk; longer sections are split on paragraph boundaries
(`_split_section`) into several chunks that keep the same citation/metadata,
so citations still resolve to the whole section (Phase-1 tuning).
ponytail: stdlib xml.etree, requests (already a dep). No XML framework."""
from __future__ import annotations
import xml.etree.ElementTree as ET
from functools import lru_cache

import requests

API = "https://www.ecfr.gov/api/versioner/v1"
UA = {"User-Agent": "aml-kyc-rag-chatbot/0.1 (portfolio project)"}
DEFAULT_CHUNK_CHAR_BUDGET = 1500


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


def _split_section(text: str, budget: int) -> list[str]:
    """Split section text on paragraph boundaries into chunks <= budget chars.

    Returns [text] unchanged when it already fits. Never splits inside a
    paragraph — paragraphs are packed greedily so a chunk may run over budget
    only when a single paragraph itself exceeds it (kept whole, uncut)."""
    if len(text) <= budget:
        return [text]
    paras = text.split("\n")
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for p in paras:
        added = len(p) + (1 if cur else 0)  # +1 for the joining newline
        if cur and cur_len + added > budget:
            chunks.append("\n".join(cur))
            cur, cur_len = [p], len(p)
        else:
            cur.append(p)
            cur_len += added
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def load_part(title: str, chapter: str, part: str, as_of: str | None = None,
              chunk_char_budget: int = DEFAULT_CHUNK_CHAR_BUDGET) -> list[dict]:
    """Return one record per citable chunk (eCFR DIV8 section, split if long)."""
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
        base = {
            "citation": f"{title} CFR {cite}",
            "heading": heading,
            "source": "ecfr",
            "title": title,
            "chapter": chapter,
            "part": part,
            "section": cite,
            "url": f"https://www.ecfr.gov/current/title-{title}/chapter-{chapter}/part-{part}/section-{cite}",
            "as_of": as_of,
        }
        pieces = _split_section(body, chunk_char_budget)
        if len(pieces) == 1:
            records.append({"id": f"ecfr-{title}-{cite}", "text": pieces[0], **base})
        else:
            for i, piece in enumerate(pieces):
                records.append({"id": f"ecfr-{title}-{cite}-{i}", "text": piece, **base})
    return records


def load_parts(title: str, chapter: str, parts: list[str], as_of: str | None = None,
                chunk_char_budget: int = DEFAULT_CHUNK_CHAR_BUDGET) -> list[dict]:
    out: list[dict] = []
    for p in parts:
        out.extend(load_part(title, chapter, p, as_of, chunk_char_budget))
    return out


def changed_sections(title: str, chapter: str, part: str, since: str) -> list[tuple[str, str]]:
    """Sections amended since `since`, via the /versions endpoint (per-section
    change signal — no structure-tree diffing). Returns [(identifier, issue_date),
    ...], deduped to the latest issue_date per identifier.
    Skips entries with removed=True: a removed section has no live text left
    to fetch (full/{date}/...&section=... 404s for it) — verified live for
    1010.655 (removed 2020-08-10). Deletion-on-removal is a different, not-yet-
    specified event; this loader only surfaces re-embeddable content changes."""
    url = f"{API}/versions/title-{title}.json"
    params = {"chapter": chapter, "part": part, "issue_date[gte]": since}
    r = requests.get(url, params=params, headers=UA, timeout=30)
    r.raise_for_status()
    latest: dict[str, str] = {}
    for v in r.json().get("content_versions", []):
        if v.get("type") != "section" or v.get("removed"):
            continue
        ident = v.get("identifier")
        issue_date = v.get("issue_date")
        if not ident or not issue_date:
            continue
        if ident not in latest or issue_date > latest[ident]:
            latest[ident] = issue_date
    return sorted(latest.items())


def load_section(title: str, chapter: str, part: str, section: str, as_of: str,
                  chunk_char_budget: int = DEFAULT_CHUNK_CHAR_BUDGET) -> list[dict]:
    """Fetch one section's full XML, scoped via `section=`, and return its
    record(s) — same schema/splitting as load_part, just one DIV8."""
    url = f"{API}/full/{as_of}/title-{title}.xml"
    r = requests.get(url, params={"chapter": chapter, "part": part, "section": section},
                      headers=UA, timeout=60)
    r.raise_for_status()
    root = ET.fromstring(r.content)

    records: list[dict] = []
    for sec in root.iter("DIV8"):
        cite = sec.get("N")
        if not cite:
            continue
        head_el = sec.find("HEAD")
        heading = (head_el.text or "").strip() if head_el is not None else ""
        body = _text(sec)
        if not body:
            continue
        base = {
            "citation": f"{title} CFR {cite}",
            "heading": heading,
            "source": "ecfr",
            "title": title,
            "chapter": chapter,
            "part": part,
            "section": cite,
            "url": f"https://www.ecfr.gov/current/title-{title}/chapter-{chapter}/part-{part}/section-{cite}",
            "as_of": as_of,
        }
        pieces = _split_section(body, chunk_char_budget)
        if len(pieces) == 1:
            records.append({"id": f"ecfr-{title}-{cite}", "text": pieces[0], **base})
        else:
            for i, piece in enumerate(pieces):
                records.append({"id": f"ecfr-{title}-{cite}-{i}", "text": piece, **base})
    return records
