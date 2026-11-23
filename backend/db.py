"""Database connection helpers for tringgg."""
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = os.environ.get("TRINGGG_DB", str(BASE_DIR / "tringgg.db"))


def connect(path=None):
    """Open a connection. Autocommit mode: services.tx() handles transactions."""
    conn = sqlite3.connect(path or DEFAULT_DB, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(conn):
    """Create all tables (safe to run many times)."""
    conn.executescript((BASE_DIR / "schema.sql").read_text(encoding="utf-8"))
