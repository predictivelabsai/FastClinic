"""Read-only SQLite access for the FastClinic cockpit.

The cockpit reads `fastclinic.sqlite` (built by `python -m pms.importer`). All
access goes through `query()` / `query_one()` which return plain dicts so view
code never holds a live cursor.
"""
from __future__ import annotations

import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("FASTCLINIC_DB", os.path.join(ROOT, "fastclinic.sqlite"))

# "Today" reference for due/lapsed maths. The sample export runs to mid-2026;
# override with FASTCLINIC_TODAY=YYYY-MM-DD to pin a reference date for demos.
TODAY = os.getenv("FASTCLINIC_TODAY", "")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def db_exists() -> bool:
    return os.path.exists(DB_PATH)


def query(sql: str, params: tuple = ()) -> list[dict]:
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def scalar(sql: str, params: tuple = ()):
    row = query_one(sql, params)
    if not row:
        return None
    return next(iter(row.values()))


def reference_date() -> str:
    """ISO date used as 'now' for due/overdue/lapsed calculations.

    Defaults to the most recent activity in the DB (so demo data stays 'live'),
    or FASTCLINIC_TODAY if set.
    """
    if TODAY:
        return TODAY
    latest = scalar("SELECT MAX(item_at) FROM item")
    return (latest or "2026-06-10")[:10]
