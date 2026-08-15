"""Writable clinical workspace — Medplum-style features that stay local."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import TestClient as StarletteClient

from tests.test_fhir_r4 import _seed
from web import access, clinical
from web.clinical import ClinicalError


@pytest.fixture()
def dbs(tmp_path, monkeypatch):
    clinical_db = tmp_path / "clinical.sqlite"
    ops_db = tmp_path / "ops.sqlite"
    _seed(str(clinical_db))
    from web import db, activation_loop
    monkeypatch.setattr(db, "DB_PATH", str(clinical_db))
    monkeypatch.setattr(db, "DATABASE_BACKEND", "sqlite")
    monkeypatch.setattr(activation_loop, "OPS_DB_PATH", str(ops_db))
    monkeypatch.setenv("FASTCLINIC_OPS_DB", str(ops_db))
    monkeypatch.setenv("FASTCLINIC_OPS_BACKEND", "sqlite")
    monkeypatch.setenv("FASTCLINIC_ADMIN_EMAIL", "admin@fastclinic.example")
    return clinical_db, ops_db


def test_admin_env_login_keeps_full_access(dbs):
    assert access.role_of("admin@fastclinic.example") == "admin"
    assert access.can("admin@fastclinic.example", "billing") is True
    assert access.can("admin@fastclinic.example", "staff") is True


def test_named_admins_and_fail_closed_default(dbs):
    for email in (
        "kaljuvee@gmail.com", "joosep.laats@gmail.com", "patrickh217@gmail.com",
        "phil.hermann217@gmail.com",
    ):
        assert access.role_of(email) == "admin"
        assert access.can(email, "settings-roles") is True
    assert access.role_of("new.patient@example.com") == "patient"
    assert access.can("new.patient@example.com", "patients") is False
    with pytest.raises(ValueError, match="cannot be demoted"):
        access.set_profile("kaljuvee@gmail.com", "doctor")


def test_role_narrowing_does_not_affect_admin(dbs):
    from web.layout import left_pane
    access.set_profile("gp@example.com", "doctor")
    access.set_profile("desk@example.com", "receptionist")
    access.set_profile("bill@example.com", "billing")
    access.set_profile("pat@example.com", "patient", subject_id=1)
    assert access.can("gp@example.com", "chart") is True
    assert access.can("gp@example.com", "billing") is False
    assert access.can("desk@example.com", "appointments") is True
    assert access.can("desk@example.com", "chart") is False
    assert access.can("bill@example.com", "billing") is True
    assert access.can("bill@example.com", "orders") is False
    assert access.can("pat@example.com", "portal") is True
    assert access.can("pat@example.com", "patients") is False
    assert access.home_path("pat@example.com") == "/portal"
    assert access.allowed_nav_keys("gp@example.com") != access.allowed_nav_keys("desk@example.com")
    assert access.allowed_nav_keys("desk@example.com") != access.allowed_nav_keys("bill@example.com")
    assert access.allowed_nav_keys("bill@example.com") != access.allowed_nav_keys("pat@example.com")
    admin_nav = str(left_pane("dashboard", "admin@fastclinic.example"))
    doctor_nav = str(left_pane("dashboard", "gp@example.com"))
    reception_nav = str(left_pane("dashboard", "desk@example.com"))
    billing_nav = str(left_pane("dashboard", "bill@example.com"))
    patient_nav = str(left_pane("portal", "pat@example.com"))
    assert "/settings/roles" in admin_nav
    assert "/settings/roles" not in doctor_nav + reception_nav + billing_nav + patient_nav
    assert "/orders" in doctor_nav and "/orders" not in reception_nav
    assert "/appointments" in reception_nav and "/billing" not in reception_nav
    assert "/billing" in billing_nav and 'href="/patients"' not in patient_nav
    assert "/portal" in patient_nav and "/clinical" not in patient_nav
    assert access.role_of("admin@fastclinic.example") == "admin"


def test_chart_order_task_coverage_and_message_loop(dbs):
    enc = clinical.open_encounter(1, clinician_id=7, reason="Review")
    assert enc["status"] == "in-progress"
    note = clinical.add_note(
        1, encounter_id=enc["id"], subjective="Cough",
        assessment="Likely viral", plan="Rest",
    )
    assert note["subjective"] == "Cough"
    order = clinical.place_order(1, "lab", "Full blood count", encounter_id=enc["id"], code="FBC")
    assert order["status"] == "active"
    order = clinical.set_order_status(order["id"], "completed")
    assert order["status"] == "completed"
    task = clinical.add_task(1, "Call with results", encounter_id=enc["id"])
    task = clinical.set_task_status(task["id"], "completed")
    assert task["status"] == "completed"
    cover = clinical.add_coverage(1, "Bupa", member_id="B-99")
    assert cover["payor"] == "Bupa"
    thread = clinical.start_thread("Results", subject_id=1, body="All clear", sender_email="gp@example.com")
    clinical.post_message(thread["id"], "Thank you", sender_email="pat@example.com")
    assert len(clinical.messages(thread["id"])) == 2
    finished = clinical.finish_encounter(enc["id"])
    assert finished["status"] == "finished"
    assert clinical.intakes_for(1) == []
    clinical.save_intake(1, {"allergies": "none"})
    assert len(clinical.intakes_for(1)) == 1


def test_unknown_patient_is_refused(dbs):
    with pytest.raises(ClinicalError):
        clinical.open_encounter(999)


def test_api_chart_and_orders(dbs, monkeypatch):
    from web.api import api
    monkeypatch.setenv("FASTSME_API_TOKEN", "tok")
    client = TestClient(api)
    auth = {"Authorization": "Bearer tok"}
    created = client.post("/v1/chart/encounters", headers=auth,
                          json={"subject_id": 1, "reason": "Review"})
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    note = client.post("/v1/chart/notes", headers=auth, json={
        "subject_id": 1, "encounter_id": eid, "assessment": "Well",
    })
    assert note.status_code == 201
    order = client.post("/v1/orders", headers=auth, json={
        "subject_id": 1, "kind": "imaging", "name": "Chest X-ray",
    })
    assert order.status_code == 201
    patched = client.patch(f"/v1/orders/{order.json()['id']}", headers=auth,
                           json={"status": "completed"})
    assert patched.json()["status"] == "completed"
    cover = client.post("/v1/coverage", headers=auth,
                        json={"subject_id": 1, "payor": "AXA"})
    assert cover.status_code == 201
    listed = client.get("/v1/coverage", headers=auth, params={"subject_id": 1})
    assert listed.json()["data"][0]["payor"] == "AXA"
    health = client.get("/v1/health")
    assert health.json()["version"] == "1.4.0"


def test_cockpit_routes_and_patient_denial(dbs, monkeypatch):
    monkeypatch.setenv("FASTCLINIC_ADMIN_EMAIL", "admin@fastclinic.example")
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_AUTH_ENABLED", "true")
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_EMAIL", "admin@fastclinic.example")
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_PASSWORD", "FastClinic2026$")
    monkeypatch.setenv("FASTCLINIC_SECRET", "test-secret")
    from web.account_auth import accounts
    accounts._seed_bootstrap_account()
    import web_app
    client = StarletteClient(web_app.app)
    signed = client.post(
        "/auth/local/login",
        data={"email": "admin@fastclinic.example", "password": "FastClinic2026$"},
    )
    assert signed.status_code == 200, signed.text
    chart = client.get("/patients/1/chart")
    assert chart.status_code == 200
    assert "SOAP" in chart.text or "Chart" in chart.text
    opened = client.post("/patients/1/chart/open", data={"reason": "Review"}, follow_redirects=True)
    assert opened.status_code == 200
    orders = client.get("/orders")
    assert orders.status_code == 200
    staff = client.get("/admin/staff")
    assert staff.status_code == 200
    with pytest.raises(ValueError, match="cannot be demoted"):
        access.set_profile("admin@fastclinic.example", "patient", subject_id=1)
    # configured admin email always stays admin
    assert access.role_of("admin@fastclinic.example") == "admin"
    access.set_profile("visitor@example.com", "patient", subject_id=1)
    assert access.can("visitor@example.com", "billing") is False
    assert access.home_path("visitor@example.com") == "/portal"
