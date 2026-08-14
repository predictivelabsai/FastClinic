"""Clearly labelled, non-PHI Lithuanian integration fixtures."""
from __future__ import annotations

from copy import deepcopy

from .identifiers import JAR_SYSTEM, SYNTHETIC_ID_SYSTEM

FIXTURE_ID = "lt-outpatient-e025-001"

_FIXTURE = {
    "fixture_id": FIXTURE_ID,
    "synthetic": True,
    "warning": "Not an official ESPBI test identity and not valid for production submission.",
    "organization": {
        "resourceType": "Organization",
        "id": "lt-clinic-sandbox",
        "identifier": [{"system": JAR_SYSTEM, "value": "SYNTHETIC-JAR-001"}],
        "active": True,
        "name": "Sintetinė Vilniaus klinika",
    },
    "patient": {
        "resourceType": "Patient",
        "id": "lt-patient-sandbox-001",
        "identifier": [{"system": SYNTHETIC_ID_SYSTEM, "value": "LT-SANDBOX-PATIENT-001"}],
        "active": True,
        "name": [{"use": "official", "text": "Testas Pacientas", "family": "Pacientas", "given": ["Testas"]}],
        "gender": "male",
        "birthDate": "1989-01-01",
    },
    "practitioner": {
        "resourceType": "Practitioner",
        "id": "lt-practitioner-sandbox-001",
        "identifier": [{"system": SYNTHETIC_ID_SYSTEM, "value": "LT-SANDBOX-PRACTITIONER-001"}],
        "active": True,
        "name": [{"text": "Gydytoja Testuotoja", "family": "Testuotoja", "given": ["Gydytoja"]}],
    },
    "practitioner_role": {
        "resourceType": "PractitionerRole",
        "id": "lt-role-sandbox-001",
        "identifier": [{"system": SYNTHETIC_ID_SYSTEM, "value": "LT-SANDBOX-ROLE-001"}],
        "active": True,
        "period": {"start": "2026-01-01"},
        "practitioner": {"reference": "Practitioner/lt-practitioner-sandbox-001"},
        "organization": {"reference": "Organization/lt-clinic-sandbox"},
        "code": [{"coding": [{"system": "http://esveikata.lt/classifiers/RoleType", "code": "DOCTOR", "display": "Gydytojas"}]}],
        "specialty": [{"coding": [{"system": "http://esveikata.lt/classifiers/QualificationCode", "code": "SANDBOX-GP", "display": "Synthetic general practitioner"}]}],
    },
    "encounter": {
        "resourceType": "Encounter",
        "id": "lt-encounter-sandbox-001",
        "status": "completed",
        "class": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"}]},
        "subject": {"reference": "Patient/lt-patient-sandbox-001"},
        "actualPeriod": {"start": "2026-08-14T09:00:00+03:00", "end": "2026-08-14T09:25:00+03:00"},
        "serviceProvider": {"reference": "Organization/lt-clinic-sandbox"},
    },
    "condition": {
        "resourceType": "Condition",
        "id": "lt-condition-sandbox-001",
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
        "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": "Z00.0", "display": "General medical examination"}]},
        "subject": {"reference": "Patient/lt-patient-sandbox-001"},
        "encounter": {"reference": "Encounter/lt-encounter-sandbox-001"},
    },
    "note": {
        "resourceType": "DocumentReference",
        "id": "lt-note-sandbox-001",
        "status": "current",
        "subject": {"reference": "Patient/lt-patient-sandbox-001"},
        "content": [{"attachment": {"contentType": "text/markdown", "data": "IyBTeW50aGV0aWMgdmlzaXQgbm90ZQoKLSBObyBQSEkuCi0gU2FuZGJveCBvbmx5Lg=="}}],
    },
    "appointment": {
        "resourceType": "Appointment",
        "id": "lt-appointment-sandbox-001",
        "status": "booked",
        "start": "2026-08-14T09:00:00+03:00",
        "end": "2026-08-14T09:25:00+03:00",
        "participant": [
            {"actor": {"reference": "Patient/lt-patient-sandbox-001"}, "status": "accepted"},
            {"actor": {"reference": "PractitionerRole/lt-role-sandbox-001"}, "status": "accepted"},
        ],
    },
    "lab_order": {
        "resourceType": "ServiceRequest",
        "id": "lt-lab-order-sandbox-001",
        "status": "active",
        "intent": "order",
        "code": {"coding": [{"system": "http://loinc.org", "code": "58410-2", "display": "Complete blood count panel"}]},
        "subject": {"reference": "Patient/lt-patient-sandbox-001"},
        "encounter": {"reference": "Encounter/lt-encounter-sandbox-001"},
        "requester": {"reference": "PractitionerRole/lt-role-sandbox-001"},
    },
}


def outpatient_fixture() -> dict:
    return deepcopy(_FIXTURE)
