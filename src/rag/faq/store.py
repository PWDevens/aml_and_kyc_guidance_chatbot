"""Semantic FAQ store — stdlib sqlite3, Tier-1 (FAQ_CACHE §2). Mirrors
src/rag/cache.py and src/etl/state.py: one _conn() helper, CREATE TABLE IF
NOT EXISTS on first use, parameterized SQL only, no ORM, connection closed in
finally.

One table. Each row is a curated FAQ entry: canonical question + paraphrases,
a pre-verified answer + citations, topic_keys for the D4 cross-check, and the
embeddings for canonical_question + every paraphrase (max-over-paraphrases
matching per D2), stored as one float32 BLOB (n_vectors, 384) plus a count so
the matcher can reshape it back. `stale`/`stale_reason` implement the R5
suppression flag (D14)."""
from __future__ import annotations

import json
import sqlite3

import numpy as np

from ..config import RagConfig

_DIM = 384


def _conn(cfg: RagConfig) -> sqlite3.Connection:
    conn = sqlite3.connect(cfg.faq_db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS faq_entries ("
        "  id                 TEXT PRIMARY KEY,"
        "  canonical_question TEXT NOT NULL,"
        "  paraphrases_json    TEXT NOT NULL,"
        "  answer              TEXT NOT NULL,"
        "  citations_json      TEXT NOT NULL,"
        "  topic_keys_json      TEXT NOT NULL,"
        "  embeddings          BLOB NOT NULL,"
        "  n_vectors            INTEGER NOT NULL,"
        "  verified_by          TEXT,"
        "  as_of                TEXT,"
        "  stale                INTEGER NOT NULL DEFAULT 0,"
        "  stale_reason         TEXT"
        ")"
    )
    return conn


def _row_to_entry(row: tuple) -> dict:
    (id_, canonical_question, paraphrases_json, answer, citations_json,
     topic_keys_json, embeddings_blob, n_vectors, verified_by, as_of,
     stale, stale_reason) = row
    vectors = np.frombuffer(embeddings_blob, dtype=np.float32).reshape(n_vectors, _DIM)
    return {
        "id": id_,
        "canonical_question": canonical_question,
        "paraphrases": json.loads(paraphrases_json),
        "answer": answer,
        "citations": json.loads(citations_json),
        "topic_keys": json.loads(topic_keys_json),
        "embeddings": vectors,
        "verified_by": verified_by,
        "as_of": as_of,
        "stale": bool(stale),
        "stale_reason": stale_reason,
    }


def upsert_entry(cfg: RagConfig, entry: dict, embeddings: np.ndarray) -> None:
    """Insert or replace one FAQ entry. `embeddings` is (n, 384) float32 —
    one row per canonical_question+paraphrase string, in that order (D2)."""
    embeddings = np.asarray(embeddings, dtype=np.float32)
    conn = _conn(cfg)
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO faq_entries "
                "(id, canonical_question, paraphrases_json, answer, citations_json, "
                " topic_keys_json, embeddings, n_vectors, verified_by, as_of, stale, stale_reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry["id"],
                    entry["canonical_question"],
                    json.dumps(entry.get("paraphrases", [])),
                    entry["answer"],
                    json.dumps(entry.get("citations", [])),
                    json.dumps(entry.get("topic_keys", [])),
                    embeddings.tobytes(),
                    embeddings.shape[0],
                    entry.get("verified_by"),
                    entry.get("as_of"),
                    int(entry.get("stale", 0)),
                    entry.get("stale_reason"),
                ),
            )
    finally:
        conn.close()


def iter_entries(cfg: RagConfig) -> list[dict]:
    """All entries (including stale ones — callers apply the stale policy)."""
    conn = _conn(cfg)
    try:
        rows = conn.execute(
            "SELECT id, canonical_question, paraphrases_json, answer, citations_json, "
            "topic_keys_json, embeddings, n_vectors, verified_by, as_of, stale, stale_reason "
            "FROM faq_entries"
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_entry(r) for r in rows]


def flag_stale(cfg: RagConfig, citation: str) -> int:
    """Mark every non-stale entry whose topic_keys or citations reference
    `citation` as stale (R5). Returns the number of entries flagged.
    `citation` may be the full form ("31 CFR 1010.311") or the bare section
    ("1010.311") — matched against both forms since topic_keys conventionally
    stores the bare section (see data/faq_seed.yaml) while ETL passes the
    full citation string."""
    section = citation.split()[-1]  # bare section suffix, e.g. "1010.311"
    conn = _conn(cfg)
    try:
        rows = conn.execute(
            "SELECT id, topic_keys_json, citations_json FROM faq_entries WHERE stale = 0"
        ).fetchall()
        matched = []
        for entry_id, topic_keys_json, citations_json in rows:
            topic_keys = json.loads(topic_keys_json)
            citation_strs = [c.get("citation", "") for c in json.loads(citations_json)]
            if (citation in topic_keys or section in topic_keys
                    or citation in citation_strs or section in citation_strs):
                matched.append(entry_id)
        with conn:
            for entry_id in matched:
                conn.execute(
                    "UPDATE faq_entries SET stale = 1, stale_reason = ? WHERE id = ?",
                    (f"citation {citation} updated by ETL", entry_id),
                )
    finally:
        conn.close()
    return len(matched)


def is_stale(cfg: RagConfig, entry_id: str) -> bool:
    conn = _conn(cfg)
    try:
        row = conn.execute(
            "SELECT stale FROM faq_entries WHERE id = ?", (entry_id,)
        ).fetchone()
    finally:
        conn.close()
    return bool(row[0]) if row else False
