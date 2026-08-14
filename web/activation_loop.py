"""Persisted activation loop — reminders, the communication log, and outcomes.

Phase 2 of the Clinic OS plan (docs/CLINIC_OS_PLAN.md §6). The activation engines
in `web/activation.py` compute *who to contact* from clinic history; this module
records *what was actually done about it* so the loop is closed and measurable:

    reminder        a persisted intent to contact a subject about something,
                    with per-channel bodies, a due date, and optional recurrence.
                    Shaped after Provet's Reminder / FHIR ImmunizationRecommendation.
    communication   an immutable log row: a message actually sent (or blocked /
                    failed), to which party, on which channel, with the provider
                    message id. This is what lets us suppress duplicates and
                    attribute a return visit to a nudge.
    attribution     did a qualifying visit follow a communication within N days?

Operational state lives in its OWN SQLite file, not the PMS replica: re-running
`pms.importer` drops and rebuilds the read-only replica, and activation state must
survive that. Path: FASTCLINIC_OPS_DB, else fastclinic_ops.sqlite beside the app.
"""
from __future__ import annotations

import os
import json
from datetime import datetime, timedelta

from web.db import query as _main_query, reference_date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPS_DB_PATH = os.getenv("FASTCLINIC_OPS_DB") or os.path.join(ROOT, "fastclinic_ops.sqlite")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reminder (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER,
    category TEXT,
    source_engine TEXT,
    due_date TEXT,
    status TEXT DEFAULT 'pending',
    sms_text TEXT,
    email_subject TEXT,
    email_text TEXT,
    recurring_interval_days INTEGER,
    created_at TEXT,
    sent_at TEXT
);
CREATE TABLE IF NOT EXISTS communication (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reminder_id INTEGER,
    subject_id INTEGER,
    party_id INTEGER,
    channel TEXT,
    to_addr TEXT,
    body TEXT,
    provider TEXT,
    provider_message_id TEXT,
    status TEXT,
    error TEXT,
    sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_comm_subject ON communication (subject_id);
CREATE INDEX IF NOT EXISTS idx_reminder_subject ON reminder (subject_id);
CREATE TABLE IF NOT EXISTS appointment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER,
    party_id INTEGER,
    clinician_id INTEGER,
    start_at TEXT,
    end_at TEXT,
    status TEXT DEFAULT 'scheduled',
    reason TEXT,
    room TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_appt_clinician ON appointment (clinician_id, start_at);
CREATE INDEX IF NOT EXISTS idx_appt_subject ON appointment (subject_id);
CREATE TABLE IF NOT EXISTS external_booking (
    idempotency_key TEXT PRIMARY KEY,
    appointment_id INTEGER NOT NULL,
    guest_name TEXT NOT NULL,
    guest_email TEXT NOT NULL,
    guest_phone TEXT,
    service_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_external_booking_appointment
    ON external_booking (appointment_id);
CREATE TABLE IF NOT EXISTS invoice (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    consultation_id INTEGER,
    subject_id INTEGER,
    party_id INTEGER,            -- the payer (role=payer, else primary party)
    invoice_date TEXT,
    due_date TEXT,
    total REAL,
    paid REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'Unpaid',
    created_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_invoice_consult ON invoice (consultation_id);
CREATE TABLE IF NOT EXISTS gl_entry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT,
    account TEXT,
    debit REAL,
    credit REAL,
    ref TEXT
);
CREATE TABLE IF NOT EXISTS payment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    method TEXT,
    reference TEXT,
    status TEXT NOT NULL DEFAULT 'received',
    idempotency_key TEXT,
    received_at TEXT,
    created_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_idempotency
    ON payment (idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payment_invoice ON payment (invoice_id);
CREATE TABLE IF NOT EXISTS api_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    item_id TEXT,
    before_json TEXT,
    after_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_api_audit_resource
    ON api_audit (resource, item_id, created_at);
"""


def _connect():
    from web.ops_db import connect
    return connect(OPS_DB_PATH)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def query(sql: str, params: tuple = ()) -> list[dict]:
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def execute(sql: str, params: tuple = ()) -> int:
    with _connect() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def log_api_audit(
    action: str,
    resource: str,
    item_id: str,
    before: dict | None,
    after: dict | None,
) -> None:
    """Append a mutation record without storing credentials or request secrets."""
    execute(
        """INSERT INTO api_audit
           (action, resource, item_id, before_json, after_json, created_at)
           VALUES (?,?,?,?,?,?)""",
        (
            action,
            resource,
            str(item_id),
            json.dumps(before, sort_keys=True, default=str) if before is not None else None,
            json.dumps(after, sort_keys=True, default=str) if after is not None else None,
            _now(),
        ),
    )


def api_audit(limit: int = 100, resource: str = "") -> list[dict]:
    if resource:
        return query(
            "SELECT * FROM api_audit WHERE resource=? ORDER BY id DESC LIMIT ?",
            (resource, limit),
        )
    return query("SELECT * FROM api_audit ORDER BY id DESC LIMIT ?", (limit,))


def external_booking(idempotency_key: str) -> dict | None:
    rows = query(
        """SELECT e.*, a.clinician_id, a.start_at, a.end_at, a.room
           FROM external_booking e
           JOIN appointment a ON a.id=e.appointment_id
           WHERE e.idempotency_key=?""",
        (idempotency_key,),
    )
    return rows[0] if rows else None


def create_external_booking(
    *,
    idempotency_key: str,
    appointment_id: int,
    guest_name: str,
    guest_email: str,
    guest_phone: str,
    service_id: str,
) -> dict:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO external_booking
               (idempotency_key,appointment_id,guest_name,guest_email,guest_phone,
                service_id,status,created_at)
               VALUES (?,?,?,?,?,?, 'confirmed', ?)""",
            (
                idempotency_key,
                appointment_id,
                guest_name[:160],
                guest_email.lower()[:320],
                guest_phone[:40],
                service_id[:120],
                _now(),
            ),
        )
        conn.commit()
    return external_booking(idempotency_key)


def cancel_external_booking(appointment_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT appointment_id FROM external_booking WHERE appointment_id=?",
            (appointment_id,),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE external_booking SET status='cancelled' WHERE appointment_id=?",
            (appointment_id,),
        )
        conn.execute(
            "UPDATE appointment SET status='cancelled' WHERE id=?",
            (appointment_id,),
        )
        conn.commit()
    rows = query(
        "SELECT * FROM external_booking WHERE appointment_id=?", (appointment_id,)
    )
    return rows[0] if rows else None


def _primary_subject(party_id) -> int | None:
    if party_id is None:
        return None
    rows = _main_query(
        "SELECT subject_id FROM subject_party_role WHERE party_id=? "
        "ORDER BY is_primary DESC LIMIT 1", (party_id,))
    return rows[0]["subject_id"] if rows else None


def resolve_by_phone(phone: str) -> tuple[int | None, int | None]:
    """Best-effort (party_id, subject_id) for an outbound phone number."""
    rows = _main_query("SELECT id FROM party WHERE phone=? LIMIT 1", (phone,))
    pid = rows[0]["id"] if rows else None
    return pid, _primary_subject(pid)


def resolve_by_email(email: str) -> tuple[int | None, int | None]:
    rows = _main_query("SELECT id FROM party WHERE LOWER(TRIM(email))=? LIMIT 1",
                       ((email or "").strip().lower(),))
    pid = rows[0]["id"] if rows else None
    return pid, _primary_subject(pid)


# ------------------------------------------------------------------ reminders --
def create_reminder(subject_id: int, category: str, *, source_engine: str = "manual",
                    due_date: str | None = None, sms_text: str | None = None,
                    email_subject: str | None = None, email_text: str | None = None,
                    recurring_interval_days: int | None = None) -> int:
    return execute(
        """INSERT INTO reminder (subject_id, category, source_engine, due_date,
               status, sms_text, email_subject, email_text,
               recurring_interval_days, created_at)
           VALUES (?,?,?,?, 'pending', ?,?,?, ?, ?)""",
        (subject_id, category, source_engine, due_date, sms_text, email_subject,
         email_text, recurring_interval_days, _now()),
    )


def enqueue_due_reminders() -> int:
    """Persist a pending reminder for each currently-due recurring service.

    Idempotent per (subject, category): a subject already holding a pending
    reminder for that category is skipped, so re-running does not pile up dupes.
    Message copy is drafted once at enqueue time from the same engine the UI uses.
    """
    from web.activation import due_rows, draft_reminder  # local: avoid import cycle
    from pms.catalog import recall_interval_days

    created = 0
    with _connect() as conn:  # one connection for the whole batch
        seen = {(r["subject_id"], r["category"]) for r in conn.execute(
            "SELECT subject_id, category FROM reminder WHERE status='pending'"
        ).fetchall()}
        for r in due_rows():
            sid, cat = r.get("patient_id"), r.get("category")
            if sid is None or not cat or (sid, cat) in seen:
                continue
            seen.add((sid, cat))
            conn.execute(
                """INSERT INTO reminder (subject_id, category, source_engine, due_date,
                       status, sms_text, email_subject, email_text,
                       recurring_interval_days, created_at)
                   VALUES (?,?,?,?, 'pending', ?, NULL, NULL, ?, ?)""",
                (sid, cat, "reminders", r.get("due_date"), draft_reminder(r),
                 recall_interval_days(cat) or None, _now()),
            )
            created += 1
        conn.commit()
    return created


def mark_sent(reminder_id: int) -> None:
    """Provet's mark_sent transition; rolls a recurring reminder forward."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT due_date, recurring_interval_days FROM reminder WHERE id=?",
            (reminder_id,),
        ).fetchone()
        conn.execute("UPDATE reminder SET status='sent', sent_at=? WHERE id=?",
                     (_now(), reminder_id))
        # A recurring reminder spawns its next occurrence rather than dying.
        if row and row["recurring_interval_days"] and row["due_date"]:
            try:
                nxt = (datetime.fromisoformat(row["due_date"][:10])
                       + timedelta(days=int(row["recurring_interval_days"]))).date().isoformat()
                conn.execute(
                    """INSERT INTO reminder (subject_id, category, source_engine,
                           due_date, status, sms_text, email_subject, email_text,
                           recurring_interval_days, created_at)
                       SELECT subject_id, category, source_engine, ?, 'pending',
                           sms_text, email_subject, email_text,
                           recurring_interval_days, ? FROM reminder WHERE id=?""",
                    (nxt, _now(), reminder_id),
                )
            except ValueError:
                pass
        conn.commit()


def pending_reminders(limit: int = 200) -> list[dict]:
    return query("SELECT * FROM reminder WHERE status='pending' "
                 "ORDER BY due_date LIMIT ?", (limit,))


def get_reminder(reminder_id: int) -> dict | None:
    rows = query("SELECT * FROM reminder WHERE id=?", (reminder_id,))
    return rows[0] if rows else None


def update_reminder(reminder_id: int, values: dict) -> tuple[dict, dict] | None:
    before = get_reminder(reminder_id)
    if not before:
        return None
    allowed = {
        "category", "due_date", "status", "sms_text", "email_subject",
        "email_text", "recurring_interval_days",
    }
    clean = {key: value for key, value in values.items() if key in allowed}
    if not clean:
        raise ValueError("At least one reminder field is required")
    if clean.get("status") not in {None, "pending", "sent", "cancelled", "failed"}:
        raise ValueError("Invalid reminder status")
    # ``mark_sent`` also creates the next recurring occurrence, so use it only
    # for the actual transition.  Apply any accompanying content/date edits
    # first so the rolled-forward reminder inherits the updated values.
    transitions_to_sent = clean.get("status") == "sent" and before["status"] != "sent"
    fields_to_update = dict(clean)
    if transitions_to_sent:
        fields_to_update.pop("status")
    if fields_to_update:
        assignments = ",".join(f"{field}=?" for field in fields_to_update)
        with _connect() as conn:
            conn.execute(
                f"UPDATE reminder SET {assignments} WHERE id=?",
                (*fields_to_update.values(), reminder_id),
            )
            conn.commit()
    if transitions_to_sent:
        mark_sent(reminder_id)
    return before, get_reminder(reminder_id) or before


def cancel_reminder(reminder_id: int) -> tuple[dict, dict] | None:
    return update_reminder(reminder_id, {"status": "cancelled"})


def reminder_counts() -> dict:
    rows = query("SELECT status, COUNT(*) AS n FROM reminder GROUP BY status")
    return {r["status"]: r["n"] for r in rows}


# ------------------------------------------------------------- communications --
def log_communication(*, channel: str, to_addr: str, body: str,
                      status: str, subject_id: int | None = None,
                      party_id: int | None = None, reminder_id: int | None = None,
                      provider: str = "", provider_message_id: str = "",
                      error: str = "") -> int:
    """Record an outbound attempt — sent, failed, or blocked. Immutable log."""
    return execute(
        """INSERT INTO communication (reminder_id, subject_id, party_id, channel,
               to_addr, body, provider, provider_message_id, status, error, sent_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (reminder_id, subject_id, party_id, channel, to_addr, body, provider,
         provider_message_id, status, error, _now()),
    )


def recent_communications(limit: int = 100) -> list[dict]:
    return query("SELECT * FROM communication ORDER BY id DESC LIMIT ?", (limit,))


def get_communication(communication_id: int) -> dict | None:
    rows = query("SELECT * FROM communication WHERE id=?", (communication_id,))
    return rows[0] if rows else None


def communication_counts() -> dict:
    rows = query("SELECT status, COUNT(*) AS n FROM communication GROUP BY status")
    return {r["status"]: r["n"] for r in rows}


def already_contacted(subject_id: int, category: str, within_days: int = 30) -> bool:
    """Has this subject been messaged about this category recently? Duplicate guard."""
    if subject_id is None:
        return False
    cutoff = (datetime.now() - timedelta(days=within_days)).isoformat(timespec="seconds")
    rows = query(
        """SELECT 1 FROM communication c
           WHERE c.subject_id=? AND c.status='sent' AND c.sent_at >= ?
             AND (c.reminder_id IN (SELECT id FROM reminder WHERE category=?)
                  OR ?='')
           LIMIT 1""",
        (subject_id, cutoff, category, category or ""),
    )
    return bool(rows)


# ----------------------------------------------------------------- attribution --
def attribution(within_days: int = 30) -> dict:
    """Did a qualifying visit follow each sent communication within N days?

    Joins the ops communication log to the read-only PMS replica in Python (the
    two live in separate SQLite files). A 'qualifying visit' is any consultation
    with is_visit=1 dated after the message and within the window.
    """
    sent = query("SELECT id, subject_id, sent_at FROM communication "
                 "WHERE status='sent' AND subject_id IS NOT NULL")
    if not sent:
        return {"sent": 0, "converted": 0, "rate": 0.0, "within_days": within_days}
    converted = 0
    for c in sent:
        start = c["sent_at"][:10]
        end = (datetime.fromisoformat(start) + timedelta(days=within_days)).date().isoformat()
        hit = _main_query(
            "SELECT 1 FROM consultation WHERE subject_id=? AND is_visit=1 "
            "AND consult_at > ? AND consult_at <= ? LIMIT 1",
            (c["subject_id"], start, end),
        )
        if hit:
            converted += 1
    n = len(sent)
    return {"sent": n, "converted": converted,
            "rate": round(converted / n, 4) if n else 0.0, "within_days": within_days}
