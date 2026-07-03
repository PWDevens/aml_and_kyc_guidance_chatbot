"""Tier-1 semantic FAQ matcher (FAQ_CACHE §3). max-over-paraphrases cosine
matching (D2) + FAQ_SIM_THRESHOLD (D3) + topic-key cross-check (D4).

D2: embeds every stored canonical_question + paraphrases string per entry and
scores a query as max(cosine(query, e) for e in entry_vectors) — matching
against the canonical question alone was measured to NOT separate on-topic
paraphrases from off-topic look-alikes (bands overlap), so canonical-only
matching is prohibited.

D4: the topic-key cross-check is the real false-positive guard, not the
threshold alone. If frame_query extracted a citation_hint or numeric_hint,
at least one of those hints must be consistent with the matched entry's
topic_keys, or the candidate is treated as a miss.

Defensive posture mirrors src/rag/llm/models.py::available(): faq.db absent
or the embedding model unavailable/offline both degrade to a miss (log +
return None), never a crash — the app must still answer via retrieval."""
from __future__ import annotations

import logging

import numpy as np

from ..config import RagConfig
from . import store
from .embed import embed_query

log = logging.getLogger(__name__)

# Below the shipped threshold but close enough to be worth a debug log line
# for future threshold tuning (FAQ_CACHE §3 "gray-band near-misses").
_GRAY_BAND_MARGIN = 0.05


class FaqHit(dict):
    """Small dict-shaped hit — {"id", "answer", "citations", "as_of", "score"}."""


def _max_cosine(query_vec: np.ndarray, entry_vecs: np.ndarray) -> float:
    # both sides are L2-normalized (D1), so cosine == dot product.
    return float(np.max(entry_vecs @ query_vec))


def _hint_consistent_with_topic_keys(hints: dict, topic_keys: list[str]) -> bool:
    """D4: a citation_hint or numeric_hint must appear in (or be consistent
    with) topic_keys, else the candidate is a mismatch. If neither hint is
    present, the cross-check cannot fire — cosine threshold alone decides."""
    citation_hint = hints.get("citation_hint")
    numeric_hint = hints.get("numeric_hint")
    if not citation_hint and not numeric_hint:
        return True

    keys_blob = " ".join(topic_keys)
    ok = False
    if citation_hint:
        # topic_keys may store the bare section ("1010.311") or the full
        # citation ("31 CFR 1010.311") — accept either form.
        section = citation_hint.split()[-1]
        ok = ok or citation_hint in keys_blob or section in keys_blob
    if numeric_hint:
        digits = numeric_hint.replace("$", "").replace(",", "").strip()
        ok = ok or digits in keys_blob.replace(",", "") or numeric_hint in keys_blob
    # If only one of the two hints was present, that hint alone decides. If
    # both were present, either one being consistent is enough (a query can
    # legitimately carry a citation hint AND an unrelated numeric aside).
    return ok


def match(cfg: RagConfig, framed_query: str, hints: dict) -> "FaqHit | None":
    try:
        entries = store.iter_entries(cfg)
    except Exception:
        log.info("faq matcher: faq.db unavailable, falling through to Tier-2/retrieval")
        return None
    if not entries:
        return None

    try:
        query_vec = embed_query(framed_query, cfg.embed_model)
    except Exception:
        log.info("faq matcher: embedding unavailable, falling through to Tier-2/retrieval")
        return None

    best = None  # (score, entry)
    for entry in entries:
        if entry["stale"] and cfg.faq_stale_policy == "suppress":
            continue
        if entry["stale"] and cfg.faq_stale_policy != "suppress":
            # D14: only `suppress` is built this iteration; any other value
            # is treated as suppress (tech-debt note in changes.md).
            continue
        score = _max_cosine(query_vec, entry["embeddings"])
        if best is None or score > best[0]:
            best = (score, entry)

    if best is None:
        return None
    score, entry = best

    if score < cfg.faq_sim_threshold:
        if score >= cfg.faq_sim_threshold - _GRAY_BAND_MARGIN:
            try:
                log.info("faq matcher: gray-band near-miss id=%s score=%.3f threshold=%.3f",
                          entry["id"], score, cfg.faq_sim_threshold)
            except Exception:
                pass  # best-effort logging only
        return None

    if cfg.faq_topic_crosscheck and not _hint_consistent_with_topic_keys(hints, entry["topic_keys"]):
        return None

    return FaqHit(
        id=entry["id"],
        answer=entry["answer"],
        citations=entry["citations"],
        as_of=entry["as_of"],
        score=score,
    )
