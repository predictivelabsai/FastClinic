"""ESPBI OAuth 1.0 signing boundary.

The legacy transport details are isolated here so the rest of FastClinic does
not depend on them. Sandbox proofs are intentionally not accepted for live I/O.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, urlsplit


def oauth_body_hash(body: bytes) -> str:
    return base64.b64encode(hashlib.sha1(body).digest()).decode("ascii")


def signature_base(method: str, url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    base_url = f"{parts.scheme}://{parts.netloc}{parts.path}"
    combined = list(parse_qsl(parts.query, keep_blank_values=True)) + list(params.items())
    normalized = "&".join(
        f"{_escape(key)}={_escape(value)}"
        for key, value in sorted((str(k), str(v)) for k, v in combined)
    )
    return "&".join((_escape(method.upper()), _escape(base_url), _escape(normalized)))


@dataclass
class OAuthRequestSigner:
    consumer_key: str
    private_key_pem: bytes

    def authorization_header(
        self, method: str, url: str, body: bytes, *, requestor_id: str,
        nonce: str | None = None, timestamp: int | None = None,
    ) -> str:
        params = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_nonce": nonce or secrets.token_hex(16),
            "oauth_signature_method": "RSA-SHA1",
            "oauth_timestamp": str(timestamp or int(time.time())),
            "oauth_version": "1.0",
            "oauth_body_hash": oauth_body_hash(body),
            "requestor_id": requestor_id,
        }
        signature = self._sign(signature_base(method, url, params))
        params["oauth_signature"] = signature
        return "OAuth " + ", ".join(
            f'{_escape(key)}="{_escape(value)}"' for key, value in sorted(params.items())
        )

    def _sign(self, base: str) -> str:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError as exc:  # pragma: no cover - deployment guard
            raise RuntimeError("ESPBI RSA signing requires the cryptography package") from exc
        private_key = serialization.load_pem_private_key(self.private_key_pem, password=None)
        raw = private_key.sign(base.encode("utf-8"), padding.PKCS1v15(), hashes.SHA1())
        return base64.b64encode(raw).decode("ascii")


def _escape(value: str) -> str:
    return quote(str(value), safe="~-._")
