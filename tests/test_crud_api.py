"""End-to-end API tests against disposable clinical and operational databases."""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from web import access, activation_loop, api_store, db, mobile_auth
from web.api import api, backend


TOKEN = "test-write-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    clinical = tmp_path / "clinical.sqlite"
    operations = tmp_path / "operations.sqlite"
    shutil.copy2("fastclinic.sqlite", clinical)
    monkeypatch.setattr(db, "DB_PATH", str(clinical))
    monkeypatch.setattr(backend, "path", str(clinical))
    monkeypatch.setattr(activation_loop, "OPS_DB_PATH", str(operations))
    monkeypatch.setenv("FASTSME_API_TOKEN", TOKEN)
    with TestClient(api) as test_client:
        yield test_client


def _first(client, resource):
    response = client.get(f"/v1/{resource}?limit=1")
    assert response.status_code == 200, response.text
    return response.json()["data"][0]


def test_openapi_documents_deep_surface_and_consistent_errors(client, monkeypatch):
    schema = client.get("/openapi.json").json()
    assert schema["info"]["version"] == "1.5.0"
    assert schema["servers"][0]["url"] == "https://api.fastclinic.dev"
    assert len(schema["paths"]) >= 47
    assert "post" in schema["paths"]["/v1/patients"]
    assert {"get", "patch", "delete"} <= set(schema["paths"]["/v1/patients/{item_id}"])
    assert "/v1/analytics/specialties" in schema["paths"]
    assert "/v1/trial-balance" in schema["paths"]
    assert "/v1/mobile/bootstrap" in schema["paths"]
    assert "/v1/mobile/booking/chat" in schema["paths"]

    health = client.get("/v1/health").json()
    assert health["database_backend"] == "sqlite"
    assert health["database_ready"] is True

    missing_route = client.get("/v1/not-a-resource")
    assert missing_route.status_code == 404
    assert missing_route.json()["error"]["code"] == "http_error"

    cors = client.options(
        "/v1/patients",
        headers={
            "Origin": "https://integration.example.test",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert cors.status_code == 200
    assert "PATCH" in cors.headers["access-control-allow-methods"]

    missing_name = client.post("/v1/patients", headers=AUTH, json={})
    assert missing_name.status_code == 422
    assert missing_name.json()["error"]["code"] == "validation_error"

    monkeypatch.delenv("FASTSME_API_TOKEN")
    disabled = client.post("/v1/patients", json={"official_name": "No token"})
    assert disabled.status_code == 503
    assert disabled.json()["error"]["code"] == "writes_disabled"
    invalid = client.post("/v1/appointments", headers=AUTH, json={})
    assert invalid.status_code == 503  # token was deliberately disabled above


def test_patient_crud_archives_instead_of_erasing(client):
    created = client.post(
        "/v1/patients",
        headers=AUTH,
        json={"official_name": "API Synthetic Patient", "gender": "F", "city": "Tallinn"},
    )
    assert created.status_code == 201, created.text
    patient_id = created.json()["id"]

    changed = client.patch(
        f"/v1/patients/{patient_id}", headers=AUTH, json={"city": "Tartu"}
    )
    assert changed.status_code == 200
    assert changed.json()["city"] == "Tartu"

    archived = client.delete(f"/v1/patients/{patient_id}", headers=AUTH)
    assert archived.status_code == 204
    read_back = client.get(f"/v1/patients/{patient_id}")
    assert read_back.status_code == 200
    assert read_back.json()["archived"] == 1

    audit = client.get("/v1/audit?resource=patients", headers=AUTH).json()["data"]
    assert {row["action"] for row in audit} >= {"create", "update", "archive"}


def test_party_and_relationship_crud_preserve_link_integrity(client):
    patient = client.post(
        "/v1/patients", headers=AUTH, json={"official_name": "Synthetic Minor"}
    ).json()
    party = client.post(
        "/v1/parties",
        headers=AUTH,
        json={"name": "Synthetic Guardian", "email": "guardian@example.test"},
    ).json()
    path = f"/v1/relationships/{patient['id']}/{party['id']}/guardian"
    relation = client.post(
        "/v1/relationships",
        headers=AUTH,
        json={
            "subject_id": patient["id"],
            "party_id": party["id"],
            "role": "guardian",
            "is_primary": True,
        },
    )
    assert relation.status_code == 201, relation.text
    assert relation.json()["is_primary"] == 1

    # A subject always retains exactly one primary contact, even when a client
    # attempts to demote its only relationship.
    demoted = client.patch(path, headers=AUTH, json={"is_primary": False})
    assert demoted.status_code == 200
    assert demoted.json()["is_primary"] == 1

    linked_delete = client.delete(f"/v1/parties/{party['id']}", headers=AUTH)
    assert linked_delete.status_code == 409
    changed = client.patch(path, headers=AUTH, json={"role": "payer"})
    assert changed.status_code == 200
    assert changed.json()["role"] == "payer"
    payer_path = f"/v1/relationships/{patient['id']}/{party['id']}/payer"
    assert client.delete(payer_path, headers=AUTH).status_code == 204
    assert client.delete(f"/v1/parties/{party['id']}", headers=AUTH).status_code == 204


def test_note_lifecycle_validates_consultation_and_archives(client):
    consultation = _first(client, "consultations")
    created = client.post(
        "/v1/notes",
        headers=AUTH,
        json={
            "subject_id": consultation["subject_id"],
            "consultation_id": consultation["id"],
            "text": "Synthetic API note",
            "draft": True,
        },
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]
    changed = client.patch(
        f"/v1/notes/{note_id}",
        headers=AUTH,
        json={"text": "Updated synthetic API note", "draft": False},
    )
    assert changed.status_code == 200
    assert len(changed.json()["text_hash"]) == 64
    assert client.delete(f"/v1/notes/{note_id}", headers=AUTH).status_code == 204
    assert client.get(f"/v1/notes/{note_id}").json()["archived_at"]


def test_appointment_crud_detects_conflicts_and_cancels(client):
    patient = _first(client, "patients")
    clinician = client.get("/v1/clinicians").json()["data"][0]
    payload = {
        "subject_id": patient["id"],
        "clinician_id": clinician["id"],
        "start_at": "2027-01-04 09:00",
        "duration_min": 20,
        "reason": "Synthetic API booking",
    }
    created = client.post("/v1/appointments", headers=AUTH, json=payload)
    assert created.status_code == 201, created.text
    appointment_id = created.json()["id"]
    conflict = client.post("/v1/appointments", headers=AUTH, json=payload)
    assert conflict.status_code == 409
    invalid_clinician = client.patch(
        f"/v1/appointments/{appointment_id}", headers=AUTH, json={"clinician_id": 999999}
    )
    assert invalid_clinician.status_code == 404
    moved = client.patch(
        f"/v1/appointments/{appointment_id}",
        headers=AUTH,
        json={"start_at": "2027-01-04 10:00", "status": "confirmed"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["start_at"] == "2027-01-04 10:00"
    assert client.delete(f"/v1/appointments/{appointment_id}", headers=AUTH).status_code == 204
    assert client.get(f"/v1/appointments/{appointment_id}").json()["status"] == "cancelled"


def test_mobile_patient_contract_is_identity_scoped(client, monkeypatch):
    patient = _first(client, "patients")
    clinician = client.get("/v1/clinicians").json()["data"][0]
    access.set_profile("mobile.patient@example.com", "patient", subject_id=patient["id"])
    principal = access.profile("mobile.patient@example.com")
    api.dependency_overrides[mobile_auth.require_mobile_principal] = lambda: principal
    monkeypatch.setenv("MODEL_PROVIDER", "")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    try:
        me = client.get("/v1/mobile/me")
        assert me.status_code == 200 and me.json()["subject_id"] == patient["id"]
        bootstrap = client.get("/v1/mobile/bootstrap")
        assert bootstrap.status_code == 200
        assert bootstrap.json()["booking_modes"] == ["assistant", "classical"]
        availability = client.get(
            "/v1/mobile/availability",
            params={"clinician_id": clinician["id"], "day": "2027-01-05"},
        )
        assert availability.status_code == 200 and availability.json()["slots"]
        payload = {
            "clinician_id": clinician["id"], "starts_at": "2027-01-05 09:00",
            "appointment_type_code": "general", "reason": "Mobile booking",
        }
        created = client.post("/v1/mobile/appointments", json=payload)
        assert created.status_code == 201, created.text
        assert created.json()["subject_id"] == patient["id"]
        injected = client.post(
            "/v1/mobile/appointments", json={**payload, "subject_id": patient["id"] + 1},
        )
        assert injected.status_code == 422
        own = client.get("/v1/mobile/appointments").json()["data"]
        assert {row["id"] for row in own} == {created.json()["id"]}
        cancelled = client.post(f"/v1/mobile/appointments/{created.json()['id']}/cancel")
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    finally:
        api.dependency_overrides.pop(mobile_auth.require_mobile_principal, None)


def test_reminders_consent_and_immutable_blocked_communication(client):
    patient = client.post(
        "/v1/patients", headers=AUTH, json={"official_name": "Consent Subject"}
    ).json()
    party = client.post(
        "/v1/parties",
        headers=AUTH,
        json={"name": "Consent Party", "phone": "+37255550123"},
    ).json()
    client.post(
        "/v1/relationships",
        headers=AUTH,
        json={"subject_id": patient["id"], "party_id": party["id"], "role": "self", "is_primary": True},
    )
    consent_response = client.patch(
        f"/v1/parties/{party['id']}/marketing-consent",
        headers=AUTH,
        json={"marketing_opt_out": True},
    )
    assert consent_response.status_code == 200
    reminder = client.post(
        "/v1/reminders",
        headers=AUTH,
        json={"subject_id": patient["id"], "category": "health_plan", "due_date": "2027-01-05"},
    )
    assert reminder.status_code == 201
    reminder_id = reminder.json()["id"]
    blocked = client.post(
        "/v1/communications",
        headers=AUTH,
        json={
            "channel": "sms",
            "to_addr": "+37255550123",
            "body": "Synthetic marketing reminder",
            "reminder_id": reminder_id,
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "marketing_opt_out"
    communications = client.get("/v1/communications", headers=AUTH).json()["data"]
    assert communications[0]["status"] == "blocked"
    assert client.delete(f"/v1/reminders/{reminder_id}", headers=AUTH).status_code == 204


def test_invoice_payment_refund_and_void_keep_ledger_balanced(client):
    consultation = next(
        row for row in client.get("/v1/consultations?limit=20").json()["data"]
        if row["revenue_vat"] and row["revenue_vat"] > 1
    )
    invoice_response = client.post(
        "/v1/invoices", headers=AUTH, json={"consultation_id": consultation["id"]}
    )
    assert invoice_response.status_code == 201, invoice_response.text
    invoice = invoice_response.json()
    duplicate = client.post(
        "/v1/invoices", headers=AUTH, json={"consultation_id": consultation["id"]}
    )
    assert duplicate.status_code == 409

    payment_headers = {**AUTH, "Idempotency-Key": "synthetic-payment-001"}
    first = client.post(
        "/v1/payments",
        headers=payment_headers,
        json={"invoice_id": invoice["id"], "amount": 1.0, "method": "card"},
    )
    assert first.status_code == 201, first.text
    repeated = client.post(
        "/v1/payments",
        headers=payment_headers,
        json={"invoice_id": invoice["id"], "amount": 1.0, "method": "card"},
    )
    assert repeated.status_code == 201
    assert repeated.json()["id"] == first.json()["id"]
    idempotency_conflict = client.post(
        "/v1/payments",
        headers=payment_headers,
        json={"invoice_id": invoice["id"], "amount": 0.5, "method": "card"},
    )
    assert idempotency_conflict.status_code == 409
    overpayment = client.post(
        "/v1/payments",
        headers={**AUTH, "Idempotency-Key": "synthetic-payment-002"},
        json={"invoice_id": invoice["id"], "amount": invoice["total"] + 1},
    )
    assert overpayment.status_code == 409
    assert client.get("/v1/trial-balance", headers=AUTH).json()["balanced"] is True

    refund = client.delete(f"/v1/payments/{first.json()['id']}", headers=AUTH)
    assert refund.status_code == 200
    assert refund.json()["status"] == "refunded"
    assert client.delete(f"/v1/invoices/{invoice['id']}", headers=AUTH).status_code == 204
    assert client.get(f"/v1/invoices/{invoice['id']}", headers=AUTH).json()["status"] == "Void"
    assert client.get("/v1/trial-balance", headers=AUTH).json()["balanced"] is True


def test_analytics_and_sensitive_operational_reads_have_expected_access(client):
    overview = client.get("/v1/analytics/overview")
    assert overview.status_code == 200
    assert overview.json()["total_patients"] > 0
    specialties = client.get("/v1/analytics/specialties")
    assert specialties.status_code == 200
    assert specialties.json()["data"]
    assert client.get("/v1/reminders").status_code == 401
    assert client.get("/v1/ledger").status_code == 401
