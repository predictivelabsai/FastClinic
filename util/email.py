"""Email provider abstraction — Postmark.

Used by the Email Broadcaster and the activation engines to send reminder /
win-back / follow-up emails from a verified FastClinic domain.

Env vars:
    POSTMARK_API_TOKEN     Postmark Server API token (sends mail)
    POSTMARK_FROM          From address, e.g. clinic@fastclinic.example
    POSTMARK_FROM_NAME     Display name, e.g. "FastClinic"
    EMAIL_REPLY_TO         Reply-To address (optional)
    POSTMARK_MESSAGE_STREAM  Stream id (optional, default "outbound")

The sending domain (fastclinic.example) is DKIM + Return-Path verified in Postmark,
so any @fastclinic.example From address is allowed.
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger("email")

POSTMARK_URL = "https://api.postmarkapp.com/email"


@dataclass
class EmailResult:
    ok: bool
    provider: str = "postmark"
    message_id: str = ""
    error: str = ""


def is_configured() -> bool:
    return bool(os.getenv("POSTMARK_API_TOKEN") and os.getenv("POSTMARK_FROM"))


def config_summary() -> dict:
    """Non-secret view of the current email config, for the admin/broadcaster UI."""
    return {
        "configured": is_configured(),
        "from": os.getenv("POSTMARK_FROM", ""),
        "from_name": os.getenv("POSTMARK_FROM_NAME", ""),
        "reply_to": os.getenv("EMAIL_REPLY_TO", ""),
        "stream": os.getenv("POSTMARK_MESSAGE_STREAM", "outbound"),
        "token_set": bool(os.getenv("POSTMARK_API_TOKEN")),
    }


def _from_header() -> str:
    addr = os.getenv("POSTMARK_FROM", "")
    name = os.getenv("POSTMARK_FROM_NAME", "")
    return f"{name} <{addr}>" if name and addr else addr


def send(to: str, subject: str, body: str, *, html: bool = False) -> EmailResult:
    """Send a single email via Postmark. `body` is plain text unless html=True."""
    token = os.getenv("POSTMARK_API_TOKEN", "")
    from_addr = os.getenv("POSTMARK_FROM", "")
    to = (to or "").strip()
    if not token or not from_addr:
        return EmailResult(ok=False, error="Missing POSTMARK_API_TOKEN or POSTMARK_FROM")
    if not to or not subject.strip() or not body.strip():
        return EmailResult(ok=False, error="Recipient, subject, and body are required")

    payload = {
        "From": _from_header(),
        "To": to,
        "Subject": subject,
        "MessageStream": os.getenv("POSTMARK_MESSAGE_STREAM", "outbound"),
    }
    payload["HtmlBody" if html else "TextBody"] = body
    reply_to = os.getenv("EMAIL_REPLY_TO", "")
    if reply_to:
        payload["ReplyTo"] = reply_to

    try:
        r = requests.post(
            POSTMARK_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": token,
            },
            json=payload,
            timeout=15,
        )
        data = r.json() if r.content else {}
        # Postmark returns ErrorCode 0 on success (HTTP 200).
        if r.status_code == 200 and data.get("ErrorCode", 1) == 0:
            return EmailResult(ok=True, message_id=data.get("MessageID", ""))
        return EmailResult(ok=False, error=data.get("Message", f"HTTP {r.status_code}"))
    except Exception as e:
        logger.exception("Postmark send failed")
        return EmailResult(ok=False, error=str(e))
