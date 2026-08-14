"""Persistent country-adapter sandbox ledger with idempotency/reconciliation."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from web import ops_db


class IdempotencyConflict(ValueError):
    pass


def submit(
    *, country_code: str, surface: str, document_type: str, subject_ref: str,
    practitioner_role_ref: str, payload: dict, idempotency_key: str,
) -> dict:
    country = country_code.strip().upper()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(canonical.encode()).hexdigest()
    now = _now()
    with ops_db.connect() as conn:
        existing = conn.execute(
            "SELECT * FROM national_exchange WHERE country_code=? AND idempotency_key=?",
            (country, idempotency_key),
        ).fetchone()
        if existing:
            row = dict(existing)
            if row["payload_hash"] != payload_hash:
                raise IdempotencyConflict("Idempotency key was already used with a different payload")
            return _decode(row, replay=True)
        exchange_id = str(uuid.uuid4())
        correlation_id = f"{country}-SBX-{uuid.uuid4()}"
        response = {
            "sandbox": True,
            "accepted": True,
            "correlation_id": correlation_id,
            "message": f"Accepted by FastClinic {country} mock transport; not sent to a national system.",
        }
        conn.execute(
            "INSERT INTO national_exchange (id,country_code,idempotency_key,surface,document_type,"
            "subject_ref,practitioner_role_ref,correlation_id,status,payload_hash,request_json,"
            "response_json,error,attempt_count,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (exchange_id, country, idempotency_key, surface, document_type, subject_ref,
             practitioner_role_ref, correlation_id, "accepted", payload_hash, canonical,
             json.dumps(response, sort_keys=True), None, 1, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM national_exchange WHERE id=?", (exchange_id,)).fetchone()
    return _decode(dict(row), replay=False)


def reconcile(exchange_id: str, *, country_code: str) -> dict | None:
    country = country_code.strip().upper()
    with ops_db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM national_exchange WHERE id=? AND country_code=?", (exchange_id, country),
        ).fetchone()
        if not row:
            return None
        current = dict(row)
        response = json.loads(current.get("response_json") or "{}")
        response.update({
            "reconciled": True,
            "reconciled_at": _now(),
            "national_document_id": f"SYNTHETIC-{country}-{current['document_type']}-{exchange_id[:8]}",
        })
        conn.execute(
            "UPDATE national_exchange SET status=?,response_json=?,updated_at=? WHERE id=?",
            ("reconciled", json.dumps(response, sort_keys=True), _now(), exchange_id),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM national_exchange WHERE id=?", (exchange_id,)).fetchone()
    return _decode(dict(updated), replay=False)


def list_exchanges(*, country_code: str, limit: int = 100) -> list[dict]:
    with ops_db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM national_exchange WHERE country_code=? "
            "ORDER BY created_at DESC LIMIT ?", (country_code.strip().upper(), limit),
        ).fetchall()
    return [_decode(dict(row), replay=False) for row in rows]


def _decode(row: dict, *, replay: bool) -> dict:
    row["request"] = json.loads(row.pop("request_json"))
    row["response"] = json.loads(row.pop("response_json") or "null")
    row["idempotent_replay"] = replay
    return row


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
