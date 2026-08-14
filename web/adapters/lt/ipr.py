"""National IPR appointment sandbox projection."""
from __future__ import annotations


def appointment_message(fixture: dict) -> dict:
    appointment = fixture["appointment"]
    return {
        "surface": "IPR",
        "mode": "sandbox",
        "not_production_conformant": True,
        "appointment_id": appointment["id"],
        "status": appointment["status"],
        "start": appointment["start"],
        "end": appointment["end"],
        "patient_ref": f"Patient/{fixture['patient']['id']}",
        "practitioner_role_ref": f"PractitionerRole/{fixture['practitioner_role']['id']}",
        "organization_ref": f"Organization/{fixture['organization']['id']}",
    }


def validate_appointment(payload: dict) -> dict:
    required = ("appointment_id", "status", "start", "end", "patient_ref", "practitioner_role_ref", "organization_ref")
    errors = [f"{key} is required" for key in required if not payload.get(key)]
    if payload.get("surface") != "IPR":
        errors.append("surface must be IPR")
    if payload.get("start") and payload.get("end") and payload["start"] >= payload["end"]:
        errors.append("start must precede end")
    return {"valid": not errors, "errors": errors, "official_validator_run": False}
