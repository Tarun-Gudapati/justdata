"""Persistent recent / frequent questions (local SQLite).

Separate from demo.db so wiping sample data never clears the list.
Swap this module's backend later when moving to the live DB.
"""
import sqlite3
from pathlib import Path

_DB = Path("recents.db")


def _connect():
    conn = sqlite3.connect(_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recent_queries (
            id           INTEGER PRIMARY KEY,
            question     TEXT NOT NULL UNIQUE,
            use_count    INTEGER NOT NULL DEFAULT 1,
            last_used_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    conn.close()


def record(question: str) -> None:
    """Upsert a question: bump count + refresh last_used_at."""
    q = (question or "").strip()
    if not q:
        return
    init()
    conn = _connect()
    conn.execute(
        """
        INSERT INTO recent_queries (question, use_count, last_used_at)
        VALUES (?, 1, datetime('now'))
        ON CONFLICT(question) DO UPDATE SET
            use_count = use_count + 1,
            last_used_at = datetime('now')
        """,
        (q,),
    )
    conn.commit()
    conn.close()


def list_recent(limit: int = 20):
    """Most recently used questions first."""
    init()
    conn = _connect()
    rows = conn.execute(
        """
        SELECT id, question, use_count, last_used_at
        FROM recent_queries
        ORDER BY last_used_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear() -> None:
    init()
    conn = _connect()
    conn.execute("DELETE FROM recent_queries")
    conn.commit()
    conn.close()
