"""MedBackend OAuth 2.0/OIDC bearer validation for FastClinic mobile APIs."""
from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException, Security, status
from fastapi.security import OAuth2AuthorizationCodeBearer

from web import access


oauth2 = OAuth2AuthorizationCodeBearer(
    authorizationUrl=os.getenv("MEDBACKEND_PATIENT_AUTH_URL") or "https://dev-auth.medbackend.com/oauth/patient/authorize",
    tokenUrl=os.getenv("MEDBACKEND_PATIENT_TOKEN_URL") or "https://dev-auth.medbackend.com/oauth/patient/token",
    scopes={"openid": "Identify the signed-in user", "profile": "Read the user's FastClinic profile"},
    auto_error=False,
)


def _unauthorized(message: str = "A valid MedBackend access token is required"):
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "invalid_mobile_token", "message": message, "details": {}},
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_mobile_principal(token: str | None = Security(oauth2)) -> dict[str, Any]:
    """Validate a MedBackend JWT and resolve its email to fail-closed local RBAC."""
    if not token:
        _unauthorized()
    jwks_url = (os.getenv("MEDBACKEND_PATIENT_JWKS_URL") or "").strip()
    audience = (os.getenv("MEDBACKEND_PATIENT_CLIENT_ID") or "").strip()
    if not jwks_url or not audience:
        raise HTTPException(
            status_code=503,
            detail={"code": "mobile_auth_unavailable", "message": "Mobile OAuth is not configured", "details": {}},
        )
    try:
        import jwt
        key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(token).key
        options = {"require": ["exp", "sub"], "verify_iss": bool(os.getenv("MEDBACKEND_PATIENT_ISSUER"))}
        claims = jwt.decode(
            token, key, algorithms=["RS256", "ES256"], audience=audience,
            issuer=os.getenv("MEDBACKEND_PATIENT_ISSUER") or None, options=options,
        )
    except Exception:
        _unauthorized()
    email = str(claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    if not email:
        _unauthorized("The access token does not contain an account email")
    profile = access.profile(email)
    if profile["role"] == "patient" and not profile.get("subject_id"):
        raise HTTPException(
            status_code=403,
            detail={"code": "patient_not_linked", "message": "This account is not linked to a FastClinic patient", "details": {}},
        )
    return {**profile, "claims": {"sub": claims["sub"]}}
