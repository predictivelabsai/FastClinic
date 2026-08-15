"""Opt-in MedBackend patient OAuth and GraphQL integration checks.

Run the non-destructive live checks with::

    MEDBACKEND_LIVE_TEST=1 python -m dotenv run -- \
      pytest -q tests/medbackend_test.py --tb=line

MedBackend issues patient tokens through the OAuth 2.0 authorization-code
grant; ``client_credentials`` is not supported and neither is PKCE, because
the patient client is confidential.  A browser is not required either:
``POST /oauth/{project_uid}/{entity_type}/login`` takes the patient's
credentials and answers with JSON ``{"redirect_url": "...?code=...&state=..."}``
-- no 302 to follow -- and the authorization code parsed out of it is then
exchanged at the token endpoint for an RS256 access token.  That makes the whole
flow scriptable, so no hand-pasted one-time code is needed.

Set ``MEDBACKEND_PATIENT_EMAIL`` / ``MEDBACKEND_PATIENT_PASSWORD`` for a
verified patient account, or short-circuit the login with a short-lived
``MEDBACKEND_PATIENT_ACCESS_TOKEN``.  No secret, password or token is included
in assertion messages or output.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

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

# Supplied per environment, never committed: a verified patient account plus the
# redirect URI registered on the MedBackend user flow.
CREDENTIALS = (
    "MEDBACKEND_PATIENT_EMAIL",
    "MEDBACKEND_PATIENT_PASSWORD",
    "MEDBACKEND_PATIENT_REDIRECT_URI",
)

OAUTH_STATE = "fastclinic-integration-check"


@dataclass(frozen=True)
class OAuthResult:
    """Secrets stay in memory for the duration of one live test session."""

    access_token: str
    authorization_code_received: bool
    source: str


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


def _credentials() -> dict[str, str]:
    missing = [name for name in CREDENTIALS if not os.getenv(name)]
    if missing:
        pytest.skip(f"set {', '.join(missing)} to exercise the patient login flow")
    return {name: os.environ[name] for name in CREDENTIALS}


def _login_url(config: dict[str, str]) -> str:
    """``/login`` is a sibling of the configured ``/token`` endpoint."""
    return config["MEDBACKEND_PATIENT_TOKEN_URL"].rsplit("/", 1)[0] + "/login"


def _server_error(response: requests.Response) -> str:
    """Server-supplied error text only -- request payloads are never echoed."""
    try:
        body = response.json()
    except ValueError:
        return "<non-JSON response>"
    return body.get("error_description") or body.get("error") or body.get("message") or "<no error field>"


def _authorization_code(config: dict[str, str], credentials: dict[str, str]) -> str:
    """Log the patient in and return the one-time authorization code.

    The code lives 5 minutes and is consumed by the first exchange, so it is
    fetched fresh per test rather than carried in the environment.
    """
    __tracebackhide__ = True
    response = requests.post(
        _login_url(config),
        json={
            "email": credentials["MEDBACKEND_PATIENT_EMAIL"],
            "password": credentials["MEDBACKEND_PATIENT_PASSWORD"],
            "redirect_uri": credentials["MEDBACKEND_PATIENT_REDIRECT_URI"],
            "state": OAUTH_STATE,
        },
        timeout=20,
    )
    # 404 means the project or the Patient user flow is missing, 401 bad
    # credentials, 403 an unverified or half-provisioned account.
    assert response.status_code == 200, (
        f"patient login failed with HTTP {response.status_code}: {_server_error(response)}"
    )
    redirect_url = response.json().get("redirect_url", "")
    query = parse_qs(urlparse(redirect_url).query)
    assert query.get("state") == [OAUTH_STATE], "login redirect did not preserve OAuth state"
    code = query.get("code", [""])[0]
    assert code, "login succeeded but the redirect_url carried no authorization code"
    return code


def _exchange_code(config: dict[str, str], credentials: dict[str, str], code: str) -> str:
    __tracebackhide__ = True
    response = requests.post(
        config["MEDBACKEND_PATIENT_TOKEN_URL"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            # Compared byte for byte against the URI sent to /login.
            "redirect_uri": credentials["MEDBACKEND_PATIENT_REDIRECT_URI"],
            "client_id": config["MEDBACKEND_PATIENT_CLIENT_ID"],
            "client_secret": config["MEDBACKEND_PATIENT_CLIENT_SECRET"],
        },
        timeout=20,
    )
    assert response.status_code == 200, (
        f"patient token exchange failed with HTTP {response.status_code}: {_server_error(response)}"
    )
    body = response.json()
    assert body.get("access_token"), "token exchange returned no access_token"
    assert body.get("token_type", "Bearer").lower() == "bearer"
    return body["access_token"]


def _oauth_result(config: dict[str, str]) -> OAuthResult:
    __tracebackhide__ = True
    token = os.getenv("MEDBACKEND_PATIENT_ACCESS_TOKEN")
    if token:
        return OAuthResult(token, False, "injected_access_token")
    credentials = _credentials()
    code = _authorization_code(config, credentials)
    token = _exchange_code(config, credentials, code)
    return OAuthResult(token, True, "authorization_code")


@pytest.fixture(scope="session")
def live_oauth() -> OAuthResult:
    """Drive one OAuth transaction and reuse only its in-memory access token.

    Fetching one result per session matters because authorization codes are
    short-lived and single-use.  It also avoids performing multiple password
    logins merely because several assertions exercise the same flow.
    """
    return _oauth_result(_config())


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


def test_patient_login_issues_authorization_code(live_oauth: OAuthResult):
    if live_oauth.source == "injected_access_token":
        pytest.skip("an injected access token bypasses the authorization-code login")
    assert live_oauth.authorization_code_received


def test_patient_authorization_code_exchange(live_oauth: OAuthResult):
    assert live_oauth.access_token


def test_patient_list_graphql(live_oauth: OAuthResult):
    config = _config()
    response = requests.post(
        config["MEDBACKEND_GRAPHQL_URL"],
        headers={
            "Authorization": f"Bearer {live_oauth.access_token}",
            "Content-Type": "application/json",
            # Must equal the project_uid claim in the token; backbone rejects a
            # mismatch before it resolves anything.
            "X-Project-ID": config["MEDBACKEND_PROJECT_ID"],
        },
        json={"query": "{ PatientList { id } }"},
        timeout=20,
    )
    assert response.status_code == 200, f"GraphQL request failed with HTTP {response.status_code}"
    body = response.json()
    # GraphQL answers 200 even when it refuses the query, so errors come first.
    errors = body.get("errors") or []
    assert not errors, f"GraphQL returned errors: {[error.get('message') for error in errors]}"
    # A patient token is compartment-scoped: this lists the caller, not a roster.
    assert isinstance((body.get("data") or {}).get("PatientList"), list)
