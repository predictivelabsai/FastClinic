"""Server-side OAuth 2.0 + PKCE connectivity check for MedBackend patients."""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from urllib.parse import urlencode

import requests
from web.ops_db import connect

TEST_EMAIL = "kaljuvee@gmail.com"
TRANSACTION_TTL = 300


class MedBackendOAuthError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise MedBackendOAuthError(f"{name} is not configured")
    return value


def configured() -> bool:
    return all(os.getenv(name) for name in (
        "MEDBACKEND_PROJECT_ID", "MEDBACKEND_GRAPHQL_URL",
        "MEDBACKEND_PATIENT_CLIENT_ID", "MEDBACKEND_PATIENT_CLIENT_SECRET",
        "MEDBACKEND_PATIENT_AUTH_URL", "MEDBACKEND_PATIENT_TOKEN_URL",
        "MEDBACKEND_PATIENT_REDIRECT_URI",
    ))


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def begin(email: str) -> str:
    email = (email or "").strip().lower()
    allowed = (os.getenv("MEDBACKEND_OAUTH_TEST_EMAIL") or TEST_EMAIL).strip().lower()
    if email != allowed:
        raise MedBackendOAuthError("this MedBackend patient test is assigned to another account")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    now = int(time.time())
    with connect() as db:
        db.execute(
            "DELETE FROM medbackend_oauth_transaction WHERE expires_at<? OR used_at IS NOT NULL",
            (now,),
        )
        db.execute(
            """INSERT INTO medbackend_oauth_transaction(
                 state_hash,account_email,code_verifier,expires_at,created_at
               ) VALUES(?,?,?,?,?)""",
            (hashlib.sha256(state.encode()).hexdigest(), email,
             verifier, now + TRANSACTION_TTL, now),
        )
        db.commit()
    query = {
        "response_type": "code",
        "client_id": _required("MEDBACKEND_PATIENT_CLIENT_ID"),
        "redirect_uri": _required("MEDBACKEND_PATIENT_REDIRECT_URI"),
        "scope": os.getenv("MEDBACKEND_PATIENT_SCOPES") or "openid profile patient/*.read",
        "state": state,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
    }
    return f"{_required('MEDBACKEND_PATIENT_AUTH_URL')}?{urlencode(query)}"


def _consume(state: str, email: str) -> str:
    now = int(time.time())
    digest = hashlib.sha256((state or "").encode()).hexdigest()
    with connect() as db:
        row = db.execute(
            """SELECT state_hash,account_email,code_verifier FROM medbackend_oauth_transaction
               WHERE state_hash=? AND account_email=? AND used_at IS NULL AND expires_at>?""",
            (digest, email.strip().lower(), now),
        ).fetchone()
        if not row:
            raise MedBackendOAuthError("OAuth state is invalid or expired")
        db.execute(
            "UPDATE medbackend_oauth_transaction SET used_at=? WHERE state_hash=?",
            (now, digest),
        )
        db.commit()
    return row["code_verifier"]


def _graphql(token: str, query: str) -> dict:
    response = requests.post(
        _required("MEDBACKEND_GRAPHQL_URL"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Project-ID": _required("MEDBACKEND_PROJECT_ID"),
        },
        json={"query": query}, timeout=20,
    )
    if response.status_code != 200:
        raise MedBackendOAuthError(f"GraphQL connectivity returned HTTP {response.status_code}")
    body = response.json()
    if body.get("errors"):
        raise MedBackendOAuthError("GraphQL connectivity returned an authorization or schema error")
    return body.get("data") or {}


def complete(code: str, state: str, email: str) -> dict:
    verifier = _consume(state, email)
    response = requests.post(
        _required("MEDBACKEND_PATIENT_TOKEN_URL"),
        data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": _required("MEDBACKEND_PATIENT_REDIRECT_URI"),
            "client_id": _required("MEDBACKEND_PATIENT_CLIENT_ID"),
            "client_secret": _required("MEDBACKEND_PATIENT_CLIENT_SECRET"),
            "code_verifier": verifier,
        }, timeout=20,
    )
    if response.status_code != 200:
        _record(email, "failed", None, None, f"token_http_{response.status_code}")
        raise MedBackendOAuthError(f"patient token exchange returned HTTP {response.status_code}")
    token = response.json().get("access_token")
    if not token:
        _record(email, "failed", None, None, "missing_access_token")
        raise MedBackendOAuthError("patient token exchange returned no access token")
    identity = _graphql(token, "{ Me { reference resourceType } }").get("Me") or {}
    patients = _graphql(token, "{ PatientList { id } }").get("PatientList") or []
    result = {
        "status": "connected", "identity_reference": identity.get("reference"),
        "patient_count": len(patients),
    }
    _record(email, result["status"], result["identity_reference"], result["patient_count"], None)
    return result


def _record(email: str, status: str, identity: str | None,
            patient_count: int | None, error_code: str | None) -> None:
    with connect() as db:
        db.execute(
            """INSERT INTO medbackend_connection_audit(
                 account_email,status,identity_reference,patient_count,error_code,tested_at
               ) VALUES(?,?,?,?,?,?)""",
            (email.strip().lower(), status, identity, patient_count, error_code, int(time.time())),
        )
        db.commit()


def latest(email: str) -> dict | None:
    with connect() as db:
        row = db.execute(
            """SELECT status,patient_count,error_code,tested_at
               FROM medbackend_connection_audit WHERE account_email=?
               ORDER BY id DESC LIMIT 1""",
            (email.strip().lower(),),
        ).fetchone()
        return dict(row) if row else None
