from urllib.parse import parse_qs, urlsplit

import pytest

from web import medbackend_oauth


@pytest.fixture()
def oauth_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTCLINIC_OPS_BACKEND", "sqlite")
    monkeypatch.setenv("FASTCLINIC_OPS_DB", str(tmp_path / "ops.sqlite"))
    monkeypatch.setenv("FASTCLINIC_SECRET", "test-secret-that-is-long-enough")
    monkeypatch.setenv("MEDBACKEND_PROJECT_ID", "project-test")
    monkeypatch.setenv("MEDBACKEND_GRAPHQL_URL", "https://backend.example/graphql")
    monkeypatch.setenv("MEDBACKEND_PATIENT_CLIENT_ID", "patient-client")
    monkeypatch.setenv("MEDBACKEND_PATIENT_CLIENT_SECRET", "patient-secret")
    monkeypatch.setenv("MEDBACKEND_PATIENT_AUTH_URL", "https://auth.example/authorize")
    monkeypatch.setenv("MEDBACKEND_PATIENT_TOKEN_URL", "https://auth.example/token")
    monkeypatch.setenv(
        "MEDBACKEND_PATIENT_REDIRECT_URI",
        "https://clinic.example/integrations/medbackend/patient/callback",
    )


def test_begin_uses_authorization_code_pkce_and_one_time_state(oauth_env):
    url = medbackend_oauth.begin("kaljuvee@gmail.com")
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    assert parsed.path == "/authorize"
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"][0]
    assert query["state"][0]
    verifier = medbackend_oauth._consume(query["state"][0], "kaljuvee@gmail.com")
    assert verifier
    with pytest.raises(medbackend_oauth.MedBackendOAuthError, match="invalid or expired"):
        medbackend_oauth._consume(query["state"][0], "kaljuvee@gmail.com")


def test_begin_rejects_another_account(oauth_env):
    with pytest.raises(medbackend_oauth.MedBackendOAuthError, match="another account"):
        medbackend_oauth.begin("someone@example.com")


def test_complete_uses_token_once_and_records_safe_result(oauth_env, monkeypatch):
    state = parse_qs(urlsplit(medbackend_oauth.begin("kaljuvee@gmail.com")).query)["state"][0]

    class Response:
        status_code = 200
        def __init__(self, body):
            self._body = body
        def json(self):
            return self._body

    calls = []
    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/token"):
            return Response({"access_token": "short-lived-token", "token_type": "Bearer"})
        query = kwargs["json"]["query"]
        if "PatientList" in query:
            return Response({"data": {"PatientList": [{"id": "one"}]}})
        return Response({"data": {"Me": {"reference": "Patient/one", "resourceType": "Patient"}}})

    monkeypatch.setattr(medbackend_oauth.requests, "post", fake_post)
    result = medbackend_oauth.complete("one-time-code", state, "kaljuvee@gmail.com")
    assert result["status"] == "connected"
    assert result["patient_count"] == 1
    assert medbackend_oauth.latest("kaljuvee@gmail.com")["status"] == "connected"
    assert all("short-lived-token" not in str(call[1].get("data", {})) for call in calls)

