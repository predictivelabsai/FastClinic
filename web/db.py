"""Configurable clinical-database access for the FastClinic cockpit.

The clinical model defaults to PostgreSQL and can use the bundled SQLite
database when explicitly selected for isolated local development and tests.
"""
from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("FASTCLINIC_DB") or os.path.join(ROOT, "fastclinic.sqlite")
DATABASE_URL = os.getenv("DATABASE_URL_PROD") or os.getenv("DATABASE_URL") or ""
DB_SCHEMA = os.getenv("FASTCLINIC_DB_SCHEMA") or "fast_clinic"
DATABASE_BACKEND = (os.getenv("FASTCLINIC_DATABASE_BACKEND") or "postgresql").lower()

# "Today" reference for due/lapsed maths. The sample export runs to mid-2026;
# override with FASTCLINIC_TODAY=YYYY-MM-DD to pin a reference date for demos.
TODAY = os.getenv("FASTCLINIC_TODAY", "")

_POSTGRES_ALIASES = {"postgres", "postgresql", "pg"}
_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def backend_name() -> str:
    """Return the normalized clinical backend name."""
    if DATABASE_BACKEND in _POSTGRES_ALIASES:
        return "postgresql"
    if DATABASE_BACKEND == "sqlite":
        return "sqlite"
    raise RuntimeError(
        "FASTCLINIC_DATABASE_BACKEND must be 'sqlite' or 'postgresql'"
    )


def is_postgres() -> bool:
    return backend_name() == "postgresql"


def database_target() -> str:
    """Return the configured target without logging or otherwise exposing it."""
    if is_postgres():
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL_PROD (or DATABASE_URL) is required for PostgreSQL"
            )
        return DATABASE_URL
    return DB_PATH


def _schema() -> str:
    if not _SCHEMA_RE.fullmatch(DB_SCHEMA):
        raise RuntimeError("FASTCLINIC_DB_SCHEMA is not a valid SQL identifier")
    return DB_SCHEMA


def sql(sql_text: str) -> str:
    """Translate the small portable query subset used by the application."""
    if not is_postgres():
        return sql_text
    translated = sql_text.replace("?", "%s")
    translated = translated.replace(
        "strftime('%Y-%m', consult_at)",
        "TO_CHAR(consult_at::timestamp, 'YYYY-MM')",
    )
    translated = translated.replace(
        "GROUP_CONCAT(d.name, '; ')", "STRING_AGG(d.name, '; ')"
    )
    translated = translated.replace(
        "GROUP_CONCAT(DISTINCT cat)", "STRING_AGG(DISTINCT cat, ',')"
    )
    translated = translated.replace(
        "GROUP_CONCAT(DISTINCT i.category)",
        "STRING_AGG(DISTINCT i.category, ',')",
    )
    return translated


@contextmanager
def connection(*, write: bool = False) -> Iterator[Any]:
    """Open a clinical connection and commit/roll back writes transactionally."""
    if is_postgres():
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as exc:  # pragma: no cover - deployment dependency guard
            raise RuntimeError("PostgreSQL requires psycopg2") from exc
        conn = psycopg2.connect(
            database_target(),
            connect_timeout=10,
            cursor_factory=RealDictCursor,
            options=f"-c search_path={_schema()}",
        )
        conn.autocommit = False
    else:
        conn = sqlite3.connect(DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=15000")
        if write:
            conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        if write:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(conn: Any, sql_text: str, params: tuple | list = ()):
    """Execute portable SQL on either DB-API connection type."""
    if is_postgres():
        cursor = conn.cursor()
        cursor.execute(sql(sql_text), params)
        return cursor
    return conn.execute(sql_text, params)


def db_errors() -> tuple[type[Exception], ...]:
    errors: list[type[Exception]] = [
        sqlite3.IntegrityError,
        sqlite3.OperationalError,
    ]
    try:
        import psycopg2
        errors.extend([psycopg2.IntegrityError, psycopg2.OperationalError])
    except ImportError:
        pass
    return tuple(errors)


def db_exists() -> bool:
    if not is_postgres():
        return os.path.exists(DB_PATH)
    try:
        with connection() as conn:
            row = execute(
                conn,
                "SELECT COUNT(*) AS n FROM information_schema.tables "
                "WHERE table_schema=? AND table_name='subject'",
                (_schema(),),
            ).fetchone()
            return bool(row and row["n"])
    except Exception:
        return False


def query(sql_text: str, params: tuple = ()) -> list[dict]:
    with connection() as conn:
        rows = execute(conn, sql_text, params).fetchall()
        return [dict(row) for row in rows]


def query_one(sql_text: str, params: tuple = ()) -> dict | None:
    rows = query(sql_text, params)
    return rows[0] if rows else None


def scalar(sql_text: str, params: tuple = ()):
    row = query_one(sql_text, params)
    if not row:
        return None
    return next(iter(row.values()))


def reference_date() -> str:
    """ISO date used as 'now' for due/overdue/lapsed calculations."""
    if TODAY:
        return TODAY
    latest = scalar("SELECT MAX(item_at) FROM item")
    return (latest or "2026-06-10")[:10]
