"""Behavior tests for the Iteration-4 backend surface (Cognitus UI restyle):

1. The three new static routes added to src/app/api.py (`/cognitus.css`,
   `/cognitus.js`, `/app.js`) — added by the orchestrator to replace the
   senior-dev's inlined-asset workaround for `Flask(__name__,
   static_folder=None)`. Verifies 200 + non-empty body + a reasonable
   content-type actually sent by `send_from_directory` (not assumed), and
   that a path-traversal attempt is rejected (AC: spec "Files to modify" /
   api.py section; changes.md "RESOLVED by the orchestrator").

2. The `source_tier` field (D4): present as "faq" on the FAQ fast-path's
   `citations` event (already covered by
   test_chat_stream_orchestration.py::test_faq_tier1_hit_skips_retrieval_and_generation_entirely
   — not duplicated here), and genuinely ABSENT (no key at all, not even
   null) from both `_gen_iter2_path`'s and `_gen_orchestrated_path`'s
   `citations` events, preserving the AC-2/D9 byte-identical-collapse spirit
   from iteration 3.

3. A lightweight structural check on index.html: exactly one <h1>, <header>,
   <main>, <footer>, and one <aside> (AC-1).

Run:  python -m pytest tests/test_iter4_static_and_source_tier.py -q
"""
from __future__ import annotations

import json
import re
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from src.app import api
from src.rag.config import CONFIG

STATIC_DIR = Path(__file__).resolve().parent.parent / "src" / "app" / "static"


def _events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = block.splitlines()
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        out.append((event, data))
    return out


def _tmp_cfg(d: str, **kw):
    return replace(
        CONFIG,
        cache_path=str(Path(d) / "cache.db"),
        faq_db_path=str(Path(d) / "faq.db"),
        **kw,
    )


# ---------------------------------------------------------------------------
# New static routes: /cognitus.css, /cognitus.js, /app.js
# ---------------------------------------------------------------------------

def test_cognitus_css_served_with_200_and_css_content_type():
    client = api.app.test_client()
    r = client.get("/cognitus.css")
    assert r.status_code == 200
    assert len(r.get_data()) > 0
    # Werkzeug's send_from_directory infers this from the .css extension;
    # verify the actual value rather than assuming a fixed literal.
    assert "css" in r.headers.get("Content-Type", "").lower()


def test_cognitus_js_served_with_200_and_js_content_type():
    client = api.app.test_client()
    r = client.get("/cognitus.js")
    assert r.status_code == 200
    assert len(r.get_data()) > 0
    ctype = r.headers.get("Content-Type", "").lower()
    assert "javascript" in ctype or "ecmascript" in ctype


def test_app_js_served_with_200_and_js_content_type():
    client = api.app.test_client()
    r = client.get("/app.js")
    assert r.status_code == 200
    assert len(r.get_data()) > 0
    ctype = r.headers.get("Content-Type", "").lower()
    assert "javascript" in ctype or "ecmascript" in ctype


def test_static_routes_serve_the_real_files_on_disk():
    """Confirms the routes actually serve src/app/static/*, not some other
    copy — bodies must match the files on disk byte-for-byte."""
    client = api.app.test_client()
    for route, filename in (
        ("/cognitus.css", "cognitus.css"),
        ("/cognitus.js", "cognitus.js"),
        ("/app.js", "app.js"),
    ):
        r = client.get(route)
        on_disk = (STATIC_DIR / filename).read_bytes()
        assert r.get_data() == on_disk


# ---------------------------------------------------------------------------
# Path traversal protection on the new routes
# ---------------------------------------------------------------------------

def test_cognitus_css_route_rejects_path_traversal():
    client = api.app.test_client()
    for attempt in ("/../requirements.txt", "/..%2Frequirements.txt", "/%2e%2e/requirements.txt"):
        r = client.get("/cognitus.css" + attempt)
        assert r.status_code in (400, 404), f"{attempt!r} -> {r.status_code}, expected 400/404"


def test_cognitus_js_route_rejects_path_traversal():
    client = api.app.test_client()
    for attempt in ("/../requirements.txt", "/..%2Frequirements.txt"):
        r = client.get("/cognitus.js" + attempt)
        assert r.status_code in (400, 404), f"{attempt!r} -> {r.status_code}, expected 400/404"


def test_app_js_route_rejects_path_traversal():
    client = api.app.test_client()
    for attempt in ("/../requirements.txt", "/..%2Frequirements.txt"):
        r = client.get("/app.js" + attempt)
        assert r.status_code in (400, 404), f"{attempt!r} -> {r.status_code}, expected 400/404"


def test_top_level_traversal_against_bare_route_prefix_does_not_leak_requirements_txt():
    """A blunter traversal attempt straight off the site root must not expose
    files outside src/app/static (defense-in-depth check, mirrors the
    existing GET / route's own send_from_directory protection)."""
    client = api.app.test_client()
    r = client.get("/../requirements.txt")
    assert r.status_code in (400, 404)
    r2 = client.get("/..%2Frequirements.txt")
    assert r2.status_code in (400, 404)


# ---------------------------------------------------------------------------
# source_tier: absent (not even null) on the two non-FAQ citations events
# ---------------------------------------------------------------------------

def test_iter2_path_citations_event_has_no_source_tier_key():
    """_gen_iter2_path must remain byte-identical apart from the FAQ branch
    (D9/AC-2 spirit extended to D4): its citations event dict must not gain a
    source_tier key at all, not even source_tier=None."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=False, faq_cache=False)
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.models.available", return_value=True), \
             patch("src.app.api.models.stream", return_value=iter(["It is ", "$10,000."])):
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": "What is the CTR dollar threshold?"})
            events = _events(r.get_data(as_text=True))
            cites = next(d_ for e, d_ in events if e == "citations")
            assert "source_tier" not in cites


def test_iter2_path_cache_hit_citations_event_has_no_source_tier_key():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=False, faq_cache=False)
        from src.rag import cache
        question = "What is the CTR dollar threshold?"
        cache.put(cfg, question, "Cached answer.", [{"citation": "31 CFR 1010.311"}], "2026-01-01")

        with patch("src.app.api.CONFIG", cfg):
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": question})
            events = _events(r.get_data(as_text=True))
            cites = next(d_ for e, d_ in events if e == "citations")
            assert "source_tier" not in cites


def test_orchestrated_path_citations_event_has_no_source_tier_key():
    """_gen_orchestrated_path's citations tail (both the generated-answer
    branch and the no-citations early-return branch) must also never carry
    source_tier — only the Tier-1 FAQ branch in chat_stream.gen() may."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=True, faq_cache=False, verify_answers=False)
        context = ("[31 CFR 1010.311] Filing obligations\nEach financial institution shall "
                   "file a report of a transaction in currency of more than $10,000.")
        citations = [{"citation": "31 CFR 1010.311", "heading": "Filing obligations",
                      "url": "u", "source": "ecfr", "as_of": "2026-06-30"}]
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.models.available", return_value=True), \
             patch("src.app.api.models.stream",
                   return_value=iter(["Each financial institution shall file."])), \
             patch("src.app.api.retrieve", return_value=(context, citations)):
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": "What is the CTR dollar threshold?"})
            events = _events(r.get_data(as_text=True))
            cites = next(d_ for e, d_ in events if e == "citations")
            assert "source_tier" not in cites


def test_orchestrated_path_no_citations_branch_has_no_source_tier_key():
    with tempfile.TemporaryDirectory() as d:
        cfg = _tmp_cfg(d, orchestration=True, faq_cache=False, verify_answers=False)
        with patch("src.app.api.CONFIG", cfg), \
             patch("src.app.api.retrieve", return_value=("", [])):
            client = api.app.test_client()
            r = client.post("/chat_stream", json={"question": "Some zero-hit question"})
            events = _events(r.get_data(as_text=True))
            cites = next(d_ for e, d_ in events if e == "citations")
            assert "source_tier" not in cites


# ---------------------------------------------------------------------------
# AC-1: HTML structural landmarks (exactly one each)
# ---------------------------------------------------------------------------

def _tag_open_count(html: str, tag: str) -> int:
    # Matches "<tag" followed by whitespace or '>' so e.g. <header> is not
    # miscounted by a hypothetical <headerx>; closing tags are ignored.
    return len(re.findall(r"<" + re.escape(tag) + r"(\s|>)", html, flags=re.IGNORECASE))


def test_index_html_has_exactly_one_h1():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert _tag_open_count(html, "h1") == 1


def test_index_html_has_exactly_one_header_main_footer():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert _tag_open_count(html, "header") == 1
    assert _tag_open_count(html, "main") == 1
    assert _tag_open_count(html, "footer") == 1


def test_index_html_has_exactly_one_aside_for_citation_panel():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert _tag_open_count(html, "aside") == 1
    # It should be the citation panel per spec AC-1/AC-7.
    aside_match = re.search(r"<aside[^>]*>", html, flags=re.IGNORECASE)
    assert aside_match is not None
    assert "citation" in aside_match.group(0).lower()


def test_index_html_references_cognitus_assets_via_link_and_script_src():
    """Confirms the orchestrator's fix is actually wired up in the markup:
    real <link>/<script src> tags pointing at the new routes, not inlined
    <style>/<script> blocks (changes.md 'Deliberate simplifications' #1)."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<link[^>]+href=["\']/cognitus\.css["\']', html)
    assert re.search(r'<script[^>]+src=["\']/cognitus\.js["\']', html)
    assert re.search(r'<script[^>]+src=["\']/app\.js["\']', html)
    # No leftover inlined blocks duplicating the external files.
    assert "<style>" not in html
