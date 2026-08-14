"""TEHIK Master Patient Index R5 sandbox request projections."""
from __future__ import annotations


MPI_PROFILE = "https://fhir.ee/mpi/StructureDefinition/ee-mpi-patient-verified"
MPI_IG_VERSION = "1.5.0-trial-use"


def authorization_request(fixture: dict) -> dict:
    return {
        "user": {
            "personalCode": "OFFICIAL-TEHIK-TEST-USER-REQUIRED",
            "personalCodeSystem": "https://fhir.ee/sid/pid/est/ni",
        },
        "organization": fixture["organization"]["registry_code"],
        "patient": {"id": fixture["patient"]["id"]},
        "role": "healthcare-professional",
        "purpose": "Synthetic treatment-context integration test",
    }


def patient_preview(fixture: dict) -> dict:
    patient = dict(fixture["patient"])
    patient["meta"] = {
        "profile": [MPI_PROFILE],
        "tag": [{"system": "https://fastclinic.dev/fhir/tag", "code": "synthetic-nonconformant"}],
    }
    return {
        "resource": patient,
        "fhir_release": "5.0.0",
        "implementation_guide": MPI_IG_VERSION,
        "production_conformant": False,
        "reason": "No official TEHIK test identity or validator was used.",
    }


def validate_patient_preview(payload: dict) -> dict:
    resource = payload.get("resource") or payload
    errors = []
    if resource.get("resourceType") != "Patient":
        errors.append("resourceType must be Patient")
    if MPI_PROFILE not in resource.get("meta", {}).get("profile", []):
        errors.append("EE MPI verified-patient profile is required")
    if not resource.get("identifier"):
        errors.append("Patient.identifier is required")
    return {"valid": not errors, "errors": errors, "official_validator_run": False, "fhir_release": "5.0.0"}
