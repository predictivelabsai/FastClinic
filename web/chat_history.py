"""Bounded, user-scoped conversation history for the FastClinic assistant.

Chat state is operational data, so it lives beside reminders and appointments in
``FASTCLINIC_OPS_DB`` rather than in the rebuildable PMS replica.  The owner is
stored as a one-way hash, threads are opaque IDs, and old/oversized context is
pruned before it is replayed to the model.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHAT_DB_PATH = Path(os.getenv("FASTCLINIC_OPS_DB") or ROOT / "fastclinic_ops.sqlite")
_THREAD_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,128}$")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_hash TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    language TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_thread
    ON chat_message (owner_hash, thread_id, id);
CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_message (created_at);
"""


def _connect() -> sqlite3.Connection:
    CHAT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(CHAT_DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.executescript(_SCHEMA)
    return connection


def _owner_hash(owner_id: str | None) -> str:
    normalized = (owner_id or "local").strip().lower()[:320]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _thread_id(thread_id: str) -> str:
    value = (thread_id or "").strip()
    if not _THREAD_RE.fullmatch(value):
        raise ValueError("invalid chat thread id")
    return value


def _int_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


def history(owner_id: str | None, thread_id: str) -> list[dict[str, str]]:
    """Return a bounded chronological user/assistant history for model replay."""
    owner, thread = _owner_hash(owner_id), _thread_id(thread_id)
    limit = _int_setting("FASTCLINIC_CHAT_HISTORY_MESSAGES", 20, 2, 100)
    max_chars = _int_setting("FASTCLINIC_CHAT_HISTORY_CHARS", 24000, 1000, 100000)
    with _connect() as connection:
        rows = connection.execute(
            """SELECT role,content FROM chat_message
               WHERE owner_hash=? AND thread_id=? ORDER BY id DESC LIMIT ?""",
            (owner, thread, limit),
        ).fetchall()
    messages = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
    while messages and sum(len(item["content"]) for item in messages) > max_chars:
        messages.pop(0)
    # Never begin replay with an orphaned assistant turn after count/size pruning.
    if messages and messages[0]["role"] == "assistant":
        messages.pop(0)
    return messages


def append_turn(
    owner_id: str | None,
    thread_id: str,
    user_message: str,
    assistant_message: str,
    language: str = "en",
) -> None:
    """Atomically append one complete turn and prune expired/excess history."""
    owner, thread = _owner_hash(owner_id), _thread_id(thread_id)
    max_message_chars = _int_setting("FASTCLINIC_CHAT_MESSAGE_CHARS", 12000, 1000, 50000)
    keep_messages = _int_setting("FASTCLINIC_CHAT_STORED_MESSAGES", 100, 2, 1000)
    retention_days = _int_setting("FASTCLINIC_CHAT_RETENTION_DAYS", 30, 1, 3650)
    now = datetime.now(timezone.utc)
    values = (
        (owner, thread, "user", (user_message or "")[:max_message_chars], language, now.isoformat()),
        (owner, thread, "assistant", (assistant_message or "")[:max_message_chars], language, now.isoformat()),
    )
    with _connect() as connection:
        connection.executemany(
            """INSERT INTO chat_message
               (owner_hash,thread_id,role,content,language,created_at)
               VALUES (?,?,?,?,?,?)""",
            values,
        )
        connection.execute(
            "DELETE FROM chat_message WHERE created_at < ?",
            ((now - timedelta(days=retention_days)).isoformat(),),
        )
        connection.execute(
            """DELETE FROM chat_message
               WHERE owner_hash=? AND thread_id=? AND id NOT IN (
                   SELECT id FROM chat_message WHERE owner_hash=? AND thread_id=?
                   ORDER BY id DESC LIMIT ?
               )""",
            (owner, thread, owner, thread, keep_messages),
        )
        connection.commit()


def clear_thread(owner_id: str | None, thread_id: str) -> None:
    owner, thread = _owner_hash(owner_id), _thread_id(thread_id)
    with _connect() as connection:
        connection.execute(
            "DELETE FROM chat_message WHERE owner_hash=? AND thread_id=?", (owner, thread)
        )
        connection.commit()
