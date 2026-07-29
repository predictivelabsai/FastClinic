"""FastClinic public synthetic reads and token-gated appointment writes."""

from fastapi import Depends, HTTPException
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
