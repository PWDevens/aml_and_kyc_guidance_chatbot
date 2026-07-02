"""ETL state — watermarks + provenance ledger, stdlib sqlite3 (mirrors
src/rag/cache.py: one _conn() helper, CREATE TABLE IF NOT EXISTS on first use,
no ORM, no migration framework).

Two tables (docs/ETL_AND_TRIGGERS.md §4):
- watermarks: one row per source ('fedreg' | 'ecfr'), the last-processed
  position so the next poll only asks for what's new.
- provenance: one row per ingest action, answering *why* (rule_id +
  document_ref) and *when* (timestamp, as_of) a chunk is in the corpus."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ..rag.config import RagConfig


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn(cfg: RagConfig) -> sqlite3.Connection:
    conn = sqlite3.connect(cfg.etl_state_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS watermarks ("
        "  source        TEXT PRIMARY KEY,"
        "  value         TEXT NOT NULL,"
        "  document_ref  TEXT,"
        "  updated_at    TEXT NOT NULL"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS provenance ("
        "  id              INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  timestamp       TEXT NOT NULL,"
        "  rule_id         TEXT NOT NULL,"
        "  source          TEXT NOT NULL,"
        "  document_ref    TEXT NOT NULL,"
        "  citation        TEXT NOT NULL,"
        "  action          TEXT NOT NULL,"
        "  chunks_changed  INTEGER NOT NULL,"
        "  as_of           TEXT,"
        "  status          TEXT NOT NULL"
        ")"
    )
    return conn


def get_watermark(cfg: RagConfig, source: str) -> tuple[str, str | None] | None:
    """Return (value, document_ref) or None if no watermark yet."""
    conn = _conn(cfg)
    try:
        row = conn.execute(
            "SELECT value, document_ref FROM watermarks WHERE source = ?", (source,)
        ).fetchone()
    finally:
        conn.close()
    return None if row is None else (row[0], row[1])


def set_watermark(cfg: RagConfig, source: str, value: str, document_ref: str | None) -> None:
    """INSERT OR REPLACE the watermark for source; stamps updated_at."""
    conn = _conn(cfg)
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO watermarks (source, value, document_ref, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (source, value, document_ref, _now()),
            )
    finally:
        conn.close()


def record(cfg: RagConfig, *, rule_id: str, source: str, document_ref: str, citation: str,
           action: str, chunks_changed: int, as_of: str | None, status: str) -> None:
    """Append one provenance row (stamps timestamp)."""
    conn = _conn(cfg)
    try:
        with conn:
            conn.execute(
                "INSERT INTO provenance "
                "(timestamp, rule_id, source, document_ref, citation, action, "
                " chunks_changed, as_of, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (_now(), rule_id, source, document_ref, citation, action,
                 chunks_changed, as_of, status),
            )
    finally:
        conn.close()


def last_successful_run(cfg: RagConfig) -> str | None:
    """Max(timestamp) over provenance WHERE status='success', or None."""
    conn = _conn(cfg)
    try:
        row = conn.execute(
            "SELECT MAX(timestamp) FROM provenance WHERE status = 'success'"
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def counts_by_source(records_metadatas: list[dict]) -> dict[str, int]:
    """Tally 'source' over a metadata list (used by /corpus_status)."""
    counts: dict[str, int] = {}
    for m in records_metadatas:
        src = m.get("source", "")
        counts[src] = counts.get(src, 0) + 1
    return counts
