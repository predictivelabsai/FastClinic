"""Typed FastClinic API: synthetic clinical reads and domain-safe operations.

The public demo contains synthetic data only. Public reads demonstrate the data
model; every mutation and every operational record containing contact details is
gated by ``FASTSME_API_TOKEN``. Domain actions preserve appointment conflicts,
consent suppression, immutable communications, and balanced accounting.
"""

from __future__ import annotations

import os
import secrets
from datetime import date
from typing import Any, Literal

from fastapi import Depends, Header, HTTPException, Query, Response, Security, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field

from web import (
    activation,
    activation_loop,
    api_store,
    appointments,
    billing,
    clinic_queries,
    consent,
    db,
)

from .api_core import (
    DatabaseBackend,
    ErrorEnvelope,
    Resource,
    bearer,
    create_database_api,
    require_write_token,
)


PATIENT_CREATE_FIELDS = (
    "official_name", "gender", "date_of_birth", "date_of_registration",
    "city", "zip_code", "street_address", "street_address_2",
    "country_region", "state", "critical_notes", "remarks", "insurance",
    "insurance_company", "blood_group", "nhs_number",
    "registered_clinician_id", "home_department_id", "private", "external",
)
PARTY_CREATE_FIELDS = ("name", "phone", "email", "city", "zip_code")

RESOURCES = (
    Resource(
        "patients", "subject", "Patients",
        "Synthetic patient demographic and registration records. DELETE archives rather than erases a clinical subject.",
        write_fields=PATIENT_CREATE_FIELDS,
        required_write_fields=("official_name",),
        update_fields=PATIENT_CREATE_FIELDS,
        search_fields=("official_name", "city", "nhs_number", "insurance_company"),
        soft_delete_field="archived",
    ),
    Resource(
        "parties", "party", "Parties",
        "Contactable or billable parties, separated from subjects of care for guardianship, consent, and payer attribution.",
        write_fields=PARTY_CREATE_FIELDS,
        required_write_fields=("name",),
        update_fields=PARTY_CREATE_FIELDS,
        search_fields=("name", "phone", "email", "city"),
    ),
    Resource(
        "consultations", "consultation", "Consultations",
        "Synthetic consultation activity and revenue. Derived/imported records are read-only.",
        search_fields=("consult_at",),
    ),
    Resource(
        "treatments", "item", "Treatments",
        "Billable treatment lines classified by category and specialty. Derived/imported records are read-only.",
        search_fields=("code", "name", "category", "specialty"),
    ),
    Resource(
        "diagnoses", "diagnosis", "Diagnoses",
        "Synthetic diagnosis records linked to consultations. Imported clinical facts are read-only.",
        search_fields=("code", "name", "description", "category"),
    ),
    Resource(
        "notes", "note", "Clinical notes",
        "Synthetic clinical notes. Writes use dedicated validation and archive rather than hard delete.",
        search_fields=("text", "custom_type", "note_at"),
    ),
)


# Used by /developers as a concise human-readable operation catalogue.
API_GROUPS = (
    (
        "Clinical records",
        "Patients, parties, guardians and payers, consultations, diagnoses, treatments, and validated note editing.",
        (
            ("GET POST PATCH DELETE", "/api/v1/patients", "Patient CRUD; DELETE archives", "Public read · token write"),
            ("GET POST PATCH DELETE", "/api/v1/parties", "Party CRUD; linked parties cannot be deleted", "Public read · token write"),
            ("GET POST PATCH DELETE", "/api/v1/relationships", "Guardian, self, payer, family, and emergency roles", "Public read · token write"),
            ("GET", "/api/v1/consultations · /diagnoses · /treatments", "Imported clinical activity", "Public synthetic read"),
            ("GET POST PATCH DELETE", "/api/v1/notes", "Validated note lifecycle; DELETE archives", "Public read · token write"),
        ),
    ),
    (
        "Scheduling",
        "Availability, clinicians, conflict-safe booking, rescheduling, status transitions, and cancellation.",
        (
            ("GET", "/api/v1/clinicians · /availability", "Bookable clinician schedules", "Public read"),
            ("GET POST PATCH DELETE", "/api/v1/appointments", "Conflict-safe appointment lifecycle", "Public read · token write"),
            ("GET POST", "/api/v1/external/*", "FastBooking availability and idempotent reservations", "FastBooking token"),
        ),
    ),
    (
        "Activation & communications",
        "Consent-filtered recall lists, persistent reminders, immutable delivery logs, and outcome attribution.",
        (
            ("GET", "/api/v1/activation/due · /lapsed · /followup", "Consent-filtered activation cohorts", "Token required"),
            ("GET POST PATCH DELETE", "/api/v1/reminders", "Reminder lifecycle; DELETE cancels", "Token required"),
            ("GET POST", "/api/v1/communications", "Consent-gated SMS/email and immutable logs", "Token required"),
            ("GET PATCH", "/api/v1/parties/{id}/marketing-consent", "Marketing opt-out state", "Token required"),
        ),
    ),
    (
        "Billing & ledger",
        "Idempotent invoicing, payments and refunds, voids through reversing journals, and balanced-ledger reporting.",
        (
            ("GET POST PATCH DELETE", "/api/v1/invoices", "Invoice lifecycle; DELETE posts a void reversal", "Token required"),
            ("GET POST DELETE", "/api/v1/payments", "Idempotent receipts; DELETE posts a refund", "Token required"),
            ("GET", "/api/v1/ledger · /trial-balance", "Immutable journal and balances", "Token required"),
        ),
    ),
    (
        "Analytics & audit",
        "The same operational views used by the dashboards, plus an append-only API mutation trail.",
        (
            ("GET", "/api/v1/analytics/*", "Overview, revenue, specialties, procedures, demographics, and clinicians", "Public synthetic read"),
            ("GET", "/api/v1/audit", "Append-only API mutation records", "Token required"),
            ("GET", "/api/v1/health", "Version and write-readiness status", "Public read"),
        ),
    ),
    (
        "FHIR R4 & country adapters",
        "Clinic OS Phase 5a/5b: vanilla R4 projection, UK Core profiles, GP Connect STU3 translation.",
        (
            ("GET", "/api/v1/fhir/metadata", "CapabilityStatement", "Public read"),
            ("GET", "/api/v1/fhir/{type}/{id}", "Single resource read", "Public clinical · token for ops"),
            ("GET", "/api/v1/fhir/Patient/{id}/$everything", "Subject bundle", "Public clinical · token adds ops"),
            ("POST", "/api/v1/fhir/$validate", "Structural validation", "Public"),
            ("POST", "/api/v1/fhir/$import", "Map a resource onto the core", "Token required"),
            ("GET POST", "/api/v1/adapters/GB/*", "NHS Number, UK Core export, STU3, reminders", "Public map · token for ops"),
        ),
    ),
)


backend = DatabaseBackend(db.database_target(), RESOURCES)
api = create_database_api(
    product="FastClinic",
    version="1.3.0",
    description=(
        "Typed integration access across FastClinic's synthetic clinical model, "
        "scheduling, activation, consent, billing, and analytics."
    ),
    base_url="https://fastclinic.dev",
    backend=backend,
    resources=RESOURCES,
    on_mutation=activation_loop.log_api_audit,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RelationshipCreate(StrictModel):
    subject_id: int = Field(gt=0)
    party_id: int = Field(gt=0)
    role: Literal["self", "guardian", "payer", "emergency", "family", "other"]
    is_primary: bool = False


class RelationshipUpdate(StrictModel):
    role: Literal["self", "guardian", "payer", "emergency", "family", "other"] | None = None
    is_primary: bool | None = None


class NoteCreate(StrictModel):
    subject_id: int = Field(gt=0)
    consultation_id: int | None = Field(default=None, gt=0)
    text: str = Field(min_length=1, max_length=20000)
    type: int | None = None
    custom_type: str | None = Field(default=None, max_length=120)
    draft: bool = True
    note_at: str | None = None
    clinician_id: int | None = Field(default=None, gt=0)


class NoteUpdate(StrictModel):
    text: str | None = Field(default=None, min_length=1, max_length=20000)
    type: int | None = None
    custom_type: str | None = Field(default=None, max_length=120)
    draft: bool | None = None
    clinician_id: int | None = Field(default=None, gt=0)
    edit_reason: str | None = Field(default=None, max_length=500)


class AppointmentCreate(StrictModel):
    subject_id: int = Field(gt=0, description="Synthetic patient identifier")
    clinician_id: int = Field(gt=0)
    start_at: str = Field(examples=["2026-08-03 09:00"])
    duration_min: int = Field(default=20, ge=10, le=240)
    reason: str = Field(default="", max_length=500)
    room: str = Field(default="", max_length=120)


class AppointmentUpdate(StrictModel):
    subject_id: int | None = Field(default=None, gt=0)
    clinician_id: int | None = Field(default=None, gt=0)
    start_at: str | None = None
    duration_min: int | None = Field(default=None, ge=10, le=240)
    reason: str | None = Field(default=None, max_length=500)
    room: str | None = Field(default=None, max_length=120)
    status: Literal["scheduled", "confirmed", "cancelled", "completed"] | None = None


class ReminderCreate(StrictModel):
    subject_id: int = Field(gt=0)
    category: str = Field(min_length=1, max_length=120)
    due_date: date | None = None
    sms_text: str | None = Field(default=None, max_length=2000)
    email_subject: str | None = Field(default=None, max_length=300)
    email_text: str | None = Field(default=None, max_length=10000)
    recurring_interval_days: int | None = Field(default=None, ge=1, le=3650)


class ReminderUpdate(StrictModel):
    category: str | None = Field(default=None, min_length=1, max_length=120)
    due_date: date | None = None
    status: Literal["pending", "sent", "cancelled", "failed"] | None = None
    sms_text: str | None = Field(default=None, max_length=2000)
    email_subject: str | None = Field(default=None, max_length=300)
    email_text: str | None = Field(default=None, max_length=10000)
    recurring_interval_days: int | None = Field(default=None, ge=1, le=3650)


class CommunicationCreate(StrictModel):
    channel: Literal["sms", "email"]
    to_addr: str = Field(min_length=3, max_length=320)
    body: str = Field(min_length=1, max_length=10000)
    email_subject: str | None = Field(default=None, min_length=1, max_length=300)
    provider: str = Field(default="", max_length=40)
    reminder_id: int | None = Field(default=None, gt=0)
    allow_duplicate: bool = False


class ConsentUpdate(StrictModel):
    marketing_opt_out: bool


class InvoiceCreate(StrictModel):
    consultation_id: int = Field(gt=0)


class InvoiceUpdate(StrictModel):
    due_date: date


class PaymentCreate(StrictModel):
    invoice_id: int = Field(gt=0)
    amount: float = Field(gt=0)
    method: str = Field(default="", max_length=80)
    reference: str = Field(default="", max_length=160)


class ExternalGuest(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=320)
    phone: str = Field(default="", max_length=40)


class ExternalAppointmentCreate(StrictModel):
    practitioner_id: str
    service_id: str
    starts_at: str
    duration_min: int = Field(default=20, ge=10, le=240)
    guest: ExternalGuest
    notes: str = Field(default="", max_length=2000)


def _problem(status_code: int, code: str, message: str, **details):
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "details": details},
    )


def _domain_error(exc: Exception):
    if isinstance(exc, api_store.NotFound):
        _problem(404, "not_found", str(exc))
    if isinstance(exc, api_store.Conflict):
        _problem(409, "conflict", str(exc))
    raise exc


def _audit(action: str, resource: str, item_id: Any, before=None, after=None) -> None:
    activation_loop.log_api_audit(action, resource, str(item_id), before, after)


def _clinician_exists(clinician_id: int) -> bool:
    return any(row["id"] == clinician_id for row in appointments.clinicians())


# ---------------------------------------------------------- people and notes --
@api.get("/v1/relationships", tags=["Relationships"])
def list_relationships(subject_id: int | None = None, party_id: int | None = None):
    rows = api_store.relationships(subject_id=subject_id, party_id=party_id)
    return {"data": rows, "meta": {"total": len(rows)}}


@api.get("/v1/relationships/{subject_id}/{party_id}/{role}", tags=["Relationships"])
def get_relationship(subject_id: int, party_id: int, role: str):
    row = api_store.relationship(subject_id, party_id, role)
    if not row:
        _problem(404, "not_found", "Relationship was not found")
    return row


@api.post("/v1/relationships", status_code=201, dependencies=[Depends(require_write_token)], tags=["Relationships"])
def create_relationship(payload: RelationshipCreate):
    try:
        row = api_store.create_relationship(**payload.model_dump())
    except (api_store.NotFound, api_store.Conflict) as exc:
        _domain_error(exc)
    _audit("create", "relationships", f"{payload.subject_id}:{payload.party_id}:{payload.role}", None, row)
    return row


@api.patch("/v1/relationships/{subject_id}/{party_id}/{role}", dependencies=[Depends(require_write_token)], tags=["Relationships"])
def patch_relationship(subject_id: int, party_id: int, role: str, payload: RelationshipUpdate):
    values = payload.model_dump(exclude_unset=True)
    if "role" in values:
        values["new_role"] = values.pop("role")
    try:
        before, after = api_store.update_relationship(
            subject_id, party_id, role, **values
        )
    except (api_store.NotFound, api_store.Conflict) as exc:
        _domain_error(exc)
    _audit("update", "relationships", f"{subject_id}:{party_id}:{role}", before, after)
    return after


@api.delete("/v1/relationships/{subject_id}/{party_id}/{role}", status_code=204, dependencies=[Depends(require_write_token)], tags=["Relationships"])
def remove_relationship(subject_id: int, party_id: int, role: str):
    try:
        before = api_store.delete_relationship(subject_id, party_id, role)
    except (api_store.NotFound, api_store.Conflict) as exc:
        _domain_error(exc)
    _audit("delete", "relationships", f"{subject_id}:{party_id}:{role}", before, None)
    return Response(status_code=204)


@api.delete("/v1/parties/{item_id}", status_code=204, dependencies=[Depends(require_write_token)], tags=["Parties"])
def delete_party(item_id: int):
    try:
        before = api_store.delete_unlinked_party(item_id)
    except (api_store.NotFound, api_store.Conflict) as exc:
        _domain_error(exc)
    _audit("delete", "parties", item_id, before, None)
    return Response(status_code=204)


@api.post("/v1/notes", status_code=201, dependencies=[Depends(require_write_token)], tags=["Clinical notes"])
def create_note(payload: NoteCreate):
    try:
        row = api_store.create_note(payload.model_dump())
    except (api_store.NotFound, api_store.Conflict) as exc:
        _domain_error(exc)
    _audit("create", "notes", row.get("id"), None, row)
    return row


@api.patch("/v1/notes/{item_id}", dependencies=[Depends(require_write_token)], tags=["Clinical notes"])
def patch_note(item_id: int, payload: NoteUpdate):
    try:
        before, after = api_store.update_note(item_id, payload.model_dump(exclude_unset=True))
    except (api_store.NotFound, api_store.Conflict) as exc:
        _domain_error(exc)
    _audit("update", "notes", item_id, before, after)
    return after


@api.delete("/v1/notes/{item_id}", status_code=204, dependencies=[Depends(require_write_token)], tags=["Clinical notes"])
def delete_note(item_id: int):
    try:
        before, after = api_store.archive_note(item_id)
    except (api_store.NotFound, api_store.Conflict) as exc:
        _domain_error(exc)
    _audit("archive", "notes", item_id, before, after)
    return Response(status_code=204)


@api.get("/v1/parties/{party_id}/marketing-consent", dependencies=[Depends(require_write_token)], tags=["Consent"])
def get_marketing_consent(party_id: int):
    rows = db.query("SELECT id, marketing_opt_out FROM party WHERE id=?", (party_id,))
    if not rows:
        _problem(404, "not_found", "Party was not found", id=party_id)
    return {"party_id": party_id, "marketing_opt_out": bool(rows[0]["marketing_opt_out"])}


@api.patch("/v1/parties/{party_id}/marketing-consent", dependencies=[Depends(require_write_token)], tags=["Consent"])
def patch_marketing_consent(party_id: int, payload: ConsentUpdate):
    try:
        before, after = api_store.set_marketing_opt_out(party_id, payload.marketing_opt_out)
    except api_store.NotFound as exc:
        _domain_error(exc)
    _audit("consent", "parties", party_id, before, after)
    return {"party_id": party_id, "marketing_opt_out": bool(after["marketing_opt_out"])}


# --------------------------------------------------------------- scheduling --
@api.get("/v1/clinicians", tags=["Appointments"])
def list_clinicians():
    rows = appointments.clinicians()
    return {"data": rows, "meta": {"total": len(rows)}}


@api.get("/v1/availability", tags=["Appointments"])
def availability(clinician_id: int = Query(gt=0), day: date = Query()):
    return {
        "clinician_id": clinician_id,
        "day": day.isoformat(),
        "slots": [
            {"starts_at": row["start_at"], "duration_min": appointments.SLOT_MIN}
            for row in appointments.day_schedule(clinician_id, day)
            if row["free"]
        ],
    }


@api.get("/v1/appointments", tags=["Appointments"])
def list_appointments(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    clinician_id: int | None = Query(default=None, gt=0),
    subject_id: int | None = Query(default=None, gt=0),
    day: date | None = None,
    appointment_status: Literal["scheduled", "confirmed", "cancelled", "completed"] | None = Query(default=None, alias="status"),
):
    where, params = ["1=1"], []
    for field, value in (("clinician_id", clinician_id), ("subject_id", subject_id), ("status", appointment_status)):
        if value is not None:
            where.append(f"{field}=?")
            params.append(value)
    if day is not None:
        where.append("substr(start_at,1,10)=?")
        params.append(day.isoformat())
    clause = " AND ".join(where)
    total = activation_loop.query(f"SELECT COUNT(*) AS n FROM appointment WHERE {clause}", tuple(params))[0]["n"]
    rows = activation_loop.query(
        f"SELECT * FROM appointment WHERE {clause} ORDER BY start_at LIMIT ? OFFSET ?",
        (*params, limit, offset),
    )
    return {"data": rows, "meta": {"total": total, "limit": limit, "offset": offset}}


@api.get("/v1/appointments/{appointment_id}", tags=["Appointments"])
def get_appointment(appointment_id: int):
    row = appointments.get(appointment_id)
    if not row:
        _problem(404, "not_found", "Appointment was not found", id=appointment_id)
    return row


@api.post("/v1/appointments", status_code=201, dependencies=[Depends(require_write_token)], tags=["Appointments"])
def create_appointment(payload: AppointmentCreate):
    if not db.query_one("SELECT id FROM subject WHERE id=?", (payload.subject_id,)):
        _problem(404, "patient_not_found", "Patient was not found", id=payload.subject_id)
    if not _clinician_exists(payload.clinician_id):
        _problem(404, "clinician_not_found", "Clinician was not found", id=payload.clinician_id)
    try:
        appointment_id = appointments.book(**payload.model_dump())
    except (ValueError, appointments.SlotTaken) as exc:
        _problem(409, "slot_taken", str(exc))
    row = appointments.get(appointment_id) or {}
    _audit("create", "appointments", appointment_id, None, row)
    return row


@api.patch("/v1/appointments/{appointment_id}", dependencies=[Depends(require_write_token)], tags=["Appointments"])
def patch_appointment(appointment_id: int, payload: AppointmentUpdate):
    before = appointments.get(appointment_id)
    if not before:
        _problem(404, "not_found", "Appointment was not found", id=appointment_id)
    if payload.subject_id is not None and not db.query_one(
        "SELECT id FROM subject WHERE id=?", (payload.subject_id,)
    ):
        _problem(404, "patient_not_found", "Patient was not found", id=payload.subject_id)
    if payload.clinician_id is not None and not _clinician_exists(payload.clinician_id):
        _problem(404, "clinician_not_found", "Clinician was not found", id=payload.clinician_id)
    try:
        after = appointments.update(appointment_id, **payload.model_dump(exclude_unset=True))
    except appointments.SlotTaken as exc:
        _problem(409, "slot_taken", str(exc))
    except ValueError as exc:
        _problem(422, "invalid_appointment", str(exc))
    _audit("update", "appointments", appointment_id, before, after)
    return after


@api.delete("/v1/appointments/{appointment_id}", status_code=204, dependencies=[Depends(require_write_token)], tags=["Appointments"])
def cancel_appointment(appointment_id: int):
    before = appointments.get(appointment_id)
    if not before:
        _problem(404, "not_found", "Appointment was not found", id=appointment_id)
    after = appointments.update(appointment_id, status="cancelled")
    _audit("cancel", "appointments", appointment_id, before, after)
    return Response(status_code=204)


# ------------------------------------------------ activation and messaging --
@api.get("/v1/activation/due", dependencies=[Depends(require_write_token)], tags=["Activation"])
def due_activation(category: str = "all"):
    rows = activation.due_rows(category)
    return {"data": rows, "meta": {"total": len(rows), "category": category}}


@api.get("/v1/activation/lapsed", dependencies=[Depends(require_write_token)], tags=["Activation"])
def lapsed_activation(months: int = Query(default=12, ge=1, le=120)):
    rows = activation.lapsed_rows(months)
    return {"data": rows, "meta": {"total": len(rows), "months": months}}


@api.get("/v1/activation/followup", dependencies=[Depends(require_write_token)], tags=["Activation"])
def followup_activation(days: int = Query(default=14, ge=1, le=365)):
    rows = activation.followup_rows(days)
    return {"data": rows, "meta": {"total": len(rows), "days": days}}


@api.get("/v1/activation/attribution", dependencies=[Depends(require_write_token)], tags=["Activation"])
def activation_attribution(days: int = Query(default=30, ge=1, le=365)):
    return activation_loop.attribution(days)


@api.get("/v1/reminders", dependencies=[Depends(require_write_token)], tags=["Reminders"])
def list_reminders(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    reminder_status: Literal["pending", "sent", "cancelled", "failed"] | None = Query(default=None, alias="status"),
    subject_id: int | None = Query(default=None, gt=0),
):
    where, params = ["1=1"], []
    if reminder_status:
        where.append("status=?")
        params.append(reminder_status)
    if subject_id:
        where.append("subject_id=?")
        params.append(subject_id)
    clause = " AND ".join(where)
    total = activation_loop.query(f"SELECT COUNT(*) AS n FROM reminder WHERE {clause}", tuple(params))[0]["n"]
    rows = activation_loop.query(
        f"SELECT * FROM reminder WHERE {clause} ORDER BY due_date, id LIMIT ? OFFSET ?",
        (*params, limit, offset),
    )
    return {"data": rows, "meta": {"total": total, "limit": limit, "offset": offset}}


@api.get("/v1/reminders/{reminder_id}", dependencies=[Depends(require_write_token)], tags=["Reminders"])
def get_reminder(reminder_id: int):
    row = activation_loop.get_reminder(reminder_id)
    if not row:
        _problem(404, "not_found", "Reminder was not found", id=reminder_id)
    return row


@api.post("/v1/reminders", status_code=201, dependencies=[Depends(require_write_token)], tags=["Reminders"])
def create_reminder(payload: ReminderCreate):
    if not db.query_one("SELECT id FROM subject WHERE id=?", (payload.subject_id,)):
        _problem(404, "patient_not_found", "Patient was not found", id=payload.subject_id)
    values = payload.model_dump()
    values["due_date"] = values["due_date"].isoformat() if values["due_date"] else None
    reminder_id = activation_loop.create_reminder(**values)
    row = activation_loop.get_reminder(reminder_id) or {}
    _audit("create", "reminders", reminder_id, None, row)
    return row


@api.patch("/v1/reminders/{reminder_id}", dependencies=[Depends(require_write_token)], tags=["Reminders"])
def patch_reminder(reminder_id: int, payload: ReminderUpdate):
    values = payload.model_dump(exclude_unset=True)
    if isinstance(values.get("due_date"), date):
        values["due_date"] = values["due_date"].isoformat()
    try:
        changed = activation_loop.update_reminder(reminder_id, values)
    except ValueError as exc:
        _problem(422, "invalid_reminder", str(exc))
    if not changed:
        _problem(404, "not_found", "Reminder was not found", id=reminder_id)
    before, after = changed
    _audit("update", "reminders", reminder_id, before, after)
    return after


@api.delete("/v1/reminders/{reminder_id}", status_code=204, dependencies=[Depends(require_write_token)], tags=["Reminders"])
def delete_reminder(reminder_id: int):
    changed = activation_loop.cancel_reminder(reminder_id)
    if not changed:
        _problem(404, "not_found", "Reminder was not found", id=reminder_id)
    before, after = changed
    _audit("cancel", "reminders", reminder_id, before, after)
    return Response(status_code=204)


@api.get("/v1/communications", dependencies=[Depends(require_write_token)], tags=["Communications"])
def list_communications(limit: int = Query(default=100, ge=1, le=500)):
    rows = activation_loop.recent_communications(limit)
    return {"data": rows, "meta": {"total": len(rows), "limit": limit}}


@api.get("/v1/communications/{communication_id}", dependencies=[Depends(require_write_token)], tags=["Communications"])
def get_communication(communication_id: int):
    row = activation_loop.get_communication(communication_id)
    if not row:
        _problem(404, "not_found", "Communication was not found", id=communication_id)
    return row


@api.post("/v1/communications", status_code=201, dependencies=[Depends(require_write_token)], tags=["Communications"])
def send_communication(payload: CommunicationCreate):
    reminder = activation_loop.get_reminder(payload.reminder_id) if payload.reminder_id else None
    if payload.reminder_id and not reminder:
        _problem(404, "reminder_not_found", "Reminder was not found", id=payload.reminder_id)
    if payload.channel == "sms":
        party_id, subject_id = activation_loop.resolve_by_phone(payload.to_addr)
        blocked = consent.check_phone(payload.to_addr)
    else:
        party_id, subject_id = activation_loop.resolve_by_email(payload.to_addr)
        blocked = consent.check_email(payload.to_addr)
    if reminder:
        subject_id = reminder.get("subject_id") or subject_id
        if not payload.allow_duplicate and activation_loop.already_contacted(
            subject_id, reminder.get("category") or ""
        ):
            _problem(409, "duplicate_suppressed", "This patient was contacted recently for the same purpose")
    if blocked:
        communication_id = activation_loop.log_communication(
            channel=payload.channel, to_addr=payload.to_addr, body=payload.body,
            status="blocked", subject_id=subject_id, party_id=party_id,
            reminder_id=payload.reminder_id, provider=payload.provider,
            error="opted_out",
        )
        row = activation_loop.get_communication(communication_id)
        _audit("blocked", "communications", communication_id, None, row)
        _problem(409, "marketing_opt_out", blocked, communication_id=communication_id)
    if payload.channel == "sms":
        from util.sms import send
        provider = payload.provider or "twilio"
        result = send(payload.to_addr, payload.body, provider)
    else:
        from util.email import send
        if not payload.email_subject:
            _problem(422, "email_subject_required", "email_subject is required for email")
        result = send(payload.to_addr, payload.email_subject, payload.body)
        provider = "postmark"
    communication_id = activation_loop.log_communication(
        channel=payload.channel, to_addr=payload.to_addr, body=payload.body,
        status="sent" if result.ok else "failed", subject_id=subject_id,
        party_id=party_id, reminder_id=payload.reminder_id, provider=provider,
        provider_message_id=result.message_id or "", error=result.error or "",
    )
    row = activation_loop.get_communication(communication_id) or {}
    _audit("send" if result.ok else "failed", "communications", communication_id, None, row)
    if not result.ok:
        _problem(502, "provider_error", "The provider did not accept the message", communication_id=communication_id, provider=provider)
    if payload.reminder_id:
        activation_loop.mark_sent(payload.reminder_id)
    return row


# --------------------------------------------------------- billing and audit --
@api.get("/v1/invoices", dependencies=[Depends(require_write_token)], tags=["Billing"])
def list_invoices(limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    total = activation_loop.query("SELECT COUNT(*) AS n FROM invoice")[0]["n"]
    rows = activation_loop.query("SELECT * FROM invoice ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
    return {"data": rows, "meta": {"total": total, "limit": limit, "offset": offset}}


@api.get("/v1/invoices/{invoice_id}", dependencies=[Depends(require_write_token)], tags=["Billing"])
def get_invoice(invoice_id: int):
    row = billing.invoice(invoice_id)
    if not row:
        _problem(404, "not_found", "Invoice was not found", id=invoice_id)
    return row


@api.post("/v1/invoices", status_code=201, dependencies=[Depends(require_write_token)], tags=["Billing"])
def create_invoice(payload: InvoiceCreate):
    consultation = db.query_one("SELECT * FROM consultation WHERE id=?", (payload.consultation_id,))
    if not consultation:
        _problem(404, "consultation_not_found", "Consultation was not found", id=payload.consultation_id)
    existing = activation_loop.query("SELECT * FROM invoice WHERE consultation_id=?", (payload.consultation_id,))
    if existing:
        _problem(409, "invoice_exists", "The consultation is already invoiced", invoice_id=existing[0]["id"])
    if not consultation.get("revenue_vat"):
        _problem(422, "zero_value_consultation", "A zero-value consultation cannot be invoiced")
    invoice_id = billing.raise_invoice(payload.consultation_id)
    row = billing.invoice(invoice_id) if invoice_id else None
    if not row:
        _problem(409, "invoice_not_created", "The invoice could not be created")
    _audit("create", "invoices", invoice_id, None, row)
    return row


@api.patch("/v1/invoices/{invoice_id}", dependencies=[Depends(require_write_token)], tags=["Billing"])
def patch_invoice(invoice_id: int, payload: InvoiceUpdate):
    try:
        changed = billing.update_invoice_due_date(invoice_id, payload.due_date.isoformat())
    except ValueError as exc:
        _problem(409, "invoice_locked", str(exc))
    if not changed:
        _problem(404, "not_found", "Invoice was not found", id=invoice_id)
    before, after = changed
    _audit("update", "invoices", invoice_id, before, after)
    return after


@api.delete("/v1/invoices/{invoice_id}", status_code=204, dependencies=[Depends(require_write_token)], tags=["Billing"])
def delete_invoice(invoice_id: int):
    before = billing.invoice(invoice_id)
    if not before:
        _problem(404, "not_found", "Invoice was not found", id=invoice_id)
    if not billing.void_invoice(invoice_id):
        _problem(409, "invoice_locked", "Invoice is already void")
    after = billing.invoice(invoice_id)
    _audit("void", "invoices", invoice_id, before, after)
    return Response(status_code=204)


@api.get("/v1/payments", dependencies=[Depends(require_write_token)], tags=["Billing"])
def list_payments(limit: int = Query(default=100, ge=1, le=500), invoice_id: int | None = Query(default=None, gt=0)):
    rows = billing.payments(limit, invoice_id)
    return {"data": rows, "meta": {"total": len(rows), "limit": limit}}


@api.get("/v1/payments/{payment_id}", dependencies=[Depends(require_write_token)], tags=["Billing"])
def get_payment(payment_id: int):
    row = billing.payment(payment_id)
    if not row:
        _problem(404, "not_found", "Payment was not found", id=payment_id)
    return row


@api.post("/v1/payments", status_code=201, dependencies=[Depends(require_write_token)], tags=["Billing"])
def create_payment(payload: PaymentCreate, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200)):
    existing = activation_loop.query("SELECT * FROM payment WHERE idempotency_key=?", (idempotency_key,))
    if existing:
        prior = existing[0]
        if (
            prior["invoice_id"] != payload.invoice_id
            or abs(prior["amount"] - payload.amount) >= 0.005
            or (prior.get("method") or "") != payload.method
            or (prior.get("reference") or "") != payload.reference
        ):
            _problem(409, "idempotency_conflict", "Idempotency-Key was already used with a different payment")
        return existing[0]
    invoice = billing.invoice(payload.invoice_id)
    if not invoice:
        _problem(404, "invoice_not_found", "Invoice was not found", id=payload.invoice_id)
    outstanding = round(invoice["total"] - invoice["paid"], 2)
    if payload.amount > outstanding + 0.005:
        _problem(409, "overpayment", "Payment exceeds the invoice balance", outstanding=outstanding)
    if not billing.record_payment(**payload.model_dump(), idempotency_key=idempotency_key):
        _problem(409, "payment_rejected", "The invoice cannot accept this payment")
    row = activation_loop.query("SELECT * FROM payment WHERE idempotency_key=?", (idempotency_key,))[0]
    _audit("create", "payments", row["id"], None, row)
    return row


@api.delete("/v1/payments/{payment_id}", dependencies=[Depends(require_write_token)], tags=["Billing"])
def delete_payment(payment_id: int):
    before = billing.payment(payment_id)
    if not before:
        _problem(404, "not_found", "Payment was not found", id=payment_id)
    if not billing.refund_payment(payment_id):
        _problem(409, "payment_locked", "Payment is already reversed or cannot be refunded")
    after = billing.payment(payment_id)
    _audit("refund", "payments", payment_id, before, after)
    return after


@api.get("/v1/ledger", dependencies=[Depends(require_write_token)], tags=["Billing"])
def ledger(limit: int = Query(default=200, ge=1, le=1000), offset: int = Query(default=0, ge=0)):
    total = activation_loop.query("SELECT COUNT(*) AS n FROM gl_entry")[0]["n"]
    rows = activation_loop.query("SELECT * FROM gl_entry ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
    return {"data": rows, "meta": {"total": total, "limit": limit, "offset": offset, "balanced": billing.gl_balanced()}}


@api.get("/v1/trial-balance", dependencies=[Depends(require_write_token)], tags=["Billing"])
def trial_balance():
    return {"data": billing.trial_balance(), "balanced": billing.gl_balanced()}


@api.get("/v1/audit", dependencies=[Depends(require_write_token)], tags=["Audit"])
def audit_log(limit: int = Query(default=100, ge=1, le=500), resource: str = ""):
    rows = activation_loop.api_audit(limit, resource)
    return {"data": rows, "meta": {"total": len(rows), "limit": limit}}


# ---------------------------------------------------------------- analytics --
@api.get("/v1/analytics/overview", tags=["Analytics"])
def analytics_overview():
    return clinic_queries.overview_kpis()


@api.get("/v1/analytics/monthly", tags=["Analytics"])
def analytics_monthly(months: int = Query(default=18, ge=1, le=120)):
    return {"data": clinic_queries.monthly_trend(months), "meta": {"months": months}}


@api.get("/v1/analytics/revenue-by-category", tags=["Analytics"])
def analytics_revenue_by_category():
    return {"data": clinic_queries.revenue_by_category()}


@api.get("/v1/analytics/demographics", tags=["Analytics"])
def analytics_demographics():
    return {"data": clinic_queries.demographics_mix()}


@api.get("/v1/analytics/specialties", tags=["Analytics"])
def analytics_specialties():
    return {"data": clinic_queries.specialty_mix()}


@api.get("/v1/analytics/categories", tags=["Analytics"])
def analytics_categories():
    return {"data": clinic_queries.category_mix()}


@api.get("/v1/analytics/procedures", tags=["Analytics"])
def analytics_procedures(limit: int = Query(default=15, ge=1, le=100), specialty: str = ""):
    return {"data": clinic_queries.top_procedures(limit, specialty)}


@api.get("/v1/analytics/clinicians", tags=["Analytics"])
def analytics_clinicians():
    return {"data": clinic_queries.clinician_activity()}


# --------------------------------------------------------- FastBooking bridge --
def require_fastbooking_token(authorization: str | None = Header(default=None)) -> None:
    configured = os.getenv("FASTBOOKING_API_TOKEN", "")
    if not configured:
        _problem(503, "integration_disabled", "FastBooking integration is not configured")
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(configured, supplied):
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "A valid FastBooking bearer token is required", "details": {}},
            headers={"WWW-Authenticate": "Bearer"},
        )


@api.get("/v1/external/availability", dependencies=[Depends(require_fastbooking_token)], tags=["External booking"])
def external_availability(practitioner_id: int, day: date = Query()):
    if not _clinician_exists(practitioner_id):
        _problem(404, "clinician_not_found", "Clinician was not found", id=practitioner_id)
    return availability(practitioner_id, day)


@api.post("/v1/external/appointments", status_code=201, dependencies=[Depends(require_fastbooking_token)], tags=["External booking"])
def create_external_appointment(payload: ExternalAppointmentCreate, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8)):
    existing = activation_loop.external_booking(idempotency_key)
    if existing:
        return existing
    try:
        clinician_id = int(payload.practitioner_id)
        if not _clinician_exists(clinician_id):
            _problem(404, "clinician_not_found", "Clinician was not found", id=clinician_id)
        appointment_id = appointments.book(
            None, clinician_id, payload.starts_at,
            duration_min=payload.duration_min,
            reason=payload.notes or payload.service_id,
            with_reminder=False,
        )
    except (TypeError, ValueError):
        _problem(400, "invalid_practitioner", "Practitioner identifier must be numeric")
    except appointments.SlotTaken as exc:
        _problem(409, "slot_taken", str(exc))
    return activation_loop.create_external_booking(
        idempotency_key=idempotency_key,
        appointment_id=appointment_id,
        guest_name=payload.guest.name,
        guest_email=payload.guest.email,
        guest_phone=payload.guest.phone,
        service_id=payload.service_id,
    )


@api.post("/v1/external/appointments/{appointment_id}/cancel", dependencies=[Depends(require_fastbooking_token)], tags=["External booking"])
def cancel_external_appointment(appointment_id: int):
    cancelled = activation_loop.cancel_external_booking(appointment_id)
    if not cancelled:
        _problem(404, "appointment_not_found", "External appointment was not found")
    return cancelled


# ----------------------------------------------------------- FHIR R4 (Phase 5a) --
class FhirResource(StrictModel):
    model_config = ConfigDict(extra="allow")
    resourceType: str = Field(min_length=1, max_length=80)


class NhsIdentifierIn(StrictModel):
    value: str = Field(min_length=1, max_length=32)


def _token_ok(credentials: HTTPAuthorizationCredentials | None) -> bool:
    configured = os.getenv("FASTSME_API_TOKEN", "")
    if not configured or not credentials:
        return False
    return secrets.compare_digest(configured, credentials.credentials or "")


@api.get("/v1/fhir/metadata", tags=["FHIR"])
def fhir_metadata():
    from web import fhir
    return fhir.capability_statement()


@api.get("/v1/fhir/Patient/{subject_id}/$everything", tags=["FHIR"])
def fhir_patient_everything(
    subject_id: int,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer),
):
    from web import fhir
    try:
        return fhir.bundle_subject(subject_id, include_ops=_token_ok(credentials))
    except fhir.NotFound as exc:
        _problem(404, "not_found", str(exc))


@api.get("/v1/fhir/{resource_type}/{resource_id}", tags=["FHIR"])
def fhir_read(
    resource_type: str,
    resource_id: str,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer),
):
    from web import fhir
    try:
        return fhir.export_resource(
            resource_type, resource_id, include_ops=_token_ok(credentials),
        )
    except fhir.NotFound as exc:
        _problem(404, "not_found", str(exc))


@api.post("/v1/fhir/$validate", tags=["FHIR"])
def fhir_validate(payload: FhirResource):
    from web import fhir
    return fhir.validate_resource(payload.model_dump())


@api.post("/v1/fhir/$import", dependencies=[Depends(require_write_token)], tags=["FHIR"])
def fhir_import(payload: FhirResource):
    from web import fhir
    mapped = fhir.import_resource(payload.model_dump())
    _audit("import", "fhir", payload.resourceType, None, {"id": payload.model_dump().get("id")})
    return mapped


# ----------------------------------------------------- NHS adapter (Phase 5b) --
@api.get("/v1/adapters/GB/status", tags=["NHS adapter"])
def nhs_status():
    from web.adapters.registry import get_adapter
    return get_adapter("GB").status()


@api.post("/v1/adapters/GB/verify-identifier", tags=["NHS adapter"])
def nhs_verify_identifier(payload: NhsIdentifierIn):
    from web.adapters.registry import get_adapter
    return get_adapter("GB").verify_identifier(payload.value)


@api.get("/v1/adapters/GB/subjects/{subject_id}", tags=["NHS adapter"])
def nhs_export_subject(
    subject_id: int,
    release: str = Query(default="r4", pattern="^(r4|stu3|gpc|gpconnect)$"),
):
    from web.adapters.base import AdapterNotAvailable
    from web.adapters.registry import get_adapter
    from web import fhir
    try:
        resources = get_adapter("GB").export_subject(subject_id, release=release)
    except fhir.NotFound as exc:
        _problem(404, "not_found", str(exc))
    except AdapterNotAvailable as exc:
        _problem(503, "adapter_unavailable", str(exc))
    from web.fhir.assemble import as_bundle
    return as_bundle(resources)


@api.post("/v1/adapters/GB/import", dependencies=[Depends(require_write_token)], tags=["NHS adapter"])
def nhs_import(payload: FhirResource):
    from web.adapters.registry import get_adapter
    mapped = get_adapter("GB").import_record(payload.model_dump())
    _audit("import", "nhs", payload.resourceType, None, {"id": payload.model_dump().get("id")})
    return mapped


@api.get("/v1/adapters/GB/reminders/{reminder_id}", dependencies=[Depends(require_write_token)], tags=["NHS adapter"])
def nhs_push_reminder(reminder_id: int):
    from web.adapters.base import AdapterNotAvailable
    from web.adapters.registry import get_adapter
    try:
        return get_adapter("GB").push_reminder(reminder_id)
    except AdapterNotAvailable as exc:
        _problem(404, "not_found", str(exc))

