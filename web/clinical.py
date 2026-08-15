"""Writable clinical workspace — encounters, orders, tasks, messages, coverage.

Imported PMS consultations stay read-only. This module records *new* charting
and care-coordination work in the ops database so a re-import never wipes it.
"""
from __future__ import annotations

import json

from web import activation_loop as ops
from web import db
from web.access import audit

ORDER_KINDS = ("lab", "imaging", "referral", "medication")
ORDER_STATUSES = ("draft", "active", "completed", "cancelled")
ENCOUNTER_STATUSES = ("planned", "in-progress", "finished", "cancelled")
TASK_STATUSES = ("requested", "in-progress", "completed", "cancelled")


class ClinicalError(ValueError):
    pass


def _require_subject(subject_id: int) -> dict:
    row = db.query_one("SELECT * FROM subject WHERE id=?", (int(subject_id),))
    if not row:
        raise ClinicalError(f"Patient {subject_id} was not found")
    return row


def _row(table: str, item_id: int) -> dict | None:
    rows = ops.query(f"SELECT * FROM {table} WHERE id=?", (int(item_id),))
    return rows[0] if rows else None


# ---------------------------------------------------------------- encounters --
def open_encounter(subject_id: int, *, clinician_id: int | None = None,
                   reason: str = "", consultation_id: int | None = None,
                   actor: str = "") -> dict:
    _require_subject(subject_id)
    now = ops._now()
    eid = ops.execute(
        "INSERT INTO chart_encounter (subject_id, consultation_id, clinician_id, status, "
        "reason, started_at, created_at) VALUES (?,?,?,?,?,?,?)",
        (int(subject_id), consultation_id, clinician_id, "in-progress",
         (reason or "").strip()[:500], now, now),
    )
    audit(actor, "open", "chart_encounter", eid)
    return encounter(eid)


def finish_encounter(encounter_id: int, *, actor: str = "") -> dict:
    row = encounter(encounter_id)
    if not row:
        raise ClinicalError(f"Encounter {encounter_id} was not found")
    if row["status"] == "finished":
        return row
    ops.execute(
        "UPDATE chart_encounter SET status='finished', ended_at=? WHERE id=?",
        (ops._now(), int(encounter_id)),
    )
    audit(actor, "finish", "chart_encounter", encounter_id)
    return encounter(encounter_id)


def encounter(encounter_id: int) -> dict | None:
    return _row("chart_encounter", encounter_id)


def encounters_for(subject_id: int) -> list[dict]:
    return ops.query(
        "SELECT * FROM chart_encounter WHERE subject_id=? ORDER BY started_at DESC, id DESC",
        (int(subject_id),),
    )


def active_encounter(subject_id: int) -> dict | None:
    rows = ops.query(
        "SELECT * FROM chart_encounter WHERE subject_id=? AND status='in-progress' "
        "ORDER BY id DESC LIMIT 1",
        (int(subject_id),),
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------------- notes --
def add_note(subject_id: int, *, encounter_id: int | None = None,
             clinician_id: int | None = None, kind: str = "soap",
             subjective: str = "", objective: str = "", assessment: str = "",
             plan: str = "", actor: str = "") -> dict:
    _require_subject(subject_id)
    if encounter_id and not encounter(encounter_id):
        raise ClinicalError(f"Encounter {encounter_id} was not found")
    nid = ops.execute(
        "INSERT INTO chart_note (encounter_id, subject_id, clinician_id, kind, "
        "subjective, objective, assessment, plan, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (encounter_id, int(subject_id), clinician_id, kind or "soap",
         subjective.strip(), objective.strip(), assessment.strip(), plan.strip(),
         ops._now()),
    )
    audit(actor, "create", "chart_note", nid)
    return _row("chart_note", nid) or {}


def notes_for(subject_id: int) -> list[dict]:
    return ops.query(
        "SELECT * FROM chart_note WHERE subject_id=? ORDER BY id DESC",
        (int(subject_id),),
    )


# --------------------------------------------------------------------- orders --
def place_order(subject_id: int, kind: str, name: str, *,
                encounter_id: int | None = None, clinician_id: int | None = None,
                code: str = "", details: str = "", actor: str = "") -> dict:
    _require_subject(subject_id)
    if kind not in ORDER_KINDS:
        raise ClinicalError(f"kind must be one of {', '.join(ORDER_KINDS)}")
    title = (name or "").strip()
    if not title:
        raise ClinicalError("Order name is required")
    oid = ops.execute(
        "INSERT INTO clinical_order (encounter_id, subject_id, clinician_id, kind, code, "
        "name, status, details, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (encounter_id, int(subject_id), clinician_id, kind, (code or "").strip(),
         title[:240], "active", (details or "").strip(), ops._now()),
    )
    audit(actor, "create", "clinical_order", oid)
    return _row("clinical_order", oid) or {}


def set_order_status(order_id: int, status: str, *, actor: str = "") -> dict:
    if status not in ORDER_STATUSES:
        raise ClinicalError(f"status must be one of {', '.join(ORDER_STATUSES)}")
    row = _row("clinical_order", order_id)
    if not row:
        raise ClinicalError(f"Order {order_id} was not found")
    done = ops._now() if status == "completed" else None
    ops.execute(
        "UPDATE clinical_order SET status=?, completed_at=? WHERE id=?",
        (status, done, int(order_id)),
    )
    audit(actor, status, "clinical_order", order_id)
    return _row("clinical_order", order_id) or {}


def order(order_id: int) -> dict | None:
    return _row("clinical_order", order_id)


def orders(*, subject_id: int | None = None, status: str | None = None,
           kind: str | None = None, limit: int = 100) -> list[dict]:
    where, params = ["1=1"], []
    if subject_id is not None:
        where.append("subject_id=?")
        params.append(int(subject_id))
    if status:
        where.append("status=?")
        params.append(status)
    if kind:
        where.append("kind=?")
        params.append(kind)
    params.append(limit)
    return ops.query(
        f"SELECT * FROM clinical_order WHERE {' AND '.join(where)} "
        "ORDER BY id DESC LIMIT ?",
        tuple(params),
    )


# ---------------------------------------------------------------------- tasks --
def add_task(subject_id: int, title: str, *, encounter_id: int | None = None,
             assignee: str = "", due_date: str = "", actor: str = "") -> dict:
    _require_subject(subject_id)
    text = (title or "").strip()
    if not text:
        raise ClinicalError("Task title is required")
    tid = ops.execute(
        "INSERT INTO care_task (subject_id, encounter_id, assignee, title, status, "
        "due_date, created_at) VALUES (?,?,?,?,?,?,?)",
        (int(subject_id), encounter_id, (assignee or "").strip(), text[:240],
         "requested", due_date or None, ops._now()),
    )
    audit(actor, "create", "care_task", tid)
    return _row("care_task", tid) or {}


def set_task_status(task_id: int, status: str, *, actor: str = "") -> dict:
    if status not in TASK_STATUSES:
        raise ClinicalError(f"status must be one of {', '.join(TASK_STATUSES)}")
    if not _row("care_task", task_id):
        raise ClinicalError(f"Task {task_id} was not found")
    ops.execute("UPDATE care_task SET status=? WHERE id=?", (status, int(task_id)))
    audit(actor, status, "care_task", task_id)
    return _row("care_task", task_id) or {}


def task(task_id: int) -> dict | None:
    return _row("care_task", task_id)


def tasks(*, subject_id: int | None = None, status: str | None = None,
          limit: int = 100) -> list[dict]:
    where, params = ["1=1"], []
    if subject_id is not None:
        where.append("subject_id=?")
        params.append(int(subject_id))
    if status:
        where.append("status=?")
        params.append(status)
    params.append(limit)
    return ops.query(
        f"SELECT * FROM care_task WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?",
        tuple(params),
    )


# ------------------------------------------------------------------- coverage --
def add_coverage(subject_id: int, payor: str, *, member_id: str = "",
                 party_id: int | None = None, actor: str = "") -> dict:
    _require_subject(subject_id)
    name = (payor or "").strip()
    if not name:
        raise ClinicalError("Payor is required")
    cid = ops.execute(
        "INSERT INTO coverage (subject_id, party_id, payor, member_id, status, created_at) "
        "VALUES (?,?,?,?, 'active', ?)",
        (int(subject_id), party_id, name[:160], (member_id or "").strip()[:80], ops._now()),
    )
    audit(actor, "create", "coverage", cid)
    return _row("coverage", cid) or {}


def coverages_for(subject_id: int) -> list[dict]:
    return ops.query(
        "SELECT * FROM coverage WHERE subject_id=? ORDER BY id DESC",
        (int(subject_id),),
    )


# ------------------------------------------------------------------ messaging --
def start_thread(title: str, *, subject_id: int | None = None,
                 body: str = "", sender_email: str = "",
                 sender_role: str = "") -> dict:
    text = (title or "").strip() or "Conversation"
    tid = ops.execute(
        "INSERT INTO inbox_thread (subject_id, title, created_at) VALUES (?,?,?)",
        (subject_id, text[:200], ops._now()),
    )
    if body.strip():
        post_message(tid, body, sender_email=sender_email, sender_role=sender_role)
    return thread(tid) or {}


def post_message(thread_id: int, body: str, *, sender_email: str = "",
                 sender_role: str = "") -> dict:
    if not thread(thread_id):
        raise ClinicalError(f"Thread {thread_id} was not found")
    text = (body or "").strip()
    if not text:
        raise ClinicalError("Message body is required")
    mid = ops.execute(
        "INSERT INTO inbox_message (thread_id, sender_email, sender_role, body, created_at) "
        "VALUES (?,?,?,?,?)",
        (int(thread_id), (sender_email or "").strip().lower(), sender_role,
         text[:8000], ops._now()),
    )
    audit(sender_email, "create", "inbox_message", mid)
    return _row("inbox_message", mid) or {}


def thread(thread_id: int) -> dict | None:
    return _row("inbox_thread", thread_id)


def threads(*, subject_id: int | None = None, limit: int = 50) -> list[dict]:
    if subject_id is not None:
        return ops.query(
            "SELECT * FROM inbox_thread WHERE subject_id=? ORDER BY id DESC LIMIT ?",
            (int(subject_id), limit),
        )
    return ops.query("SELECT * FROM inbox_thread ORDER BY id DESC LIMIT ?", (limit,))


def messages(thread_id: int) -> list[dict]:
    return ops.query(
        "SELECT * FROM inbox_message WHERE thread_id=? ORDER BY id",
        (int(thread_id),),
    )


# --------------------------------------------------------------------- intake --
def save_intake(subject_id: int, answers: dict, *, title: str = "Patient intake",
                actor: str = "") -> dict:
    _require_subject(subject_id)
    iid = ops.execute(
        "INSERT INTO intake_form (subject_id, title, status, answers_json, created_at) "
        "VALUES (?,?, 'completed', ?, ?)",
        (int(subject_id), (title or "Patient intake")[:160],
         json.dumps(answers, ensure_ascii=False), ops._now()),
    )
    audit(actor, "create", "intake_form", iid)
    return _row("intake_form", iid) or {}


def intakes_for(subject_id: int) -> list[dict]:
    return ops.query(
        "SELECT * FROM intake_form WHERE subject_id=? ORDER BY id DESC",
        (int(subject_id),),
    )


def order_counts() -> dict:
    rows = ops.query("SELECT status, COUNT(*) AS n FROM clinical_order GROUP BY status")
    return {row["status"]: row["n"] for row in rows}


def task_counts() -> dict:
    rows = ops.query("SELECT status, COUNT(*) AS n FROM care_task GROUP BY status")
    return {row["status"]: row["n"] for row in rows}
