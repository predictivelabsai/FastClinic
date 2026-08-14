"""Estonian personal-code structural validation and safe display."""
from __future__ import annotations

from datetime import date

PERSONAL_CODE_SYSTEM = "https://fhir.ee/sid/pid/est/ni"
SYNTHETIC_ID_SYSTEM = "https://fastclinic.dev/sid/ee/synthetic"


def verify_personal_code(value: str) -> dict:
    raw = "".join(ch for ch in str(value or "") if ch.isdigit())
    result = {
        "valid": False, "masked": _mask(raw), "system": PERSONAL_CODE_SYSTEM,
        "traced": False, "source": "local-structure-check",
    }
    if len(raw) != 11:
        return {**result, "reason": "must_be_11_digits"}
    century = {1: 1800, 2: 1800, 3: 1900, 4: 1900, 5: 2000, 6: 2000}.get(int(raw[0]))
    if century is None:
        return {**result, "reason": "invalid_gender_century_digit"}
    try:
        born = date(century + int(raw[1:3]), int(raw[3:5]), int(raw[5:7]))
    except ValueError:
        return {**result, "reason": "invalid_encoded_birth_date"}
    if _check_digit(raw[:10]) != int(raw[-1]):
        return {**result, "reason": "checksum_failed", "birth_date": born.isoformat()}
    return {**result, "valid": True, "reason": None, "birth_date": born.isoformat()}


def _check_digit(base: str) -> int:
    digits = [int(ch) for ch in base]
    value = sum(a * b for a, b in zip(digits, (1, 2, 3, 4, 5, 6, 7, 8, 9, 1))) % 11
    if value != 10:
        return value
    value = sum(a * b for a, b in zip(digits, (3, 4, 5, 6, 7, 8, 9, 1, 2, 3))) % 11
    return 0 if value == 10 else value


def _mask(value: str) -> str:
    return f"{value[:2]}{'*' * max(0, len(value) - 4)}{value[-2:]}" if len(value) >= 4 else "*" * len(value)
