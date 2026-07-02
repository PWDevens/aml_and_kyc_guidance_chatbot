"""One runnable check: src.rag.indexing.loaders.ecfr.changed_sections excludes
`removed: true` /versions entries — no network (requests.get is mocked with an
inline fixture). This is the fix changes.md flags for tester scrutiny: a
removed section (e.g. 31 CFR 1010.655, removed 2020-08-10 per the live check
during this build) has no live text left, so `full/{date}/...&section=...`
404s for it; `changed_sections` must filter it out before the pipeline ever
tries to fetch it (see src/rag/indexing/loaders/ecfr.py::changed_sections).

Run:  python -m pytest tests/test_ecfr_changed_sections.py -q"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.rag.indexing.loaders import ecfr

_VERSIONS_RESPONSE = {
    "content_versions": [
        {"identifier": "1010.311", "issue_date": "2025-01-17", "type": "section", "removed": False},
        # removed: true -> no fetchable text; must be excluded from the result.
        {"identifier": "1010.655", "issue_date": "2020-08-10", "type": "section", "removed": True},
        # a subpart-level entry (not type == "section") must also be excluded,
        # independent of the removed filter.
        {"identifier": "1010", "issue_date": "2025-02-01", "type": "subpart", "removed": False},
        # same identifier appears twice across amendments; keep only the max issue_date.
        {"identifier": "1010.100", "issue_date": "2021-06-01", "type": "section", "removed": False},
        {"identifier": "1010.100", "issue_date": "2023-09-15", "type": "section", "removed": False},
    ]
}


def _mock_response(payload: dict):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


def test_changed_sections_excludes_removed_entries():
    with patch("src.rag.indexing.loaders.ecfr.requests.get", return_value=_mock_response(_VERSIONS_RESPONSE)) as mock_get:
        result = ecfr.changed_sections("31", "X", "1010", "2020-01-01")

    mock_get.assert_called_once()
    identifiers = [ident for ident, _ in result]
    assert "1010.655" not in identifiers, "removed:true section must be filtered out"
    assert "1010.311" in identifiers
    assert "1010.100" in identifiers


def test_changed_sections_excludes_non_section_types():
    with patch("src.rag.indexing.loaders.ecfr.requests.get", return_value=_mock_response(_VERSIONS_RESPONSE)):
        result = ecfr.changed_sections("31", "X", "1010", "2020-01-01")
    identifiers = [ident for ident, _ in result]
    assert "1010" not in identifiers  # type == "subpart", not "section"


def test_changed_sections_dedupes_to_latest_issue_date_per_identifier():
    with patch("src.rag.indexing.loaders.ecfr.requests.get", return_value=_mock_response(_VERSIONS_RESPONSE)):
        result = ecfr.changed_sections("31", "X", "1010", "2020-01-01")
    result_dict = dict(result)
    assert result_dict["1010.100"] == "2023-09-15"  # the later of the two issue_dates


def test_changed_sections_only_removed_entry_yields_empty_result():
    """A /versions response where the ONLY change since the watermark is a
    removed section must yield no changed sections at all (not an error, not
    a phantom entry) — this is exactly the scenario that 404'd during the
    real etl_run pass before the fix (see changes.md's incident note)."""
    only_removed = {"content_versions": [
        {"identifier": "1010.655", "issue_date": "2020-08-10", "type": "section", "removed": True},
    ]}
    with patch("src.rag.indexing.loaders.ecfr.requests.get", return_value=_mock_response(only_removed)):
        result = ecfr.changed_sections("31", "X", "1010", "2020-01-01")
    assert result == []


if __name__ == "__main__":
    test_changed_sections_excludes_removed_entries()
    test_changed_sections_excludes_non_section_types()
    test_changed_sections_dedupes_to_latest_issue_date_per_identifier()
    test_changed_sections_only_removed_entry_yields_empty_result()
    print("ecfr changed_sections ok")
