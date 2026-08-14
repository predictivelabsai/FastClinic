"""Lithuanian identifier validation and privacy-safe display helpers.

An ``asmens kodas`` is an external identifier, never a FastClinic primary key.
Sandbox fixtures deliberately do not contain a real-looking personal code: an
official ESPBI test patient must be supplied during onboarding.
"""
from __future__ import annotations

from datetime import date

PERSONAL_CODE_SYSTEM = "http://esveikata.lt/Identifier/PersonalCode"
ESPBI_PATIENT_SYSTEM = "http://esveikata.lt/Identifier/Patient/ESPBI"
ESI_SYSTEM = "http://esveikata.lt/Identifier/Patient/ESI"
ORGANIZATION_ESPBI_SYSTEM = "http://esveikata.lt/Identifier/ESPBI"
JAR_SYSTEM = "https://fastclinic.dev/sid/lt/jar-code"
SYNTHETIC_ID_SYSTEM = "https://fastclinic.dev/sid/lt/synthetic"


def verify_personal_code(value: str) -> dict:
    """Validate the structure, encoded birth date and two-pass checksum.

    The result never echoes the complete identifier, which keeps API logs and
    browser traces from becoming an accidental identifier store.
    """
    raw = "".join(ch for ch in str(value or "") if ch.isdigit())
    result = {
        "valid": False,
        "masked": mask_identifier(raw),
        "system": PERSONAL_CODE_SYSTEM,
        "traced": False,
        "source": "local-structure-check",
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


def mask_identifier(value: str) -> str:
    text = str(value or "")
    if len(text) < 4:
        return "*" * len(text)
    return f"{text[:2]}{'*' * (len(text) - 4)}{text[-2:]}"


def _check_digit(base: str) -> int:
    digits = [int(ch) for ch in base]
    first = sum(a * b for a, b in zip(digits, (1, 2, 3, 4, 5, 6, 7, 8, 9, 1))) % 11
    if first != 10:
        return first
    second = sum(a * b for a, b in zip(digits, (3, 4, 5, 6, 7, 8, 9, 1, 2, 3))) % 11
    return 0 if second == 10 else second
