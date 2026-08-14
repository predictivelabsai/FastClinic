"""NHS Number validation — modulus 11, no network.

The algorithm is published by NHS Digital and does not require spine access.
A valid check digit is *not* a PDS match; `traced` stays false until live.py
is onboarded.
"""
from __future__ import annotations

import re

WEIGHTS = (10, 9, 8, 7, 6, 5, 4, 3, 2)


def digits_only(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def format_nhs_number(value: str | None) -> str | None:
    digits = digits_only(value)
    if len(digits) != 10:
        return None
    return f"{digits[:3]} {digits[3:6]} {digits[6:]}"


def nhs_number_valid(value: str | None) -> bool:
    return verify_nhs_number(value)["valid"]


def verify_nhs_number(value: str | None) -> dict:
    """Return a structured modulus-11 result.

    The last digit is the check digit. Remainder 10 is always invalid
    (NHS numbers are never issued with that remainder).
    """
    raw = (value or "").strip()
    digits = digits_only(raw)
    if not raw:
        return _result(False, "", None, "empty")
    if len(digits) != 10:
        return _result(False, digits, None, "must_be_10_digits")
    if digits == "0000000000":
        return _result(False, digits, format_nhs_number(digits), "all_zero")
    total = sum(int(d) * w for d, w in zip(digits[:9], WEIGHTS))
    remainder = total % 11
    check = 11 - remainder
    if check == 11:
        check = 0
    if check == 10:
        return _result(False, digits, format_nhs_number(digits), "remainder_10")
    if check != int(digits[9]):
        return _result(False, digits, format_nhs_number(digits), "bad_check_digit")
    return _result(True, digits, format_nhs_number(digits), None)


def _result(valid: bool, digits: str, formatted: str | None, reason: str | None) -> dict:
    return {
        "valid": valid,
        "nhs_number": digits or None,
        "formatted": formatted,
        "reason": reason,
        "source": "modulus-11",
        "traced": False,
    }
