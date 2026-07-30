"""FastClinic public synthetic reads and token-gated appointment writes."""

from datetime import date

from fastapi import Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from web import appointments
from web import activation_loop
from web import db

from .api_core import (
    Resource,
    SQLiteBackend,
    create_sqlite_api,
    require_write_token,
)

RESOURCES = (
    Resource("patients", "subject", "Patients", "Synthetic patient demographic and registration records.", search_fields=("official_name", "city", "nhs_number", "insurance_company")),
    Resource("consultations", "consultation", "Consultations", "Synthetic consultation activity and revenue.", search_fields=("consult_at",)),
    Resource("treatments", "item", "Treatments", "Billable treatment lines classified by category and specialty.", search_fields=("code", "name", "category", "specialty")),
    Resource("diagnoses", "diagnosis", "Diagnoses", "Synthetic diagnosis records linked to consultations.", search_fields=("code", "name", "description", "category")),
)

backend = SQLiteBackend(db.DB_PATH, RESOURCES)
api = create_sqlite_api(
    product="FastClinic", version="1.0.0",
    description="Open integration access to FastClinic's entirely synthetic clinical demo data.",
    base_url="https://clinic.fastsme.com", backend=backend, resources=RESOURCES,
)


class AppointmentCreate(BaseModel):
    subject_id: int = Field(description="Synthetic patient identifier")
    clinician_id: int
    start_at: str = Field(examples=["2026-08-03 09:00"])
    duration_min: int = Field(default=20, ge=10, le=240)
    reason: str = ""
    room: str = ""


class ExternalGuest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=320)
    phone: str = Field(default="", max_length=40)


class ExternalAppointmentCreate(BaseModel):
    practitioner_id: str
    service_id: str
    starts_at: str
    duration_min: int = Field(default=20, ge=10, le=240)
    guest: ExternalGuest
    notes: str = Field(default="", max_length=2000)


@api.get("/v1/appointments", tags=["Appointments"])
def list_appointments(limit: int = 50, offset: int = 0):
    """List operational appointment records."""

    rows = activation_loop.query(
        "SELECT * FROM appointment ORDER BY start_at LIMIT ? OFFSET ?",
        (min(max(limit, 1), 200), max(offset, 0)),
    )
    return {"data": rows, "meta": {"limit": limit, "offset": offset}}


@api.post(
    "/v1/appointments",
    status_code=201,
    dependencies=[Depends(require_write_token)],
    tags=["Appointments"],
)
def create_appointment(payload: AppointmentCreate):
    """Book a synthetic appointment after bearer-token authentication."""

    try:
        appointment_id = appointments.book(
            payload.subject_id,
            payload.clinician_id,
            payload.start_at,
            duration_min=payload.duration_min,
            reason=payload.reason,
            room=payload.room,
        )
    except appointments.SlotTaken as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "slot_taken", "message": str(exc), "details": {}},
        ) from exc
    return activation_loop.query(
        "SELECT * FROM appointment WHERE id=?", (appointment_id,)
    )[0]


@api.get(
    "/v1/external/availability",
    dependencies=[Depends(require_write_token)],
    tags=["External booking"],
)
def external_availability(
    practitioner_id: int,
    day: date = Query(),
):
    """Return bookable slots without exposing patient or clinical data."""

    return {
        "practitioner_id": practitioner_id,
        "day": day.isoformat(),
        "slots": [
            {
                "starts_at": row["start_at"],
                "duration_min": appointments.SLOT_MIN,
            }
            for row in appointments.day_schedule(practitioner_id, day)
            if row["free"]
        ],
    }


@api.post(
    "/v1/external/appointments",
    status_code=201,
    dependencies=[Depends(require_write_token)],
    tags=["External booking"],
)
def create_external_appointment(
    payload: ExternalAppointmentCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8),
):
    """Reserve an operational appointment for FastBooking.

    Guest contact data is scheduling-only operational data. This endpoint does
    not create a clinical record, consultation, diagnosis, or treatment.
    """

    existing = activation_loop.external_booking(idempotency_key)
    if existing:
        return existing
    try:
        clinician_id = int(payload.practitioner_id)
        appointment_id = appointments.book(
            None,
            clinician_id,
            payload.starts_at,
            duration_min=payload.duration_min,
            reason=payload.notes or payload.service_id,
            with_reminder=False,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_practitioner",
                "message": "Practitioner identifier must be numeric.",
                "details": {},
            },
        ) from exc
    except appointments.SlotTaken as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "slot_taken", "message": str(exc), "details": {}},
        ) from exc
    return activation_loop.create_external_booking(
        idempotency_key=idempotency_key,
        appointment_id=appointment_id,
        guest_name=payload.guest.name,
        guest_email=payload.guest.email,
        guest_phone=payload.guest.phone,
        service_id=payload.service_id,
    )


@api.post(
    "/v1/external/appointments/{appointment_id}/cancel",
    dependencies=[Depends(require_write_token)],
    tags=["External booking"],
)
def cancel_external_appointment(appointment_id: int):
    """Cancel an externally-created appointment and release its slot."""

    cancelled = activation_loop.cancel_external_booking(appointment_id)
    if not cancelled:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "appointment_not_found",
                "message": "External appointment not found.",
                "details": {},
            },
        )
    return cancelled
