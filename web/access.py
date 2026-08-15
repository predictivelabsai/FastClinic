"""Persistent, fail-closed RBAC for FastClinic staff and patients."""
from __future__ import annotations

import os
from typing import Iterable

from web import activation_loop as ops

ROLES = ("admin", "practitioner", "receptionist", "billing", "patient")
LEGACY_ROLES = {"doctor": "practitioner"}
DEFAULT_ADMIN_EMAILS = frozenset({
    "kaljuvee@gmail.com",
    "joosep.laats@gmail.com",
    "patrickh217@gmail.com",
    "phil.hermann217@gmail.com",
})

# Nav keys (and a few extra action names) each role may open.
_ROLE_KEYS: dict[str, frozenset[str]] = {
    "admin": frozenset(),  # empty means all
    "practitioner": frozenset({
        "dashboard", "chat-full", "patients", "appointments", "treatments",
        "clinical", "chart", "orders", "tasks", "messages", "act-reminders",
        "act-lapsed", "act-followup", "act-loop", "help-shortcuts",
        "help-guide", "developers", "my-records", "sms", "email",
    }),
    "receptionist": frozenset({
        "dashboard", "patients", "appointments", "tasks",
        "act-reminders", "act-lapsed", "act-followup", "act-loop",
        "help-shortcuts", "help-guide", "my-records", "sms", "email",
    }),
    "billing": frozenset({
        "dashboard", "patients", "billing", "revenue", "help-shortcuts",
        "help-guide",
    }),
    "patient": frozenset({
        "portal", "my-records", "messages", "help-shortcuts", "help-guide",
    }),
}

ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "admin": frozenset({"*"}),
    "practitioner": frozenset({
        "appointments.read.assigned", "appointments.create.any",
        "appointments.change_status", "availability.manage.own",
        "patients.read.assigned", "charts.read.assigned", "charts.write.assigned",
        "messages.read.assigned",
    }),
    "receptionist": frozenset({
        "appointments.read.all", "appointments.create.any", "appointments.reschedule.any",
        "appointments.cancel.any", "availability.read", "patients.read.demographics",
    }),
    "billing": frozenset({"billing.read.all", "billing.write", "patients.read.demographics"}),
    "patient": frozenset({
        "appointments.read.own", "appointments.create.own", "appointments.reschedule.own",
        "appointments.cancel.own", "availability.read", "patients.read.own",
        "charts.read.own", "billing.read.own", "messages.read.own",
    }),
}


def admin_emails() -> frozenset[str]:
    configured = {
        value.strip().lower()
        for value in (os.getenv("FASTCLINIC_ADMIN_EMAILS") or "").split(",")
        if value.strip()
    }
    legacy = (
        os.getenv("FASTCLINIC_ADMIN_EMAIL")
        or os.getenv("MMG_ADMIN_EMAIL")
        or ""
    ).strip().lower()
    if legacy:
        configured.add(legacy)
    return frozenset(DEFAULT_ADMIN_EMAILS | configured)


def admin_email() -> str:
    """Retain the singular helper for older callers."""
    return sorted(admin_emails())[0]


def profile(email: str | None) -> dict:
    """Return ``{email, role, subject_id, clinician_id}``."""
    addr = (email or "").strip().lower()
    if not addr:
        return {"email": "", "role": "patient", "subject_id": None, "clinician_id": None}
    rows = ops.query("SELECT * FROM access_profile WHERE email=?", (addr,))
    if addr in admin_emails():
        row = rows[0] if rows else {}
        return {
            "email": addr, "role": "admin", "subject_id": row.get("subject_id"),
            "clinician_id": row.get("clinician_id"),
        }
    if rows:
        row = rows[0]
        return {
            "email": addr,
            "role": LEGACY_ROLES.get(row["role"], row["role"])
                    if LEGACY_ROLES.get(row["role"], row["role"]) in ROLES else "patient",
            "subject_id": row.get("subject_id"),
            "clinician_id": row.get("clinician_id"),
        }
    return {"email": addr, "role": "patient", "subject_id": None, "clinician_id": None}


def role_of(email: str | None) -> str:
    return profile(email)["role"]


def can(email: str | None, key: str) -> bool:
    role = role_of(email)
    if role == "admin":
        return True
    return key in _ROLE_KEYS.get(role, frozenset())


def effective_role(email: str | None, requested_role: str | None = None) -> str:
    """Return a safe effective role; only administrators may preview roles."""
    actual = role_of(email)
    requested = LEGACY_ROLES.get(requested_role or "", requested_role or "")
    if actual == "admin" and requested in ROLES:
        return requested
    return actual


def can_as(email: str | None, key: str, requested_role: str | None = None) -> bool:
    role = effective_role(email, requested_role)
    return role == "admin" or key in _ROLE_KEYS.get(role, frozenset())


def has_capability(email: str | None, capability: str,
                   requested_role: str | None = None) -> bool:
    capabilities = ROLE_CAPABILITIES.get(effective_role(email, requested_role), frozenset())
    return "*" in capabilities or capability in capabilities


def can_access_subject(email: str | None, subject_id: int,
                       requested_role: str | None = None) -> bool:
    """Fail-closed clinical record scope used in addition to capabilities."""
    role = effective_role(email, requested_role)
    prof = profile(email)
    if role == "admin":
        return True
    if role == "patient":
        return bool(prof.get("subject_id") and prof["subject_id"] == subject_id)
    if role == "practitioner":
        clinician_id = prof.get("clinician_id")
        if not clinician_id:
            return False
        assigned = ops.query(
            "SELECT subject_id FROM appointment WHERE subject_id=? AND clinician_id=? LIMIT 1",
            (subject_id, clinician_id),
        ) or ops.query(
            "SELECT subject_id FROM chart_encounter WHERE subject_id=? AND clinician_id=? LIMIT 1",
            (subject_id, clinician_id),
        )
        return bool(assigned)
    return role in {"receptionist", "billing"}


def assigned_subject_ids(email: str | None) -> frozenset[int]:
    clinician_id = profile(email).get("clinician_id")
    if not clinician_id:
        return frozenset()
    rows = ops.query(
        "SELECT DISTINCT subject_id FROM appointment WHERE clinician_id=? AND subject_id IS NOT NULL "
        "UNION SELECT DISTINCT subject_id FROM chart_encounter WHERE clinician_id=?",
        (clinician_id, clinician_id),
    )
    return frozenset(int(row["subject_id"]) for row in rows)


def allowed_nav_keys(email: str | None, requested_role: str | None = None) -> frozenset[str] | None:
    """None means every nav item is visible (admin)."""
    role = effective_role(email, requested_role)
    if role == "admin":
        return None
    return _ROLE_KEYS.get(role, frozenset())


def home_path(email: str | None, requested_role: str | None = None) -> str:
    return "/portal" if effective_role(email, requested_role) == "patient" else "/"


def set_profile(email: str, role: str, subject_id: int | None = None,
                clinician_id: int | None = None) -> dict:
    role = LEGACY_ROLES.get(role, role)
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    addr = (email or "").strip().lower()
    if not addr:
        raise ValueError("email is required")
    if addr in admin_emails() and role != "admin":
        raise ValueError("configured bootstrap administrators cannot be demoted")
    now = ops._now()
    existing = ops.query("SELECT email FROM access_profile WHERE email=?", (addr,))
    if existing:
        ops.execute(
            "UPDATE access_profile SET role=?, subject_id=?, clinician_id=? WHERE email=?",
            (role, subject_id, clinician_id, addr),
        )
    else:
        ops.execute(
            "INSERT INTO access_profile (email, role, subject_id, clinician_id, created_at) "
            "VALUES (?,?,?,?,?)",
            (addr, role, subject_id, clinician_id, now),
        )
    return profile(addr)


def list_profiles() -> list[dict]:
    rows = {row["email"].lower(): dict(row) for row in ops.query("SELECT * FROM access_profile")}
    for account in ops.query("SELECT email FROM accounts"):
        addr = account["email"].strip().lower()
        rows.setdefault(addr, {
            "email": addr, "role": "patient", "subject_id": None,
            "clinician_id": None, "created_at": "",
        })
    for addr in admin_emails():
        rows[addr] = {
            **rows.get(addr, {"email": addr, "subject_id": None, "clinician_id": None, "created_at": ""}),
            "role": "admin",
        }
    normalized = []
    for row in rows.values():
        normalized.append({**row, **profile(row["email"])})
    return sorted(normalized, key=lambda item: (item["role"], item["email"]))


def audit(email: str | None, action: str, resource: str, item_id="") -> None:
    ops.execute(
        "INSERT INTO access_audit (actor_email, action, resource, item_id, created_at) "
        "VALUES (?,?,?,?,?)",
        ((email or "").strip().lower() or "anonymous", action, resource, str(item_id or ""), ops._now()),
    )


def recent_audit(limit: int = 100) -> list[dict]:
    return ops.query(
        "SELECT * FROM access_audit ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def visible_nav(items: Iterable[tuple], email: str | None,
                requested_role: str | None = None) -> list:
    allowed = allowed_nav_keys(email, requested_role)
    if allowed is None:
        return list(items)
    return [item for item in items if item[0] in allowed]
