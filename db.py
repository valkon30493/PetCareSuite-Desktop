# db.py
from __future__ import annotations
import os
import sqlite3
import contextlib
from typing import Iterable, Mapping, Any, Iterator
from backup import DB_PATH  # the one source of truth for the file location

# Allow runtime override for QA/testing (optional)
_DB_PATH = os.getenv("PETWELLNESS_DB") or str(DB_PATH)

# --- PRAGMA configuration applied everywhere ---
def _configure(conn: sqlite3.Connection) -> sqlite3.Connection:
    # autocommit-style behavior to match your current pattern
    conn.isolation_level = None
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=8000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def connect(*, timeout: float = 10.0) -> sqlite3.Connection:
    """Open a connection to the single, canonical DB with consistent PRAGMAs."""
    return _configure(sqlite3.connect(_DB_PATH, timeout=timeout))

@contextlib.contextmanager
def open_conn(*, timeout: float = 10.0) -> Iterator[sqlite3.Connection]:
    """Context-managed connection helper."""
    conn = connect(timeout=timeout)
    try:
        yield conn
    finally:
        conn.close()

# --- Small convenience helpers (optional) ---
def execute(sql: str, params: Iterable[Any] | Mapping[str, Any] = ()):
    with open_conn() as con:
        cur = con.execute(sql, params if isinstance(params, Iterable) else ())
        return cur.fetchall()

def scalar(sql: str, params: Iterable[Any] | Mapping[str, Any] = ()):
    with open_conn() as con:
        cur = con.execute(sql, params if isinstance(params, Iterable) else ())
        row = cur.fetchone()
        return None if row is None else row[0]
