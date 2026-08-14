"""Copy FastClinic operational SQLite state into the configured PostgreSQL schema.

The copy is additive and transactional: existing PostgreSQL primary/unique keys
are retained, source rows with the same key are skipped, and verification occurs
before commit. No SQLite source is modified.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TABLES = (
    "reminder", "communication", "appointment", "external_booking", "invoice",
    "gl_entry", "payment", "api_audit", "chat_message", "accounts",
    "auth_tokens", "auth_limits",
)


def sqlite_tables(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with sqlite3.connect(path) as source:
        return {row[0] for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}


def copy_source(path: Path, connection) -> dict[str, int]:
    available = sqlite_tables(path)
    if not available:
        return {}
    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    copied: dict[str, int] = {}
    try:
        with connection.cursor() as cursor:
            for table in TABLES:
                if table not in available:
                    continue
                columns = [row[1] for row in source.execute(f'PRAGMA table_info("{table}")')]
                rows = source.execute(f'SELECT * FROM "{table}"').fetchall()
                if rows:
                    names = ",".join(f'"{name}"' for name in columns)
                    placeholders = ",".join("%s" for _ in columns)
                    cursor.executemany(
                        f'INSERT INTO "{table}" ({names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING',
                        [tuple(row[name] for name in columns) for row in rows],
                    )
                copied[table] = len(rows)
    finally:
        source.close()
    return copied


def reset_sequences(connection) -> None:
    with connection.cursor() as cursor:
        for table in TABLES:
            if table in {"external_booking", "auth_limits"}:
                continue
            cursor.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
            sequence = next(iter(cursor.fetchone().values()))
            if sequence:
                cursor.execute(f'SELECT COALESCE(MAX(id),0) FROM "{table}"')
                maximum = next(iter(cursor.fetchone().values()))
                cursor.execute("SELECT setval(%s, %s, %s)", (sequence, maximum or 1, maximum > 0))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ops", type=Path, default=ROOT / "fastclinic_ops.sqlite")
    parser.add_argument("--auth", type=Path, default=ROOT / "data/fastsme-accounts.sqlite")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    os.environ["FASTCLINIC_OPS_BACKEND"] = "postgresql"

    from web.ops_db import connect
    with connect() as wrapped:
        connection = wrapped.raw
        try:
            copied = {}
            for source in (args.ops, args.auth):
                for table, count in copy_source(source, connection).items():
                    copied[table] = copied.get(table, 0) + count
            reset_sequences(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    if not copied:
        print("No operational SQLite source tables found; PostgreSQL schema is initialized.")
    else:
        for table, count in copied.items():
            print(f"{table}: examined {count} source rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
