"""FedReg change watcher — watermark -> live query -> changed docs. Reuses
src.rag.indexing.loaders.fedreg for the fetch (D5); watermark bookkeeping and
upsert routing live in pipeline.py, not here."""
from __future__ import annotations

from ...rag.config import RagConfig
from ...rag.indexing.loaders import fedreg
from .. import state

SOURCE = "fedreg"


def poll(cfg: RagConfig) -> list[dict]:
    """Read the 'fedreg' watermark (or cold-start ETL_FEDREG_SINCE), fetch raw
    FinCEN FedReg docs published since it (oldest first), and return the raw
    doc dicts newer than the watermark. Empty list if nothing new. Does NOT
    advance the watermark or upsert — that's pipeline.py."""
    wm = state.get_watermark(cfg, SOURCE)
    since = wm[0] if wm else cfg.etl_fedreg_since
    watermark_doc_ref = wm[1] if wm else None

    docs = fedreg.fetch_documents(cfg.fedreg_agency, since, cfg.fedreg_max_docs)
    if wm is None:
        return docs

    # strict-after the watermark: keep docs published after `since`, or
    # published on `since` but not already at/behind the stored document_ref.
    out = []
    for doc in docs:
        pub = doc.get("publication_date", "")
        if pub > since:
            out.append(doc)
        elif pub == since and watermark_doc_ref is not None:
            if doc.get("document_number", "") > watermark_doc_ref:
                out.append(doc)
    return out
