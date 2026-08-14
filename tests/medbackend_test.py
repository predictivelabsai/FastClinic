"""Opt-in MedBackend patient OAuth and GraphQL integration checks.

Run the non-destructive live checks with::

    set -a; source .env; set +a
    MEDBACKEND_LIVE_TEST=1 pytest -q tests/medbackend_test.py

The patient client uses authorization-code OAuth; its client secret cannot be
tested with ``client_credentials``.  To exercise token exchange, provide a
fresh one-time ``MEDBACKEND_PATIENT_AUTHORIZATION_CODE``.  Alternatively set a
short-lived ``MEDBACKEND_PATIENT_ACCESS_TOKEN`` to exercise GraphQL directly.
No secret, code, or token is included in assertion messages or output.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest
import requests


pytestmark = pytest.mark.skipif(
    os.getenv("MEDBACKEND_LIVE_TEST") != "1",
    reason="set MEDBACKEND_LIVE_TEST=1 to call the MedBackend development service",
)

REQUIRED = (
    "MEDBACKEND_PROJECT_ID",
    "MEDBACKEND_GRAPHQL_URL",
    "MEDBACKEND_PATIENT_CLIENT_ID",
    "MEDBACKEND_PATIENT_CLIENT_SECRET",
    "MEDBACKEND_PATIENT_AUTH_URL",
    "MEDBACKEND_PATIENT_TOKEN_URL",
    "MEDBACKEND_PATIENT_JWKS_URL",
)


def _config() -> dict[str, str]:
    missing = [name for name in REQUIRED if not os.getenv(name)]
    assert not missing, f"Missing MedBackend settings: {', '.join(missing)}"
    values = {name: os.environ[name] for name in REQUIRED}
    for name in (
        "MEDBACKEND_GRAPHQL_URL", "MEDBACKEND_PATIENT_AUTH_URL",
        "MEDBACKEND_PATIENT_TOKEN_URL", "MEDBACKEND_PATIENT_JWKS_URL",
    ):
        parsed = urlparse(values[name])
        assert parsed.scheme == "https" and parsed.netloc, f"{name} must be an HTTPS URL"
    return values


def _token_from_authorization_code(config: dict[str, str]) -> str:
    code = os.getenv("MEDBACKEND_PATIENT_AUTHORIZATION_CODE")
    if not code:
        pytest.skip("provide a fresh MEDBACKEND_PATIENT_AUTHORIZATION_CODE")
    redirect_uri = os.getenv("MEDBACKEND_PATIENT_REDIRECT_URI")
    if not redirect_uri:
        pytest.skip("configure MEDBACKEND_PATIENT_REDIRECT_URI")
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": config["MEDBACKEND_PATIENT_CLIENT_ID"],
        "client_secret": config["MEDBACKEND_PATIENT_CLIENT_SECRET"],
    }
    verifier = os.getenv("MEDBACKEND_PATIENT_CODE_VERIFIER")
    if verifier:
        form["code_verifier"] = verifier
    response = requests.post(config["MEDBACKEND_PATIENT_TOKEN_URL"], data=form, timeout=20)
    assert response.status_code == 200, f"patient token exchange failed with HTTP {response.status_code}"
    body = response.json()
    assert body.get("access_token") and body.get("token_type", "Bearer").lower() == "bearer"
    return body["access_token"]


def test_patient_oauth_configuration_is_complete():
    config = _config()
    assert config["MEDBACKEND_PATIENT_CLIENT_SECRET"].strip()


def test_patient_jwks_is_reachable():
    config = _config()
    response = requests.get(config["MEDBACKEND_PATIENT_JWKS_URL"], timeout=20)
    assert response.status_code == 200
    keys = response.json().get("keys")
    assert isinstance(keys, list) and keys, "JWKS response contains no signing keys"
    assert all(key.get("kid") and key.get("kty") for key in keys)


def test_patient_authorization_code_exchange():
    token = _token_from_authorization_code(_config())
    assert token


def test_patient_list_graphql():
    config = _config()
    token = os.getenv("MEDBACKEND_PATIENT_ACCESS_TOKEN")
    if not token:
        code = os.getenv("MEDBACKEND_PATIENT_AUTHORIZATION_CODE")
        if not code:
            pytest.skip("provide MEDBACKEND_PATIENT_ACCESS_TOKEN or a fresh authorization code")
        token = _token_from_authorization_code(config)
    response = requests.post(
        config["MEDBACKEND_GRAPHQL_URL"],
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Project-ID": config["MEDBACKEND_PROJECT_ID"],
        },
        json={"query": "{ PatientList { id } }"},
        timeout=20,
    )
    assert response.status_code == 200, f"GraphQL request failed with HTTP {response.status_code}"
    body = response.json()
    assert not body.get("errors"), "GraphQL returned errors"
    assert isinstance((body.get("data") or {}).get("PatientList"), list)
