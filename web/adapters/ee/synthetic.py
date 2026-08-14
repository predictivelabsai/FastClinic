"""Clearly labelled Estonian non-PHI integration fixture."""
from __future__ import annotations

from copy import deepcopy

from .identifiers import SYNTHETIC_ID_SYSTEM

FIXTURE_ID = "ee-outpatient-epicrisis-001"
_FIXTURE = {
    "fixture_id": FIXTURE_ID,
    "synthetic": True,
    "warning": "Not an official TEHIK/X-Road test identity and unusable in production.",
    "organization": {"id": "ee-clinic-sandbox", "registry_code": "SYNTHETIC-REG-001", "name": "Test Tallinna Kliinik"},
    "patient": {
        "resourceType": "Patient", "id": "ee-patient-sandbox-001",
        "meta": {"profile": ["https://fhir.ee/mpi/StructureDefinition/ee-mpi-patient-verified"]},
        "identifier": [{"system": SYNTHETIC_ID_SYSTEM, "value": "EE-SANDBOX-PATIENT-001"}],
        "active": True, "name": [{"text": "Test Patsient", "family": "Patsient", "given": ["Test"]}],
        "gender": "female", "birthDate": "1990-01-01",
    },
    "practitioner": {"id": "ee-practitioner-sandbox-001", "name": "Test Arst", "role": "physician"},
    "encounter": {
        "id": "ee-encounter-sandbox-001", "start": "2026-08-14T10:00:00+03:00",
        "end": "2026-08-14T10:25:00+03:00", "setting": "ambulatory",
    },
    "diagnosis": {"system": "http://hl7.org/fhir/sid/icd-10", "code": "Z00.0", "display": "General medical examination"},
    "note": "Synthetic outpatient encounter. No PHI. Sandbox only.",
}


def outpatient_fixture() -> dict:
    return deepcopy(_FIXTURE)
