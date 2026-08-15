"""Portable operational-state storage for SQLite and PostgreSQL.

Production follows ``FASTCLINIC_OPS_BACKEND`` (or the clinical backend when it
is unset) and uses ``DATABASE_URL_PROD`` plus ``FASTCLINIC_DB_SCHEMA``. Tests and
local installs can continue to provide ``FASTCLINIC_OPS_DB`` for SQLite.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "fastclinic_ops.sqlite"
_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def backend_name() -> str:
    explicit = (os.getenv("FASTCLINIC_OPS_BACKEND") or "").strip().lower()
    if explicit:
        value = explicit
    elif os.getenv("FASTCLINIC_OPS_DB"):
        value = "sqlite"
    else:
        value = (os.getenv("FASTCLINIC_DATABASE_BACKEND") or "postgresql").lower()
    if value in {"postgres", "postgresql", "pg"}:
        return "postgresql"
    if value == "sqlite":
        return "sqlite"
    raise RuntimeError("FASTCLINIC_OPS_BACKEND must be 'sqlite' or 'postgresql'")


def is_postgres() -> bool:
    return backend_name() == "postgresql"


def _schema() -> str:
    value = os.getenv("FASTCLINIC_DB_SCHEMA") or "fast_clinic"
    if not _SCHEMA_RE.fullmatch(value):
        raise RuntimeError("FASTCLINIC_DB_SCHEMA is not a valid SQL identifier")
    return value


class Cursor:
    def __init__(self, raw, lastrowid: int | None = None):
        self.raw = raw
        self.lastrowid = lastrowid

    def fetchone(self):
        return self.raw.fetchone()

    def fetchall(self):
        return self.raw.fetchall()

    def __iter__(self):
        return iter(self.raw)


class Connection:
    def __init__(self, raw, postgres: bool):
        self.raw = raw
        self.postgres = postgres

    def execute(self, statement: str, params: tuple | list = ()) -> Cursor:
        if not self.postgres:
            raw_cursor = self.raw.execute(statement, params)
            return Cursor(raw_cursor, raw_cursor.lastrowid)
        normalized = statement.strip().upper()
        if normalized == "BEGIN IMMEDIATE":
            cursor = self.raw.cursor()
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            return Cursor(cursor)
        cursor = self.raw.cursor()
        cursor.execute(statement.replace("?", "%s"), params)
        lastrowid = None
        serial_tables = {
            "REMINDER", "COMMUNICATION", "APPOINTMENT", "INVOICE", "GL_ENTRY",
            "PAYMENT", "API_AUDIT", "CHAT_MESSAGE",
            "ACCOUNTS", "AUTH_TOKENS",
            "CHART_ENCOUNTER", "CHART_NOTE", "CLINICAL_ORDER", "COVERAGE",
            "CARE_TASK", "INBOX_THREAD", "INBOX_MESSAGE", "INTAKE_FORM",
            "ACCESS_AUDIT",
        }
        match = re.match(r'INSERT\s+INTO\s+["\']?([A-Za-z_][A-Za-z0-9_]*)', statement, re.I)
        if match and match.group(1).upper() in serial_tables:
            probe = self.raw.cursor()
            probe.execute("SELECT LASTVAL() AS id")
            lastrowid = probe.fetchone()["id"]
            probe.close()
        return Cursor(cursor, lastrowid)

    def executemany(self, statement: str, values) -> Cursor:
        cursor = self.raw.cursor() if self.postgres else self.raw.cursor()
        cursor.executemany(statement.replace("?", "%s") if self.postgres else statement, values)
        return Cursor(cursor)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.rollback()
        self.close()


def connect(sqlite_path: str | Path | None = None) -> Connection:
    if is_postgres():
        url = os.getenv("DATABASE_URL_PROD") or os.getenv("DATABASE_URL") or ""
        if not url:
            raise RuntimeError("DATABASE_URL_PROD is required for PostgreSQL operations storage")
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("PostgreSQL requires psycopg2") from exc
        raw = psycopg2.connect(
            url,
            connect_timeout=10,
            cursor_factory=RealDictCursor,
            options=f"-c search_path={_schema()}",
        )
        connection = Connection(raw, True)
        initialize(connection)
        return connection
    path = Path(sqlite_path or os.getenv("FASTCLINIC_OPS_DB") or DEFAULT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(path, timeout=15)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA busy_timeout=15000")
    connection = Connection(raw, False)
    initialize(connection)
    return connection


_TABLES = (
    """CREATE TABLE IF NOT EXISTS reminder (id {id}, subject_id INTEGER, category TEXT,
       source_engine TEXT, due_date TEXT, status TEXT DEFAULT 'pending', sms_text TEXT,
       email_subject TEXT, email_text TEXT, recurring_interval_days INTEGER,
       created_at TEXT, sent_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS communication (id {id}, reminder_id INTEGER,
       subject_id INTEGER, party_id INTEGER, channel TEXT, to_addr TEXT, body TEXT,
       provider TEXT, provider_message_id TEXT, status TEXT, error TEXT, sent_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS appointment (id {id}, subject_id INTEGER, party_id INTEGER,
       clinician_id INTEGER, start_at TEXT, end_at TEXT, status TEXT DEFAULT 'scheduled',
       reason TEXT, room TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS external_booking (idempotency_key TEXT PRIMARY KEY,
       appointment_id INTEGER NOT NULL UNIQUE, guest_name TEXT NOT NULL, guest_email TEXT NOT NULL,
       guest_phone TEXT, service_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'confirmed',
       created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS invoice (id {id}, code TEXT, consultation_id INTEGER UNIQUE,
       subject_id INTEGER, party_id INTEGER, invoice_date TEXT, due_date TEXT, total REAL,
       paid REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'Unpaid', created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS gl_entry (id {id}, entry_date TEXT, account TEXT,
       debit REAL, credit REAL, ref TEXT)""",
    """CREATE TABLE IF NOT EXISTS payment (id {id}, invoice_id INTEGER NOT NULL, amount REAL NOT NULL,
       method TEXT, reference TEXT, status TEXT NOT NULL DEFAULT 'received',
       idempotency_key TEXT UNIQUE, received_at TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS api_audit (id {id}, action TEXT NOT NULL, resource TEXT NOT NULL,
       item_id TEXT, before_json TEXT, after_json TEXT, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS chat_message (id {id}, owner_hash TEXT NOT NULL,
       thread_id TEXT NOT NULL, role TEXT NOT NULL CHECK (role IN ('user','assistant')),
       content TEXT NOT NULL, language TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS accounts (id {id}, email TEXT NOT NULL UNIQUE,
       name TEXT NOT NULL DEFAULT '', password_hash TEXT, is_verified INTEGER NOT NULL DEFAULT 0,
       google_linked INTEGER NOT NULL DEFAULT 0, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS auth_tokens (id {id}, account_id INTEGER NOT NULL
       REFERENCES accounts(id) ON DELETE CASCADE, purpose TEXT NOT NULL,
       token_hash TEXT NOT NULL UNIQUE, expires_at BIGINT NOT NULL, used_at BIGINT,
       created_at BIGINT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS auth_limits (subject_hash TEXT NOT NULL, action TEXT NOT NULL,
       window_start BIGINT NOT NULL, attempts INTEGER NOT NULL,
       PRIMARY KEY(subject_hash,action))""",
    """CREATE TABLE IF NOT EXISTS national_exchange (id TEXT PRIMARY KEY,
       country_code TEXT NOT NULL, idempotency_key TEXT NOT NULL,
       surface TEXT NOT NULL,
       document_type TEXT NOT NULL, subject_ref TEXT NOT NULL,
       practitioner_role_ref TEXT NOT NULL, correlation_id TEXT NOT NULL UNIQUE,
       status TEXT NOT NULL, payload_hash TEXT NOT NULL, request_json TEXT NOT NULL,
       response_json TEXT, error TEXT, attempt_count INTEGER NOT NULL DEFAULT 1,
       created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
       UNIQUE(country_code,idempotency_key))""",
    """CREATE TABLE IF NOT EXISTS access_role (role TEXT PRIMARY KEY, label TEXT NOT NULL,
       sort_order INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS access_profile (email TEXT PRIMARY KEY, role TEXT NOT NULL,
       subject_id INTEGER, clinician_id INTEGER, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS chart_encounter (id {id}, subject_id INTEGER NOT NULL,
       consultation_id INTEGER, clinician_id INTEGER, status TEXT NOT NULL DEFAULT 'in-progress',
       reason TEXT, started_at TEXT, ended_at TEXT, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS chart_note (id {id}, encounter_id INTEGER, subject_id INTEGER NOT NULL,
       clinician_id INTEGER, kind TEXT NOT NULL DEFAULT 'soap', subjective TEXT, objective TEXT,
       assessment TEXT, plan TEXT, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS clinical_order (id {id}, encounter_id INTEGER,
       subject_id INTEGER NOT NULL, clinician_id INTEGER, kind TEXT NOT NULL, code TEXT,
       name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', details TEXT,
       created_at TEXT NOT NULL, completed_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS coverage (id {id}, subject_id INTEGER NOT NULL, party_id INTEGER,
       payor TEXT NOT NULL, member_id TEXT, status TEXT NOT NULL DEFAULT 'active',
       created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS care_task (id {id}, subject_id INTEGER NOT NULL,
       encounter_id INTEGER, assignee TEXT, title TEXT NOT NULL,
       status TEXT NOT NULL DEFAULT 'requested', due_date TEXT, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS inbox_thread (id {id}, subject_id INTEGER, title TEXT NOT NULL,
       created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS inbox_message (id {id}, thread_id INTEGER NOT NULL,
       sender_email TEXT NOT NULL, sender_role TEXT, body TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS intake_form (id {id}, subject_id INTEGER NOT NULL,
       title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'completed', answers_json TEXT,
       created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS access_audit (id {id}, actor_email TEXT NOT NULL, action TEXT NOT NULL,
       resource TEXT NOT NULL, item_id TEXT, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS medbackend_oauth_transaction (
       state_hash TEXT PRIMARY KEY, account_email TEXT NOT NULL,
       code_verifier TEXT NOT NULL, expires_at BIGINT NOT NULL,
       used_at BIGINT, created_at BIGINT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS medbackend_connection_audit (
       id {id}, account_email TEXT NOT NULL, status TEXT NOT NULL,
       identity_reference TEXT, patient_count INTEGER, error_code TEXT,
       tested_at BIGINT NOT NULL)""",
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_comm_subject ON communication(subject_id)",
    "CREATE INDEX IF NOT EXISTS idx_reminder_subject ON reminder(subject_id)",
    "CREATE INDEX IF NOT EXISTS idx_appt_clinician ON appointment(clinician_id,start_at)",
    "CREATE INDEX IF NOT EXISTS idx_appt_subject ON appointment(subject_id)",
    "CREATE INDEX IF NOT EXISTS idx_payment_invoice ON payment(invoice_id)",
    "CREATE INDEX IF NOT EXISTS idx_api_audit_resource ON api_audit(resource,item_id,created_at)",
    "CREATE INDEX IF NOT EXISTS idx_chat_thread ON chat_message(owner_hash,thread_id,id)",
    "CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_message(created_at)",
    "CREATE INDEX IF NOT EXISTS auth_tokens_account_purpose ON auth_tokens(account_id,purpose)",
    "CREATE INDEX IF NOT EXISTS idx_national_exchange_status ON national_exchange(country_code,status,created_at)",
    "CREATE INDEX IF NOT EXISTS idx_national_exchange_subject ON national_exchange(country_code,subject_ref,created_at)",
    "CREATE INDEX IF NOT EXISTS idx_chart_enc_subject ON chart_encounter(subject_id,started_at)",
    "CREATE INDEX IF NOT EXISTS idx_chart_note_enc ON chart_note(encounter_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_subject ON clinical_order(subject_id,status)",
    "CREATE INDEX IF NOT EXISTS idx_task_subject ON care_task(subject_id,status)",
    "CREATE INDEX IF NOT EXISTS idx_inbox_thread_subject ON inbox_thread(subject_id)",
    "CREATE INDEX IF NOT EXISTS idx_inbox_msg_thread ON inbox_message(thread_id)",
    "CREATE INDEX IF NOT EXISTS idx_access_audit_actor ON access_audit(actor_email,created_at)",
    "CREATE INDEX IF NOT EXISTS idx_medbackend_connection_email ON medbackend_connection_audit(account_email,tested_at)",
)


def initialize(connection: Connection) -> None:
    identity = "BIGSERIAL PRIMARY KEY" if connection.postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    for statement in _TABLES:
        connection.execute(statement.format(id=identity))
    for role, label, sort_order in (
        ("admin", "Administrator", 10),
        ("doctor", "Doctor", 20),
        ("receptionist", "Receptionist", 30),
        ("billing", "Billing", 40),
        ("patient", "Patient", 50),
    ):
        connection.execute(
            "INSERT INTO access_role(role,label,sort_order) VALUES(?,?,?) "
            "ON CONFLICT(role) DO UPDATE SET label=excluded.label,sort_order=excluded.sort_order",
            (role, label, sort_order),
        )
    for statement in _INDEXES:
        connection.execute(statement)
    connection.commit()
