"""SMS provider abstraction — Twilio and VoodooSMS.

Env vars (set whichever provider you want to use):

  Twilio:
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_FROM_NUMBER     e.g. +447123456789

  VoodooSMS:
    VOODOO_SMS_API_KEY
    VOODOO_SMS_FROM        sender name/number, max 11 chars
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger("sms")

PROVIDERS = ["twilio", "voodoo"]


@dataclass
class SmsResult:
    ok: bool
    provider: str
    message_id: str = ""
    error: str = ""


def available_providers() -> list[str]:
    out = []
    if os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN"):
        out.append("twilio")
    if os.getenv("VOODOO_SMS_API_KEY"):
        out.append("voodoo")
    return out


def send(to: str, body: str, provider: str = "twilio") -> SmsResult:
    to = to.strip().replace(" ", "")
    if not to.startswith("+"):
        to = "+" + to
    if provider == "twilio":
        return _send_twilio(to, body)
    elif provider == "voodoo":
        return _send_voodoo(to, body)
    return SmsResult(ok=False, provider=provider, error=f"Unknown provider: {provider}")


def _send_twilio(to: str, body: str) -> SmsResult:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_FROM_NUMBER", "")
    if not sid or not token or not from_number:
        return SmsResult(ok=False, provider="twilio",
                         error="Missing TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, or TWILIO_FROM_NUMBER")
    try:
        r = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            auth=(sid, token),
            data={"To": to, "From": from_number, "Body": body},
            timeout=15,
        )
        data = r.json()
        if r.status_code in (200, 201):
            return SmsResult(ok=True, provider="twilio",
                             message_id=data.get("sid", ""))
        return SmsResult(ok=False, provider="twilio",
                         error=data.get("message", f"HTTP {r.status_code}"))
    except Exception as e:
        logger.exception("Twilio send failed")
        return SmsResult(ok=False, provider="twilio", error=str(e))


def _send_voodoo(to: str, body: str) -> SmsResult:
    api_key = os.getenv("VOODOO_SMS_API_KEY", "")
    sender = os.getenv("VOODOO_SMS_FROM", "FastClinic")
    if not api_key:
        return SmsResult(ok=False, provider="voodoo",
                         error="Missing VOODOO_SMS_API_KEY")
    # Strip leading '+' — VoodooSMS expects numeric-only destination
    dest = to.lstrip("+")
    try:
        r = requests.post(
            "https://api.voodoosms.com/sendsms",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "to": int(dest),
                "from": sender,
                "msg": body,
            },
            timeout=15,
        )
        data = r.json()
        if r.status_code in (200, 201):
            return SmsResult(ok=True, provider="voodoo",
                             message_id=str(data.get("reference_id", data.get("id", ""))))
        return SmsResult(ok=False, provider="voodoo",
                         error=data.get("message", data.get("error", f"HTTP {r.status_code}")))
    except Exception as e:
        logger.exception("VoodooSMS send failed")
        return SmsResult(ok=False, provider="voodoo", error=str(e))
