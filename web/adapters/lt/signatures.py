"""Clinical legal-signature boundary.

OAuth transport signing and a qualified clinical-document signature are
different controls. The sandbox provider proves integrity only and explicitly
has no legal effect.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime


class SandboxSignatureProvider:
    def sign(
        self, payload: dict, *, practitioner_role_ref: str,
        signed_at: str | None = None,
    ) -> dict:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return {
            "provider": "fastclinic-sandbox-integrity-proof",
            "algorithm": "SHA-256",
            "digest": hashlib.sha256(encoded).hexdigest(),
            "signed_by": practitioner_role_ref,
            "signed_at": signed_at or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "qualified_electronic_signature": False,
            "legal_effect": False,
        }


def require_qualified_signature(proof: dict) -> None:
    if not proof.get("qualified_electronic_signature") or not proof.get("legal_effect"):
        raise ValueError("Production ESPBI submission requires an approved qualified-signature provider")
