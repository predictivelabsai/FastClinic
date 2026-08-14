"""Estonian TIS/MPI/X-Road sandbox tests."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from web.adapters import exchange
from web.adapters.base import AdapterNotAvailable
from web.adapters.ee import adapter, live
from web.adapters.ee.cda import HL7_NS
from web.adapters.ee.identifiers import _check_digit, verify_personal_code
from web.adapters.ee.xroad import headers, mpi_urls
from web.adapters.registry import available_countries, get_adapter
from web.api import api


@pytest.fixture()
def sandbox_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTCLINIC_OPS_DB", str(tmp_path / "operations.sqlite"))
    monkeypatch.setenv("FASTCLINIC_OPS_BACKEND", "sqlite")
    monkeypatch.setenv("FASTSME_API_TOKEN", "sandbox-write-token")
    return tmp_path


def test_estonia_registered_and_status_is_non_production(monkeypatch):
    monkeypatch.delenv("EE_TIS_LIVE_ENABLED", raising=False)
    assert "EE" in available_countries()
    assert get_adapter("EE") is adapter
    status = adapter.status()
    assert status["national_system"] == "Tervise infosüsteem (TIS)"
    assert status["production_conformant"] is False
    assert status["surfaces"]["live_tis"] == "blocked"


def test_estonian_personal_code_validation_and_masking():
    base = "3900101001"
    value = base + str(_check_digit(base))
    result = verify_personal_code(value)
    assert result["valid"] is True
    assert result["birth_date"] == "1990-01-01"
    assert value not in str(result)
    assert verify_personal_code("39002310000")["reason"] == "invalid_encoded_birth_date"


def test_cda_fixture_is_namespace_correct_xml_and_validates():
    fixture = adapter.fixture(surface="tis")
    payload = fixture["payload"]
    root = ET.fromstring(payload["cda_xml"])
    assert root.tag == f"{{{HL7_NS}}}ClinicalDocument"
    assert root.find(f"{{{HL7_NS}}}recordTarget") is not None
    outcome = adapter.validate(surface="tis", payload=payload)
    assert outcome["valid"] is True
    assert outcome["official_validator_run"] is False
    assert "not for TIS submission" in payload["cda_xml"]


def test_mpi_fixture_is_r5_trial_use_preview():
    payload = adapter.fixture(surface="mpi")["payload"]
    assert payload["fhir_release"] == "5.0.0"
    assert payload["production_conformant"] is False
    assert payload["resource"]["meta"]["profile"] == [
        "https://fhir.ee/mpi/StructureDefinition/ee-mpi-patient-verified"
    ]
    assert "OFFICIAL-TEHIK-TEST-USER-REQUIRED" in str(payload["authorization_request"])
    assert adapter.validate(surface="mpi", payload=payload)["valid"] is True


def test_xroad_context_requires_member_path_and_purpose():
    result = headers(
        client="ee-dev/COM/12345678/fastclinic", user_personal_code="test-user",
        issue="treatment test", request_id="test-request-id",
    )
    assert result["X-Road-Client"] == "ee-dev/COM/12345678/fastclinic"
    assert result["X-Road-Issue"] == "treatment test"
    assert mpi_urls(security_server="https://security.invalid/")["mpi"].endswith("/tis/mpi")
    with pytest.raises(ValueError, match="INSTANCE/CLASS"):
        headers(client="bad", user_personal_code="test", issue="test")
    with pytest.raises(ValueError, match="purpose"):
        headers(client="ee-dev/COM/1/x", user_personal_code="test", issue="")


def test_estonian_exchange_uses_shared_country_ledger(sandbox_db):
    result = adapter.sandbox_submit(surface="tis", idempotency_key="ee-stable-key-001")
    assert result["country_code"] == "EE"
    assert result["status"] == "accepted"
    replay = adapter.sandbox_submit(surface="tis", idempotency_key="ee-stable-key-001")
    assert replay["id"] == result["id"]
    assert exchange.list_exchanges(country_code="LT") == []
    assert len(exchange.list_exchanges(country_code="EE")) == 1


def test_estonia_live_transport_is_fail_closed(monkeypatch):
    monkeypatch.setenv("EE_TIS_LIVE_ENABLED", "true")
    for name in live.REQUIRED:
        monkeypatch.setenv(name, "configured-for-test")
    with pytest.raises(AdapterNotAvailable, match="disabled"):
        live.submit({"synthetic": True})


def test_estonian_http_sandbox_contract(sandbox_db):
    client = TestClient(api)
    assert client.get("/v1/adapters/EE/status").status_code == 200
    preview = client.get("/v1/adapters/EE/xroad-preview")
    assert preview.status_code == 200
    assert preview.json()["sent"] is False
    fixture = client.get("/v1/adapters/EE/fixtures/outpatient?surface=tis")
    assert fixture.status_code == 200
    created = client.post(
        "/v1/adapters/EE/sandbox/submissions",
        headers={"Authorization": "Bearer sandbox-write-token", "Idempotency-Key": "ee-api-key-001"},
        json={"surface": "tis"},
    )
    assert created.status_code == 201, created.text
    listing = client.get(
        "/v1/adapters/EE/sandbox/submissions",
        headers={"Authorization": "Bearer sandbox-write-token"},
    )
    assert listing.status_code == 200
    assert listing.json()["meta"]["total"] == 1
