"""eCFR change watcher — watermark -> /versions since watermark -> changed
sections. Reuses src.rag.indexing.loaders.ecfr.changed_sections (D1); does
NOT fetch full text or upsert — that's pipeline.py."""
from __future__ import annotations

from ...rag.config import RagConfig
from ...rag.indexing.loaders import ecfr
from .. import state

SOURCE = "ecfr"


def poll(cfg: RagConfig) -> list[dict]:
    """For each watched part (cfg.parts), call ecfr.changed_sections(...) to
    get sections amended since the watermark. Return a list of
    {'part','section','issue_date'} for changed sections across all parts.
    Empty if nothing changed."""
    wm = state.get_watermark(cfg, SOURCE)
    since = wm[0] if wm else cfg.etl_ecfr_since

    out: list[dict] = []
    for part in cfg.parts:
        for section_id, issue_date in ecfr.changed_sections(cfg.ecfr_title, cfg.ecfr_chapter, part, since):
            if wm is not None and issue_date <= since:
                continue  # strict-after: skip the boundary re-processing
            out.append({"part": part, "section": section_id, "issue_date": issue_date})
    return out
