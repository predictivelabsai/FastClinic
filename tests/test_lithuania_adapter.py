"""Lithuanian ESPBI/IPR/eLab sandbox and API contract tests."""
from __future__ import annotations

import base64
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from web.adapters import exchange
from web.adapters.base import AdapterNotAvailable
from web.adapters.lt import adapter, live
from web.adapters.lt.auth import OAuthRequestSigner, oauth_body_hash, signature_base
from web.adapters.lt.identifiers import _check_digit, verify_personal_code
from web.adapters.lt.signatures import SandboxSignatureProvider, require_qualified_signature
from web.adapters.registry import get_adapter
from web.api import api


@pytest.fixture()
def sandbox_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTCLINIC_OPS_DB", str(tmp_path / "operations.sqlite"))
    monkeypatch.setenv("FASTCLINIC_OPS_BACKEND", "sqlite")
    monkeypatch.setenv("FASTSME_API_TOKEN", "sandbox-write-token")
    return tmp_path


def test_registry_and_status_are_explicitly_non_production(monkeypatch):
    monkeypatch.delenv("LT_ESPBI_LIVE_ENABLED", raising=False)
    assert get_adapter("LT") is adapter
    status = adapter.status()
    assert status["national_system"] == "E. sveikata / ESPBI IS"
    assert status["production_conformant"] is False
    assert status["surfaces"]["elab_fhir_r5_e200_projection"] == "available_sandbox"
    assert status["surfaces"]["live_espbi"] == "blocked"


def test_lithuanian_personal_code_validation_never_echoes_identifier():
    base = "3990101001"
    value = base + str(_check_digit(base))
    result = verify_personal_code(value)
    assert result["valid"] is True
    assert result["birth_date"] == "1999-01-01"
    assert value not in str(result)
    assert verify_personal_code(value[:-1] + str((int(value[-1]) + 1) % 10))["reason"] == "checksum_failed"
    assert verify_personal_code("39902310000")["reason"] == "invalid_encoded_birth_date"


@pytest.mark.parametrize("surface,document_type", [
    ("espbi", "E025"), ("espbi", "E027"), ("espbi", "E063"),
    ("elab", "E200"), ("ipr", "IPR"),
])
def test_all_lithuanian_fixture_surfaces_validate(surface, document_type):
    fixture = adapter.fixture(surface=surface, document_type=document_type)
    assert fixture["synthetic"] is True
    outcome = adapter.validate(surface=surface, payload=fixture["payload"])
    assert outcome["valid"] is True, outcome
    assert outcome["official_validator_run"] is False


def test_elab_is_r5_transaction_with_provenance_and_sandbox_markers():
    payload = adapter.fixture(surface="elab")["payload"]
    assert payload["type"] == "transaction"
    resources = [entry["resource"] for entry in payload["entry"]]
    kinds = {resource["resourceType"] for resource in resources}
    assert {"Composition", "ServiceRequest", "Provenance", "PractitionerRole"}.issubset(kinds)
    provenance = next(resource for resource in resources if resource["resourceType"] == "Provenance")
    assert provenance["agent"][0]["who"]["reference"].startswith("PractitionerRole/")
    assert all(entry["fullUrl"].startswith("urn:uuid:") for entry in payload["entry"])


def test_sandbox_signature_has_integrity_but_no_legal_effect():
    proof = SandboxSignatureProvider().sign({"synthetic": True}, practitioner_role_ref="PractitionerRole/test")
    assert proof["qualified_electronic_signature"] is False
    assert proof["legal_effect"] is False
    with pytest.raises(ValueError, match="qualified-signature"):
        require_qualified_signature(proof)


def test_oauth_rsa_signing_header_and_body_hash():
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    body = b'{"resourceType":"Patient"}'
    signer = OAuthRequestSigner("synthetic-consumer", pem)
    header = signer.authorization_header(
        "POST", "https://sandbox.invalid/fhir", body,
        requestor_id="Practitioner/test", nonce="fixed", timestamp=1700000000,
    )
    assert header.startswith("OAuth ")
    fields = {}
    for item in header.removeprefix("OAuth ").split(", "):
        key, value = item.split("=", 1)
        fields[unquote(key)] = unquote(value.strip('"'))
    assert fields["oauth_body_hash"] == oauth_body_hash(body)
    unsigned = {key: value for key, value in fields.items() if key != "oauth_signature"}
    base = signature_base("POST", "https://sandbox.invalid/fhir", unsigned)
    private.public_key().verify(
        base64.b64decode(fields["oauth_signature"]), base.encode(),
        padding.PKCS1v15(), hashes.SHA1(),
    )


def test_exchange_is_idempotent_and_reconcilable(sandbox_db):
    first = adapter.sandbox_submit(
        surface="espbi", document_type="E025", idempotency_key="lt-stable-key-001",
    )
    replay = adapter.sandbox_submit(
        surface="espbi", document_type="E025", idempotency_key="lt-stable-key-001",
    )
    assert first["id"] == replay["id"]
    assert replay["idempotent_replay"] is True
    assert first["request"]["_fastclinicSandboxSignature"]["legal_effect"] is False
    reconciled = exchange.reconcile(first["id"], country_code="LT")
    assert reconciled["status"] == "reconciled"
    assert reconciled["response"]["national_document_id"].startswith("SYNTHETIC-LT-E025")


def test_same_idempotency_key_with_different_payload_conflicts(sandbox_db):
    adapter.sandbox_submit(surface="espbi", document_type="E025", idempotency_key="lt-conflict-001")
    payload = adapter.fixture(surface="espbi", document_type="E025")["payload"]
    payload["clinical_document"]["status"] = "amended"
    with pytest.raises(exchange.IdempotencyConflict):
        adapter.sandbox_submit(
            surface="espbi", document_type="E025", payload=payload,
            idempotency_key="lt-conflict-001",
        )


def test_live_transport_is_fail_closed(monkeypatch):
    monkeypatch.setenv("LT_ESPBI_LIVE_ENABLED", "true")
    for name in live.REQUIRED:
        monkeypatch.setenv(name, "configured-for-test")
    with pytest.raises(AdapterNotAvailable, match="deliberately disabled"):
        live.submit({"synthetic": True})


def test_lithuanian_http_sandbox_contract(sandbox_db):
    client = TestClient(api)
    status = client.get("/v1/adapters/LT/status")
    assert status.status_code == 200
    fixture = client.get("/v1/adapters/LT/fixtures/outpatient?surface=elab")
    assert fixture.status_code == 200
    assert fixture.json()["document_type"] == "E200"
    unauthorized = client.post(
        "/v1/adapters/LT/sandbox/submissions",
        headers={"Idempotency-Key": "lt-api-key-001"},
        json={"surface": "espbi", "document_type": "E025"},
    )
    assert unauthorized.status_code == 401
    created = client.post(
        "/v1/adapters/LT/sandbox/submissions",
        headers={"Authorization": "Bearer sandbox-write-token", "Idempotency-Key": "lt-api-key-001"},
        json={"surface": "espbi", "document_type": "E025"},
    )
    assert created.status_code == 201, created.text
    exchange_id = created.json()["id"]
    reconciled = client.post(
        f"/v1/adapters/LT/sandbox/submissions/{exchange_id}/reconcile",
        headers={"Authorization": "Bearer sandbox-write-token"},
    )
    assert reconciled.status_code == 200
    assert reconciled.json()["status"] == "reconciled"
