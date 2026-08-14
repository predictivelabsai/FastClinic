"""ESPBI clinical-document sandbox projections (E025/E027/E063)."""
from __future__ import annotations

import hashlib
import json

from .terminology import document_term


def clinical_document(fixture: dict, document_type: str = "E025") -> dict:
    term = document_term(document_type)
    code = term.code
    clinical: dict = {
        "document_type": term.coding(),
        "status": "completed",
        "patient": _reference(fixture["patient"]),
        "organization": _reference(fixture["organization"]),
        "author_role": _reference(fixture["practitioner_role"]),
        "encounter": fixture["encounter"],
    }
    if code == "E025":
        clinical.update({"conditions": [fixture["condition"]], "notes": [fixture["note"]]})
    elif code in {"E027", "E027-ATS"}:
        clinical["referral"] = {
            "reason": {"coding": fixture["condition"]["code"]["coding"]},
            "requested_service": "Synthetic specialist consultation",
        }
    elif code == "E063":
        clinical["immunization"] = {
            "status": "completed",
            "vaccineCode": {"text": "Synthetic test vaccine"},
            "occurrenceDateTime": "2026-08-14T09:15:00+03:00",
            "patient": _reference(fixture["patient"]),
        }
    else:
        raise ValueError(f"{code} is not an ESPBI clinical-document projection")
    envelope = {
        "surface": "ESPBI",
        "mode": "sandbox",
        "specification": "FastClinic LT sandbox envelope 1.0",
        "not_production_conformant": True,
        "created_at": "2026-08-14T06:25:00Z",
        "clinical_document": clinical,
    }
    envelope["payload_hash"] = _hash(envelope)
    return envelope


def validate_document(payload: dict) -> dict:
    errors = []
    if payload.get("surface") != "ESPBI":
        errors.append("surface must be ESPBI")
    clinical = payload.get("clinical_document") or {}
    for field in ("document_type", "patient", "organization", "author_role", "encounter"):
        if not clinical.get(field):
            errors.append(f"clinical_document.{field} is required")
    if not payload.get("not_production_conformant"):
        errors.append("sandbox payload must retain not_production_conformant=true")
    return {"valid": not errors, "errors": errors, "official_validator_run": False}


def _reference(resource: dict) -> dict:
    return {"reference": f"{resource['resourceType']}/{resource['id']}"}


def _hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
