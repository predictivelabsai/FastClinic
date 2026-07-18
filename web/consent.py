"""Marketing-consent enforcement — the single source of truth.

`party.marketing_opt_out` records a contact's withdrawal of consent to
marketing / activation messages. It is enforced in two independent layers:

  1. **Query time** — the activation engines append `sql_filter()` so opted-out
     contacts never enter a campaign list or CSV export.
  2. **Send time** — `check_phone()` / `check_email()` gate the SMS and email
     routes, so an ad-hoc send to a suppressed contact is refused even when the
     number was pasted in by hand.

Two layers, because a filter in one query is a filter someone forgets to add to
the next one. The send boundary is the chokepoint that cannot be routed around.

Scope: this flag governs **marketing / activation outreach only**. Clinical and
transactional messages (appointment confirmations, test results, safety recalls)
are a different lawful basis and are not covered here. When such a path is added
it must bypass these helpers *deliberately*, and say so at the call site.
"""
from __future__ import annotations

from web.db import query, scalar


def sql_filter(party_alias: str = "pt") -> str:
    """SQL fragment excluding opted-out contacts. Assumes a joined party row.

    Written as `COALESCE(... , 0) = 0` so a LEFT JOIN miss (patient with no
    contact record) is treated as *not* opted out — matching the existing engine
    behaviour, which lists such patients with a blank phone. They cannot be
    messaged anyway; the send-time guard is what actually protects them.
    """
    return f"AND COALESCE({party_alias}.marketing_opt_out, 0) = 0"


def opted_out_count() -> int:
    """Contacts who have opted out of marketing, clinic-wide."""
    return scalar("SELECT COUNT(*) FROM party WHERE marketing_opt_out = 1") or 0


def _digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _phone_key(phone: str) -> str:
    """Comparable form of a phone number.

    Stored numbers are E.164 (+447890779946). A human may type 07890779946 or
    07890 779946 for the same person, so compare on the trailing national digits
    and ignore the country prefix and formatting.
    """
    d = _digits(phone)
    return d[-9:] if len(d) >= 9 else d


def is_suppressed_phone(phone: str) -> bool:
    key = _phone_key(phone)
    if not key:
        return False
    rows = query(
        "SELECT phone FROM party WHERE marketing_opt_out = 1 AND phone IS NOT NULL"
    )
    return any(_phone_key(r["phone"]) == key for r in rows)


def is_suppressed_email(email: str) -> bool:
    e = (email or "").strip().lower()
    if not e:
        return False
    return bool(
        scalar(
            "SELECT COUNT(*) FROM party "
            "WHERE marketing_opt_out = 1 AND LOWER(TRIM(email)) = ?",
            (e,),
        )
    )


SUPPRESSED_MSG = (
    "This contact has opted out of marketing messages. "
    "Sending was blocked. Clinical messages must go through a clinical channel."
)


def check_phone(phone: str) -> str | None:
    """Return an error message if this number must not be marketed to."""
    return SUPPRESSED_MSG if is_suppressed_phone(phone) else None


def check_email(email: str) -> str | None:
    return SUPPRESSED_MSG if is_suppressed_email(email) else None
