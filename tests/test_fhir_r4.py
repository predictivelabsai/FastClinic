"""Clinic OS Phase 5a — FHIR R4 shaping of the core."""
from __future__ import annotations

import sqlite3

import pytest

from pms.importer import _SCHEMA
from web import fhir
from web.fhir.importing import import_resource, validate_resource
from web.fhir.resources import NATIONAL_ID_SYSTEM, reminder_resource


def _seed(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO subject (id, party_id, gender, date_of_birth, official_name, "
        "nhs_number, city, street_address, registered_clinician_id) "
        "VALUES (1, 10, '1', '1980-01-15', 'Ada Adult', '9434765919', 'Leeds', "
        "'1 Test Street', 7)"
    )
    conn.execute(
        "INSERT INTO subject (id, party_id, gender, date_of_birth, official_name) "
        "VALUES (2, 11, '3', '2020-04-01', 'Mina Minor')"
    )
    conn.execute(
        "INSERT INTO subject (id, party_id, gender, date_of_birth, official_name) "
        "VALUES (3, 11, '1', '2022-06-01', 'Sam Sibling')"
    )
    conn.execute(
        "INSERT INTO party (id, name, phone, email, city, marketing_opt_out) "
        "VALUES (10, 'Ada Adult', '07000000001', 'ada@example.com', 'Leeds', 0)"
    )
    conn.execute(
        "INSERT INTO party (id, name, phone, email, marketing_opt_out) "
        "VALUES (11, 'Pat Parent', '07000000002', 'pat@example.com', 1)"
    )
    conn.execute("INSERT INTO subject_party_role VALUES (1, 10, 'self', 1)")
    conn.execute("INSERT INTO subject_party_role VALUES (2, 11, 'guardian', 1)")
    conn.execute("INSERT INTO subject_party_role VALUES (3, 11, 'guardian', 1)")
    conn.execute(
        "INSERT INTO consultation (id, subject_id, consult_at, revenue_vat, "
        "item_count, is_visit, clinician_id) "
        "VALUES (100, 1, '2026-01-15 10:00:00', 80, 1, 1, 7)"
    )
    conn.execute(
        "INSERT INTO diagnosis (id, consultation_id, subject_id, code, name, "
        "diagnosis_at, clinician_id) "
        "VALUES (200, 100, 1, 'J06.9', 'Upper respiratory infection', "
        "'2026-01-15 10:05:00', 7)"
    )
    conn.execute(
        "INSERT INTO item (id, consultation_id, subject_id, name, category, "
        "specialty, item_at, clinician_id, line_total_vat) "
        "VALUES (300, 100, 1, 'Influenza vaccine', 'vaccine', 'general_practice', "
        "'2026-01-15 10:10:00', 7, 12.5)"
    )
    conn.execute(
        "INSERT INTO item (id, consultation_id, subject_id, name, category, "
        "specialty, item_at, clinician_id, line_total_vat) "
        "VALUES (301, 100, 1, 'Full blood count', 'lab', 'diagnostics', "
        "'2026-01-15 10:12:00', 7, 18)"
    )
    conn.execute(
        "INSERT INTO note (id, consultation_id, subject_id, text, custom_type, "
        "draft, note_at, clinician_id) "
        "VALUES (400, 100, 1, 'Well today.', 'consult', 0, '2026-01-15 10:20:00', 7)"
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def clinical(tmp_path, monkeypatch):
    path = tmp_path / "clinical.sqlite"
    _seed(str(path))
    from web import db
    monkeypatch.setattr(db, "DB_PATH", str(path))
    monkeypatch.setattr(db, "DATABASE_BACKEND", "sqlite")
    return path


def _by_type(resources, kind):
    return [row for row in resources if row["resourceType"] == kind]


def test_capability_statement_lists_r4_resources():
    cap = fhir.capability_statement()
    assert cap["resourceType"] == "CapabilityStatement"
    assert cap["fhirVersion"] == "4.0.1"
    types = {row["type"] for row in cap["rest"][0]["resource"]}
    assert {"Patient", "RelatedPerson", "Encounter", "Condition", "Immunization"}.issubset(types)


def test_adult_export_is_self_without_related_person(clinical):
    resources = fhir.export_subject(1)
    kinds = [row["resourceType"] for row in resources]
    assert kinds.count("Patient") == 1
    patient = _by_type(resources, "Patient")[0]
    assert patient["id"] == "1"
    assert patient["gender"] == "male"
    assert patient["birthDate"] == "1980-01-15"
    assert patient["name"][0]["family"] == "Adult"
    systems = {ident["system"] for ident in patient["identifier"]}
    assert f"{NATIONAL_ID_SYSTEM}" in systems or any(
        ident.get("value") == "9434765919" for ident in patient["identifier"]
    )
    assert _by_type(resources, "RelatedPerson") == []
    assert _by_type(resources, "Person") == []
    assert _by_type(resources, "Encounter")[0]["id"] == "100"
    assert _by_type(resources, "Condition")[0]["code"]["coding"][0]["code"] == "J06.9"
    assert _by_type(resources, "Immunization")[0]["vaccineCode"]["text"] == "Influenza vaccine"
    assert _by_type(resources, "Observation")[0]["code"]["text"] == "Full blood count"
    assert _by_type(resources, "DocumentReference")[0]["status"] == "current"
    assert _by_type(resources, "Organization")[0]["id"] == "fastclinic"


def test_minor_export_denormalises_related_person_and_shared_person(clinical):
    mina = fhir.export_subject(2)
    related = _by_type(mina, "RelatedPerson")
    assert len(related) == 1
    assert related[0]["patient"]["reference"] == "Patient/2"
    assert related[0]["relationship"][0]["coding"][0]["code"] == "guardian"
    people = _by_type(mina, "Person")
    assert len(people) == 1
    links = {link["target"]["reference"] for link in people[0]["link"]}
    assert "RelatedPerson/11-2-guardian" in links
    assert "RelatedPerson/11-3-guardian" in links


def test_bundle_everything_and_single_reads(clinical):
    bundle = fhir.bundle_subject(1)
    assert bundle["resourceType"] == "Bundle"
    assert bundle["total"] >= 6
    patient = fhir.export_resource("Patient", "1")
    assert patient["resourceType"] == "Patient"
    encounter = fhir.export_resource("Encounter", "100")
    assert encounter["class"]["code"] == "AMB"
    with pytest.raises(fhir.NotFound):
        fhir.export_resource("Patient", "999")
    with pytest.raises(fhir.NotFound):
        fhir.export_resource("Alien", "1")


def test_validate_and_import_patient_round_trip(clinical):
    patient = fhir.export_resource("Patient", "1")
    outcome = validate_resource(patient)
    assert all(issue["severity"] != "error" for issue in outcome["issue"])
    mapped = import_resource(patient)
    assert mapped["apply_safe"] is True
    assert mapped["core"]["subject"]["official_name"] == "Ada Adult"
    assert mapped["core"]["subject"]["nhs_number"] == "9434765919"
    assert mapped["core"]["subject"]["gender"] == "1"

    bad = validate_resource({"resourceType": "Encounter"})
    assert any(issue["severity"] == "error" for issue in bad["issue"])


def test_related_person_import_keeps_core_role():
    mapped = import_resource({
        "resourceType": "RelatedPerson",
        "patient": {"reference": "Patient/2"},
        "name": [{"text": "Pat Parent"}],
        "relationship": [{
            "coding": [{"system": "https://fastclinic.dev/sid/party-role", "code": "guardian"}]
        }],
    })
    assert mapped["core"]["subject_party_role"]["role"] == "guardian"
    assert mapped["core"]["subject_party_role"]["subject_id"] == 2


def test_vaccine_reminder_requires_forecast_status():
    resource = reminder_resource({
        "id": 9, "subject_id": 1, "category": "vaccine",
        "status": "pending", "due_date": "2026-08-01", "created_at": "2026-07-01 09:00",
    })
    assert resource["resourceType"] == "ImmunizationRecommendation"
    rec = resource["recommendation"][0]
    assert rec["forecastStatus"]["coding"][0]["code"] == "due"
    assert rec["dateCriterion"]
    other = reminder_resource({
        "id": 10, "subject_id": 1, "category": "health_plan",
        "status": "pending", "due_date": "2026-08-01",
    })
    assert other["resourceType"] == "Task"
    outcome = validate_resource({"resourceType": "ImmunizationRecommendation", "recommendation": [{}]})
    assert any("forecastStatus" in issue["diagnostics"] for issue in outcome["issue"])
