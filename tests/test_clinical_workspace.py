"""Writable clinical workspace — Medplum-style features that stay local."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import TestClient as StarletteClient

from tests.test_fhir_r4 import _seed
from web import access, appointments, clinical
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
        access.set_profile("kaljuvee@gmail.com", "practitioner")


def test_role_narrowing_does_not_affect_admin(dbs):
    from web.layout import left_pane
    access.set_profile("gp@example.com", "practitioner")
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
    practitioner_nav = str(left_pane("dashboard", "gp@example.com"))
    reception_nav = str(left_pane("dashboard", "desk@example.com"))
    billing_nav = str(left_pane("dashboard", "bill@example.com"))
    patient_nav = str(left_pane("portal", "pat@example.com"))
    assert "/settings/roles" in admin_nav
    assert "/settings/roles" not in practitioner_nav + reception_nav + billing_nav + patient_nav
    assert "/orders" in practitioner_nav and "/orders" not in reception_nav
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


def test_patient_booking_actions_are_record_scoped(dbs):
    appointment_id = appointments.book(
        1, 7, "2026-08-17 09:00", reason="Review", with_reminder=False,
    )
    from web import activation_loop
    participants = activation_loop.query(
        "SELECT participant_type,participant_ref FROM appointment_participant "
        "WHERE appointment_id=? ORDER BY participant_type", (appointment_id,),
    )
    assert participants == [
        {"participant_type": "patient", "participant_ref": "Patient/1"},
        {"participant_type": "practitioner", "participant_ref": "Practitioner/7"},
    ]
    assert appointments.cancel_for_subject(appointment_id, 999, actor="other@example.com") is False
    assert appointments.get(appointment_id)["status"] == "scheduled"
    assert appointments.cancel_for_subject(appointment_id, 1, actor="patient@example.com") is True
    assert appointments.get(appointment_id)["status"] == "cancelled"


def test_concurrent_bookings_cannot_double_book_a_room(dbs):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    gate = Barrier(2)

    def reserve(subject_id, clinician_id):
        gate.wait()
        try:
            return appointments.book(
                subject_id, clinician_id, "2026-08-17 11:00", room="room-1",
                with_reminder=False,
            )
        except appointments.SlotTaken:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda args: reserve(*args), [(1, 7), (2, 8)]))
    assert sum(result is not None for result in results) == 1


def test_practitioner_subject_scope_follows_assigned_activity(dbs):
    access.set_profile("gp@example.com", "practitioner", clinician_id=7)
    appointments.book(1, 7, "2026-08-17 09:00", with_reminder=False)
    assert access.can_access_subject("gp@example.com", 1) is True
    assert access.can_access_subject("gp@example.com", 2) is False


def test_practitioner_availability_exception_closes_day(dbs):
    from web import activation_loop
    activation_loop.execute(
        "INSERT INTO practitioner_availability_exception "
        "(clinician_id,exception_date,available,reason) VALUES(?,?,?,?)",
        (7, "2026-08-18", 0, "Leave"),
    )
    from datetime import date
    assert appointments.day_schedule(7, date(2026, 8, 18)) == []


def test_mobile_oauth_jwt_resolves_fail_closed_rbac(dbs, monkeypatch):
    import time
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import HTTPException
    from web import mobile_auth

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class SigningKey:
        key = private_key.public_key()

    class JWKS:
        def __init__(self, url):
            assert url == "https://auth.example.test/jwks"

        def get_signing_key_from_jwt(self, token):
            return SigningKey()

    monkeypatch.setattr(jwt, "PyJWKClient", JWKS)
    monkeypatch.setenv("MEDBACKEND_PATIENT_JWKS_URL", "https://auth.example.test/jwks")
    monkeypatch.setenv("MEDBACKEND_PATIENT_CLIENT_ID", "fastclinic-mobile")
    access.set_profile("mobile@example.com", "patient", subject_id=1)
    token = jwt.encode({
        "sub": "medbackend-patient-1", "email": "mobile@example.com",
        "aud": "fastclinic-mobile", "exp": int(time.time()) + 300,
    }, private_key, algorithm="RS256")
    principal = mobile_auth.require_mobile_principal(token)
    assert principal["role"] == "patient" and principal["subject_id"] == 1

    wrong_audience = jwt.encode({
        "sub": "medbackend-patient-1", "email": "mobile@example.com",
        "aud": "another-client", "exp": int(time.time()) + 300,
    }, private_key, algorithm="RS256")
    with pytest.raises(HTTPException) as exc:
        mobile_auth.require_mobile_principal(wrong_audience)
    assert exc.value.status_code == 401


def test_langgraph_booking_requires_explicit_confirmation(dbs, monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MODEL_PROVIDER", "")
    from graph.booking_agent import respond

    proposal = respond(
        "I need practitioner 7 on 2026-08-17 at 09:00", 1, "patient@example.com",
    )
    assert proposal["booked_id"] is None
    assert proposal["pending"]["start_at"] == "2026-08-17 09:00"
    assert appointments.upcoming(100) == []

    confirmed = respond("confirm", 1, "patient@example.com", proposal["pending"])
    assert confirmed["booked_id"]
    assert appointments.get(confirmed["booked_id"])["subject_id"] == 1


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
    assert health.json()["version"] == "1.5.0"


def test_cockpit_routes_and_patient_denial(dbs, monkeypatch):
    monkeypatch.setenv("FASTCLINIC_ADMIN_EMAIL", "admin@fastclinic.example")
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_AUTH_ENABLED", "true")
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_EMAIL", "admin@fastclinic.example")
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_PASSWORD", "FastClinic2026$")
    monkeypatch.setenv("FASTCLINIC_SECRET", "test-secret")
    from web.account_auth import accounts
    accounts._seed_bootstrap_account()
    access.set_profile("admin@fastclinic.example", "admin", subject_id=1, clinician_id=7)
    import web_app
    client = StarletteClient(web_app.app)
    signed = client.post(
        "/auth/local/login",
        data={"email": "admin@fastclinic.example", "password": "FastClinic2026$"},
    )
    assert signed.status_code == 200, signed.text
    api_health = client.get("/v1/health", headers={"Host": "api.fastclinic.dev"})
    assert api_health.status_code == 200 and api_health.json()["product"] == "FastClinic"
    api_docs = client.get("/docs", headers={"Host": "api.fastclinic.dev"})
    assert api_docs.status_code == 200 and "Swagger UI" in api_docs.text
    csrf = client.post(
        "/settings/view-as", data={"role": "patient"},
        headers={"Origin": "https://attacker.example", "Sec-Fetch-Site": "cross-site"},
    )
    assert csrf.status_code == 403
    chart = client.get("/patients/1/chart")
    assert chart.status_code == 200
    assert "SOAP" in chart.text or "Chart" in chart.text
    week = client.get("/appointments?clinician_id=7&day=2026-08-17&mode=week")
    assert week.status_code == 200 and "Week overview" in week.text and "Agenda" in week.text
    opened = client.post("/patients/1/chart/open", data={"reason": "Review"}, follow_redirects=True)
    assert opened.status_code == 200
    orders = client.get("/orders")
    assert orders.status_code == 200
    staff = client.get("/admin/staff")
    assert staff.status_code == 200
    preview = client.post("/settings/view-as", data={"role": "patient"}, follow_redirects=False)
    assert preview.status_code == 303 and preview.headers["location"] == "/portal"
    assert client.get("/billing", follow_redirects=False).status_code == 303
    portal = client.get("/portal")
    assert portal.status_code == 200
    assert "Viewing as" in portal.text and "booking assistant" in portal.text.lower()
    assert "Live availability" in portal.text and "Classical" in portal.text
    proposed = client.post(
        "/portal/booking/chat",
        data={"message": "I need practitioner 7 on 2026-08-17 at 10:00"},
        follow_redirects=True,
    )
    assert proposed.status_code == 200 and "Reply" in proposed.text and "confirm" in proposed.text
    classical = client.get("/portal?mode=classical")
    assert classical.status_code == 200 and "Choose a practitioner" in classical.text
    reset = client.post("/settings/view-as", data={"role": "admin"}, follow_redirects=False)
    assert reset.status_code == 303 and reset.headers["location"] == "/"
    for role, visible, hidden in (
        ("practitioner", "Orders", "Users &amp; roles"),
        ("receptionist", "Appointments", "Orders"),
        ("billing", "Billing", "Clinical"),
    ):
        switched = client.post("/settings/view-as", data={"role": role}, follow_redirects=True)
        assert switched.status_code == 200
        assert visible in switched.text and hidden not in switched.text
    client.post("/settings/view-as", data={"role": "admin"})
    with pytest.raises(ValueError, match="cannot be demoted"):
        access.set_profile("admin@fastclinic.example", "patient", subject_id=1)
    # configured admin email always stays admin
    assert access.role_of("admin@fastclinic.example") == "admin"
    access.set_profile("visitor@example.com", "patient", subject_id=1)
    assert access.can("visitor@example.com", "billing") is False
    assert access.home_path("visitor@example.com") == "/portal"

    # Direct mutation URLs enforce record scope, independently of hidden links.
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_EMAIL", "gp@example.com")
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_PASSWORD", "Practitioner2026$")
    accounts._seed_bootstrap_account()
    access.set_profile("gp@example.com", "practitioner", clinician_id=7)
    appointments.book(1, 7, "2026-08-18 09:00", with_reminder=False)
    foreign_order = clinical.place_order(2, "lab", "Private order")
    gp_client = StarletteClient(web_app.app)
    gp_login = gp_client.post("/auth/local/login", data={
        "email": "gp@example.com", "password": "Practitioner2026$",
    })
    assert gp_login.status_code == 200
    denied = gp_client.post(f"/orders/{foreign_order['id']}/complete")
    assert "not available for your role" in denied.text
    assert clinical.order(foreign_order["id"])["status"] == "active"
