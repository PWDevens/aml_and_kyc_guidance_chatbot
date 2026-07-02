"""ETL pipeline — orchestrates one pass over both sources: watch -> classify
-> extract -> transform -> upsert -> record provenance -> advance watermark
(docs/ETL_AND_TRIGGERS.md §3). Never calls builder.build() (D4) — only
upsert_by_citation against the existing collection.

R8 atomicity: within one source's pass, every batch item is processed and its
provenance row written; the watermark advances only after the WHOLE batch
succeeds. A mid-batch failure records an 'error' row for that item and aborts
the watermark advance for that source — the batch re-processes next run and
upsert-by-citation makes the retry idempotent. A failure in one source must
not touch the other source's watermark."""
from __future__ import annotations

from ..rag.config import RagConfig
from ..rag.indexing.builder import upsert_by_citation
from ..rag.indexing.loaders import ecfr, fedreg
from . import rules, state
from .watchers import ecfr as ecfr_watcher
from .watchers import fedreg as fedreg_watcher


def _run_fedreg(cfg: RagConfig) -> dict:
    events = fedreg_watcher.poll(cfg)
    summary = {"detected": len(events), "upserted": 0, "skipped": 0, "errors": 0}
    if not events:
        return summary

    newest_pub, newest_doc_ref = None, None
    doc = None
    try:
        for doc in events:
            classification = rules.classify_fedreg(doc, set(cfg.parts), rules.TOPIC_TERMS)
            pub = doc.get("publication_date", "")
            doc_number = doc.get("document_number", "")

            if classification is None:
                state.record(cfg, rule_id="-", source=fedreg_watcher.SOURCE,
                              document_ref=doc_number, citation=doc_number,
                              action="skip", chunks_changed=0, as_of=pub, status="success")
                summary["skipped"] += 1
            else:
                rec = fedreg._record_from_doc(doc)
                if rec is None:
                    state.record(cfg, rule_id=classification["rule_id"], source=fedreg_watcher.SOURCE,
                                  document_ref=doc_number, citation=doc_number,
                                  action="skip", chunks_changed=0, as_of=pub, status="success")
                    summary["skipped"] += 1
                else:
                    rec = {**rec, "source": classification["source"]}
                    n = upsert_by_citation(cfg, rec["citation"], [rec])
                    state.record(cfg, rule_id=classification["rule_id"], source=fedreg_watcher.SOURCE,
                                  document_ref=doc_number, citation=rec["citation"],
                                  action="upsert", chunks_changed=n, as_of=pub, status="success")
                    summary["upserted"] += n

                    if classification.get("schedule"):
                        effective_on = classification.get("effective_on")
                        state.record(cfg, rule_id=classification["rule_id"], source=fedreg_watcher.SOURCE,
                                      document_ref=doc_number, citation=rec["citation"],
                                      action="schedule", chunks_changed=0,
                                      as_of=effective_on, status="success")

            # newest processed so far — advances only if the whole batch succeeds
            if newest_pub is None or pub > newest_pub or (pub == newest_pub and doc_number > (newest_doc_ref or "")):
                newest_pub, newest_doc_ref = pub, doc_number
    except Exception:
        failed = doc or {}
        state.record(cfg, rule_id="-", source=fedreg_watcher.SOURCE,
                      document_ref=failed.get("document_number", ""), citation=failed.get("document_number", ""),
                      action="upsert", chunks_changed=0, as_of=failed.get("publication_date"), status="error")
        summary["errors"] += 1
        raise
    else:
        if newest_pub is not None:
            state.set_watermark(cfg, fedreg_watcher.SOURCE, newest_pub, newest_doc_ref)
    return summary


def _run_ecfr(cfg: RagConfig) -> dict:
    events = ecfr_watcher.poll(cfg)
    summary = {"detected": len(events), "upserted": 0, "skipped": 0, "errors": 0}
    if not events:
        return summary

    wm = state.get_watermark(cfg, ecfr_watcher.SOURCE)
    watermark_value = wm[0] if wm else cfg.etl_ecfr_since
    newest_issue_date, newest_section = None, None
    ev = None
    try:
        for ev in events:
            classification = rules.classify_ecfr_section(ev["section"], ev["issue_date"], watermark_value)
            citation = f"{cfg.ecfr_title} CFR {ev['section']}"
            records = ecfr.load_section(cfg.ecfr_title, cfg.ecfr_chapter, ev["part"], ev["section"],
                                         ev["issue_date"], cfg.chunk_char_budget)
            n = upsert_by_citation(cfg, citation, records)
            state.record(cfg, rule_id=classification["rule_id"], source=ecfr_watcher.SOURCE,
                          document_ref=citation, citation=citation,
                          action="upsert", chunks_changed=n, as_of=ev["issue_date"], status="success")
            summary["upserted"] += n

            if newest_issue_date is None or ev["issue_date"] > newest_issue_date:
                newest_issue_date, newest_section = ev["issue_date"], ev["section"]
    except Exception:
        state.record(cfg, rule_id="R4", source=ecfr_watcher.SOURCE,
                      document_ref=(ev or {}).get("section", ""), citation=f"{cfg.ecfr_title} CFR {(ev or {}).get('section', '')}",
                      action="upsert", chunks_changed=0, as_of=(ev or {}).get("issue_date"), status="error")
        summary["errors"] += 1
        raise
    else:
        if newest_issue_date is not None:
            state.set_watermark(cfg, ecfr_watcher.SOURCE, newest_issue_date, newest_section)
    return summary


def run_once(cfg: RagConfig) -> dict:
    """Run one full ETL pass over both sources. Returns a summary dict
    {'fedreg': {...counts...}, 'ecfr': {...counts...}}. A failure in one
    source is caught here so it cannot corrupt the other source's watermark."""
    summary: dict = {}
    try:
        summary["fedreg"] = _run_fedreg(cfg)
    except Exception as e:
        summary["fedreg"] = {"error": str(e)}
    try:
        summary["ecfr"] = _run_ecfr(cfg)
    except Exception as e:
        summary["ecfr"] = {"error": str(e)}
    return summary
