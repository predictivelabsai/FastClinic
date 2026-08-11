"""Domain-safe write helpers for the FastClinic integration API.

The imported clinical database remains the application's normalized read model.
These helpers provide narrow, transactional mutations for relationships, notes,
contacts, and consent without exposing arbitrary SQL through the API layer.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime

from web import db


ROLES = frozenset({"self", "guardian", "payer", "emergency", "family", "other"})


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def connection():
    conn = sqlite3.connect(db.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row(row) -> dict | None:
    return dict(row) if row else None


def _require(conn, table: str, item_id: int, label: str) -> dict:
    row = conn.execute(f'SELECT * FROM "{table}" WHERE id=?', (item_id,)).fetchone()
    if not row:
        raise NotFound(f"{label} {item_id} was not found")
    return dict(row)


def relationships(
    *, subject_id: int | None = None, party_id: int | None = None
) -> list[dict]:
    sql = "SELECT * FROM subject_party_role WHERE 1=1"
    params: list[int] = []
    if subject_id is not None:
        sql += " AND subject_id=?"
        params.append(subject_id)
    if party_id is not None:
        sql += " AND party_id=?"
        params.append(party_id)
    sql += " ORDER BY subject_id, is_primary DESC, role, party_id"
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def relationship(subject_id: int, party_id: int, role: str) -> dict | None:
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return _row(
            conn.execute(
                """SELECT * FROM subject_party_role
                   WHERE subject_id=? AND party_id=? AND role=?""",
                (subject_id, party_id, role),
            ).fetchone()
        )


def _refresh_party_count(conn, party_id: int) -> None:
    conn.execute(
        """UPDATE party SET subject_count=(
               SELECT COUNT(DISTINCT subject_id) FROM subject_party_role
               WHERE party_id=?
           ) WHERE id=?""",
        (party_id, party_id),
    )


def _normalise_primary(
    conn,
    subject_id: int,
    *,
    preferred: tuple[int, str] | None = None,
    avoid: tuple[int, str] | None = None,
) -> None:
    """Keep exactly one primary relationship and subject.party_id in sync."""
    if preferred is not None:
        selected = conn.execute(
            """SELECT party_id, role FROM subject_party_role
               WHERE subject_id=? AND party_id=? AND role=?""",
            (subject_id, *preferred),
        ).fetchone()
    else:
        rows = conn.execute(
            """SELECT party_id, role, is_primary FROM subject_party_role
               WHERE subject_id=? ORDER BY is_primary DESC, party_id, role""",
            (subject_id,),
        ).fetchall()
        selected = next(
            (
                row for row in rows
                if avoid is None or (row["party_id"], row["role"]) != avoid
            ),
            rows[0] if rows else None,
        )
    conn.execute(
        "UPDATE subject_party_role SET is_primary=0 WHERE subject_id=?",
        (subject_id,),
    )
    party_id = selected["party_id"] if selected else None
    if selected:
        conn.execute(
            """UPDATE subject_party_role SET is_primary=1
               WHERE subject_id=? AND party_id=? AND role=?""",
            (subject_id, selected["party_id"], selected["role"]),
        )
    conn.execute(
        "UPDATE subject SET party_id=?, modified=? WHERE id=?",
        (party_id, _now(), subject_id),
    )


def create_relationship(
    subject_id: int,
    party_id: int,
    role: str,
    is_primary: bool,
) -> dict:
    role = role.strip().lower()
    if role not in ROLES:
        raise Conflict(f"role must be one of {', '.join(sorted(ROLES))}")
    with connection() as conn:
        _require(conn, "subject", subject_id, "Patient")
        _require(conn, "party", party_id, "Party")
        if conn.execute(
            """SELECT 1 FROM subject_party_role
               WHERE subject_id=? AND party_id=? AND role=?""",
            (subject_id, party_id, role),
        ).fetchone():
            raise Conflict("Relationship already exists")
        conn.execute(
            """INSERT INTO subject_party_role
               (subject_id, party_id, role, is_primary) VALUES (?,?,?,?)""",
            (subject_id, party_id, role, int(is_primary)),
        )
        _normalise_primary(
            conn,
            subject_id,
            preferred=(party_id, role) if is_primary else None,
        )
        _refresh_party_count(conn, party_id)
    return relationship(subject_id, party_id, role) or {}


def update_relationship(
    subject_id: int,
    party_id: int,
    role: str,
    *,
    new_role: str | None = None,
    is_primary: bool | None = None,
) -> tuple[dict, dict]:
    before = relationship(subject_id, party_id, role)
    if not before:
        raise NotFound("Relationship was not found")
    target_role = (new_role or role).strip().lower()
    if target_role not in ROLES:
        raise Conflict(f"role must be one of {', '.join(sorted(ROLES))}")
    target_primary = bool(before["is_primary"]) if is_primary is None else is_primary
    with connection() as conn:
        try:
            conn.execute(
                """UPDATE subject_party_role SET role=?, is_primary=?
                   WHERE subject_id=? AND party_id=? AND role=?""",
                (target_role, int(target_primary), subject_id, party_id, role),
            )
        except sqlite3.IntegrityError as exc:
            raise Conflict("The requested relationship already exists") from exc
        _normalise_primary(
            conn,
            subject_id,
            preferred=(party_id, target_role) if target_primary else None,
            avoid=(party_id, target_role) if before["is_primary"] and not target_primary else None,
        )
    return before, relationship(subject_id, party_id, target_role) or before


def delete_relationship(subject_id: int, party_id: int, role: str) -> dict:
    before = relationship(subject_id, party_id, role)
    if not before:
        raise NotFound("Relationship was not found")
    with connection() as conn:
        conn.execute(
            "DELETE FROM subject_party_role WHERE subject_id=? AND party_id=? AND role=?",
            (subject_id, party_id, role),
        )
        _normalise_primary(conn, subject_id)
        _refresh_party_count(conn, party_id)
    return before


def delete_unlinked_party(party_id: int) -> dict:
    with connection() as conn:
        before = _require(conn, "party", party_id, "Party")
        linked = conn.execute(
            "SELECT COUNT(*) FROM subject_party_role WHERE party_id=?", (party_id,)
        ).fetchone()[0]
        if linked:
            raise Conflict("Linked parties cannot be deleted; remove relationships first")
        conn.execute("DELETE FROM party WHERE id=?", (party_id,))
    return before


def create_note(values: dict) -> dict:
    subject_id = int(values["subject_id"])
    consultation_id = values.get("consultation_id")
    text = str(values["text"]).strip()
    if not text:
        raise Conflict("Note text is required")
    with connection() as conn:
        _require(conn, "subject", subject_id, "Patient")
        if consultation_id is not None:
            consultation = _require(conn, "consultation", int(consultation_id), "Consultation")
            if consultation.get("subject_id") != subject_id:
                raise Conflict("Consultation does not belong to the supplied patient")
        payload = {
            "subject_id": subject_id,
            "consultation_id": consultation_id,
            "text": text,
            "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "type": values.get("type"),
            "custom_type": values.get("custom_type"),
            "draft": int(bool(values.get("draft", True))),
            "note_at": values.get("note_at") or _now(),
            "clinician_id": values.get("clinician_id"),
            "approved": 0,
            "created": _now(),
            "modified": _now(),
        }
        fields = tuple(payload)
        cursor = conn.execute(
            f"INSERT INTO note ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
            tuple(payload[field] for field in fields),
        )
        note_id = cursor.lastrowid
    return get_note(note_id) or payload


def get_note(note_id: int) -> dict | None:
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return _row(conn.execute("SELECT * FROM note WHERE id=?", (note_id,)).fetchone())


def update_note(note_id: int, values: dict) -> tuple[dict, dict]:
    before = get_note(note_id)
    if not before:
        raise NotFound(f"Note {note_id} was not found")
    clean = {
        key: value for key, value in values.items()
        if key in {"text", "type", "custom_type", "draft", "clinician_id", "edit_reason"}
    }
    if "text" in clean:
        clean["text"] = str(clean["text"]).strip()
        if not clean["text"]:
            raise Conflict("Note text cannot be empty")
        if before.get("approved") and not str(clean.get("edit_reason") or "").strip():
            raise Conflict("Editing an approved note requires edit_reason")
        clean["text_hash"] = hashlib.sha256(clean["text"].encode("utf-8")).hexdigest()
    if "draft" in clean:
        clean["draft"] = int(bool(clean["draft"]))
    clean["modified"] = _now()
    with connection() as conn:
        assignments = ",".join(f"{field}=?" for field in clean)
        conn.execute(
            f"UPDATE note SET {assignments} WHERE id=?",
            (*clean.values(), note_id),
        )
    return before, get_note(note_id) or before


def archive_note(note_id: int) -> tuple[dict, dict]:
    before = get_note(note_id)
    if not before:
        raise NotFound(f"Note {note_id} was not found")
    with connection() as conn:
        conn.execute(
            "UPDATE note SET archived_at=?, modified=? WHERE id=?",
            (_now(), _now(), note_id),
        )
    return before, get_note(note_id) or before


def set_marketing_opt_out(party_id: int, opted_out: bool) -> tuple[dict, dict]:
    with connection() as conn:
        before = _require(conn, "party", party_id, "Party")
        conn.execute(
            "UPDATE party SET marketing_opt_out=? WHERE id=?",
            (int(opted_out), party_id),
        )
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        after = _row(conn.execute("SELECT * FROM party WHERE id=?", (party_id,)).fetchone())
    return before, after or before
