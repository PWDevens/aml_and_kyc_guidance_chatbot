"""Exact-match answer cache — stdlib sqlite3, Tier-2 (FAQ_CACHE §1).

Keys on the *normalized* question string only (lower/strip/collapse-whitespace)
so two differently-cased/spaced identical questions hit the same row. This is
NOT the Phase-3 semantic FAQ cache — no embeddings, no similarity, no eviction/
TTL (small local demo; add eviction if the DB grows unbounded in a later phase).
One table, created on first use, no ORM."""
from __future__ import annotations

import json
import re
import sqlite3

from .config import RagConfig

_WS = re.compile(r"\s+")


def _normalize(question: str) -> str:
    return _WS.sub(" ", question.strip().lower())


def _conn(cfg: RagConfig) -> sqlite3.Connection:
    conn = sqlite3.connect(cfg.cache_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS answer_cache ("
        "  q_norm TEXT PRIMARY KEY,"
        "  answer TEXT NOT NULL,"
        "  citations TEXT NOT NULL,"
        "  as_of TEXT"
        ")"
    )
    return conn


def get(cfg: RagConfig, question: str) -> dict | None:
    """Exact-match lookup. Returns {"answer", "citations", "as_of"} or None."""
    conn = _conn(cfg)
    try:
        row = conn.execute(
            "SELECT answer, citations, as_of FROM answer_cache WHERE q_norm = ?",
            (_normalize(question),),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    answer, citations_json, as_of = row
    return {"answer": answer, "citations": json.loads(citations_json), "as_of": as_of}


def put(cfg: RagConfig, question: str, answer: str, citations: list, as_of: str | None) -> None:
    conn = _conn(cfg)
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO answer_cache (q_norm, answer, citations, as_of) "
                "VALUES (?, ?, ?, ?)",
                (_normalize(question), answer, json.dumps(citations), as_of),
            )
    finally:
        conn.close()
