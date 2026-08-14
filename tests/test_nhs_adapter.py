"""Clinic OS Phase 5b — NHS adapter mapping (live spine stays gated)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pms.importer import _SCHEMA
from tests.test_fhir_r4 import _seed
from web.adapters.base import AdapterNotAvailable
from web.adapters.nhs import adapter, export_subject, import_record, live, push_reminder
from web.adapters.nhs.identifiers import nhs_number_valid, verify_nhs_number
from web.adapters.nhs.profiles import NHS_NUMBER_SYSTEM, as_gpconnect_stu3
from web.adapters.registry import get_adapter


@pytest.fixture()
def clinical(tmp_path, monkeypatch):
    path = tmp_path / "clinical.sqlite"
    _seed(str(path))
    from web import db
    monkeypatch.setattr(db, "DB_PATH", str(path))
    monkeypatch.setattr(db, "DATABASE_BACKEND", "sqlite")
    return path


def test_nhs_number_modulus_11():
    assert verify_nhs_number("943 476 5919")["valid"] is True
    assert verify_nhs_number("9434765919")["formatted"] == "943 476 5919"
    assert nhs_number_valid("1234567890") is False
    assert verify_nhs_number("123")["reason"] == "must_be_10_digits"
    assert verify_nhs_number("")["reason"] == "empty"


def test_verify_identifier_does_not_claim_pds_trace():
    result = adapter.verify_identifier("9434765919")
    assert result["valid"] is True
    assert result["traced"] is False
    assert result["source"] == "modulus-11"
    assert result["system"] == NHS_NUMBER_SYSTEM


def test_uk_core_export_rewrites_profile_and_nhs_system(clinical):
    resources = export_subject(1, release="r4")
    patient = next(row for row in resources if row["resourceType"] == "Patient")
    assert patient["meta"]["profile"] == [
        "https://fhir.hl7.org.uk/StructureDefinition/UKCore-Patient"
    ]
    nhs = next(ident for ident in patient["identifier"] if ident["system"] == NHS_NUMBER_SYSTEM)
    assert nhs["value"] == "9434765919"
    assert nhs["extension"][0]["valueCodeableConcept"]["coding"][0]["code"] == "02"


def test_related_person_uses_national_relationship_codes(clinical):
    resources = export_subject(2)
    related = next(row for row in resources if row["resourceType"] == "RelatedPerson")
    codes = {coding["code"] for coding in related["relationship"][0]["coding"]}
    assert "PRN" in codes
    assert "GUARD" in codes
    assert "guardian" not in codes  # core enum must not leak


def test_gpconnect_stu3_translates_profiles_and_imr_dates(clinical):
    from web.fhir.resources import reminder_resource
    r4 = reminder_resource({
        "id": 5, "subject_id": 1, "category": "vaccine",
        "status": "pending", "due_date": "2026-09-01", "created_at": "2026-08-01 08:00",
    })
    assert "dateCriterion" in r4["recommendation"][0]
    stu3 = as_gpconnect_stu3(r4)
    rec = stu3["recommendation"][0]
    assert "dateCriterion" not in rec
    assert rec["date"].startswith("2026-09-01")
    patient = next(row for row in export_subject(1, release="stu3") if row["resourceType"] == "Patient")
    assert "CareConnect-GPC-Patient-1" in patient["meta"]["profile"][0]


def test_import_uk_core_patient_and_related_person(clinical):
    patient = next(row for row in export_subject(1) if row["resourceType"] == "Patient")
    mapped = import_record(patient)
    assert mapped["core"]["subject"]["nhs_number"] == "9434765919"
    related = next(row for row in export_subject(2) if row["resourceType"] == "RelatedPerson")
    back = import_record(related)
    assert back["core"]["subject_party_role"]["role"] == "guardian"


def test_push_reminder_projects_without_spine(tmp_path, monkeypatch, clinical):
    from web import activation_loop
    ops = tmp_path / "ops.sqlite"
    monkeypatch.setattr(activation_loop, "OPS_DB_PATH", str(ops))
    with activation_loop._connect() as conn:
        conn.execute(
            "INSERT INTO reminder (id, subject_id, category, status, due_date, created_at) "
            "VALUES (1, 1, 'vaccine', 'pending', '2026-09-01', '2026-08-01 08:00')"
        )
        conn.commit()
    result = push_reminder(1)
    assert result["live"] is False
    assert result["projected"]["resourceType"] == "ImmunizationRecommendation"
    assert result["projected"]["meta"]["profile"][0].endswith("UKCore-ImmunizationRecommendation")
    with pytest.raises(AdapterNotAvailable):
        push_reminder(99)


def test_live_pds_and_gpconnect_stay_gated(monkeypatch):
    monkeypatch.delenv("NHS_LIVE_ENABLED", raising=False)
    with pytest.raises(AdapterNotAvailable) as exc:
        live.pds_lookup("9434765919")
    assert "PDS" in str(exc.value)
    with pytest.raises(AdapterNotAvailable):
        live.gpconnect_structured_record("9434765919")
    status = get_adapter("GB").status()
    assert status["surfaces"]["uk_core_r4_mapping"] == "available"
    assert status["surfaces"]["pds"] == "blocked"


def test_registry_unknown_country():
    with pytest.raises(AdapterNotAvailable):
        get_adapter("US")


def test_fhir_and_nhs_http_routes(clinical, monkeypatch):
    from web.api import api

    monkeypatch.setenv("FASTSME_API_TOKEN", "test-write-token")
    client = TestClient(api)
    meta = client.get("/v1/fhir/metadata")
    assert meta.status_code == 200
    assert meta.json()["resourceType"] == "CapabilityStatement"
    patient = client.get("/v1/fhir/Patient/1")
    assert patient.status_code == 200
    assert patient.json()["resourceType"] == "Patient"
    everything = client.get("/v1/fhir/Patient/1/$everything")
    assert everything.status_code == 200
    assert everything.json()["type"] == "searchset"
    missing = client.get("/v1/fhir/Patient/999")
    assert missing.status_code == 404
    check = client.post("/v1/adapters/GB/verify-identifier", json={"value": "9434765919"})
    assert check.status_code == 200
    assert check.json()["valid"] is True
    uk = client.get("/v1/adapters/GB/subjects/1")
    assert uk.status_code == 200
    patient_entry = next(
        entry["resource"] for entry in uk.json()["entry"]
        if entry["resource"]["resourceType"] == "Patient"
    )
    assert patient_entry["meta"]["profile"][0].endswith("UKCore-Patient")
    outcome = client.post("/v1/fhir/$validate", json={"resourceType": "Patient", "name": [{"text": "Ada"}]})
    assert outcome.status_code == 200
    assert outcome.json()["resourceType"] == "OperationOutcome"
