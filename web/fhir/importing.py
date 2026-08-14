"""FHIR R4 → FastClinic core mapping (and structural validation).

Import is a translation, not a write. Callers decide whether to persist the
returned core rows. Clinical replica tables stay read-mostly; only subject /
party / role mappings are considered apply-safe.

Document-Bundle file ingest (Terviseportaal HTML→FHIR, replay-safe PostgreSQL
load) lives in ``web.fhir.ingress`` and ``scripts/import_fhir_r4.py``.
"""
from __future__ import annotations

from typing import Any

from web.fhir.resources import NATIONAL_ID_SYSTEM, RESOURCE_TYPES

APPLY_SAFE = frozenset({"Patient", "RelatedPerson"})


def validate_resource(resource: dict) -> dict:
    """Return an OperationOutcome for a resource dict."""
    issues = list(_issues(resource))
    return {
        "resourceType": "OperationOutcome",
        "issue": issues or [{
            "severity": "information",
            "code": "informational",
            "diagnostics": "Resource is structurally acceptable for FastClinic mapping.",
        }],
    }


def import_resource(resource: dict) -> dict:
    """Translate one FHIR resource into core-shaped dictionaries.

    Returns ``{resourceType, id, apply_safe, core, issues}``. ``core`` uses
    FastClinic nouns (subject / party / role / consultation / …).
    """
    if not isinstance(resource, dict):
        raise ValueError("resource must be a JSON object")
    kind = resource.get("resourceType")
    issues = list(_issues(resource))
    fatal = [i for i in issues if i.get("severity") in {"error", "fatal"}]
    if fatal:
        return {
            "resourceType": kind,
            "id": resource.get("id"),
            "apply_safe": False,
            "core": {},
            "issues": issues,
        }
    mapper = {
        "Patient": _patient,
        "RelatedPerson": _related,
        "Person": _person,
        "Encounter": _encounter,
        "Condition": _condition,
        "Appointment": _appointment,
        "Consent": _consent,
        "Bundle": _bundle,
    }.get(kind, _generic)
    core = mapper(resource)
    return {
        "resourceType": kind,
        "id": resource.get("id"),
        "apply_safe": kind in APPLY_SAFE and not fatal,
        "core": core,
        "issues": issues,
    }


def _issues(resource: Any):
    if not isinstance(resource, dict):
        yield _issue("fatal", "invalid", "Resource is not a JSON object")
        return
    kind = resource.get("resourceType")
    if not kind:
        yield _issue("error", "required", "resourceType is required")
        return
    if kind not in RESOURCE_TYPES:
        yield _issue("error", "not-supported", f"resourceType {kind} is not mapped")
        return
    if kind == "Patient" and not (_name_text(resource) or resource.get("identifier")):
        yield _issue("error", "required", "Patient needs a name or identifier")
    if kind == "Encounter" and not resource.get("status"):
        yield _issue("error", "required", "Encounter.status is required")
    if kind == "Encounter" and not resource.get("class"):
        yield _issue("error", "required", "Encounter.class is required")
    if kind == "ImmunizationRecommendation":
        recs = resource.get("recommendation") or []
        if not recs:
            yield _issue("error", "required", "recommendation is required")
        elif not recs[0].get("forecastStatus"):
            yield _issue("error", "required", "forecastStatus is a modifier element")
    if kind == "RelatedPerson" and not _reference_id(resource.get("patient")):
        yield _issue("error", "required", "RelatedPerson.patient is 1..1")
    if kind == "Bundle":
        if not resource.get("type"):
            yield _issue("error", "required", "Bundle.type is required")
        for index, entry in enumerate(resource.get("entry") or []):
            inner = entry.get("resource") if isinstance(entry, dict) else None
            if not inner:
                yield _issue("error", "required", f"Bundle.entry[{index}] has no resource")
                continue
            for issue in _issues(inner):
                issue["diagnostics"] = f"entry[{index}]: {issue['diagnostics']}"
                yield issue


def _patient(resource: dict) -> dict:
    name = _name_text(resource)
    national = _identifier(resource, NATIONAL_ID_SYSTEM) or _identifier_by_type(resource, "NH")
    deceased = resource.get("deceasedDateTime")
    return {
        "subject": {
            "official_name": name,
            "gender": _gender_in(resource.get("gender")),
            "date_of_birth": (resource.get("birthDate") or "")[:10] or None,
            "nhs_number": national,
            "deceased_at": deceased,
            "archived": 0 if resource.get("active", True) else 1,
            **_address_fields(resource),
        }
    }


def _related(resource: dict) -> dict:
    role = _role_in(resource)
    return {
        "party": {
            "name": _name_text(resource),
            **_telecom_fields(resource),
            **_address_fields(resource),
        },
        "subject_party_role": {
            "subject_id": _reference_id(resource.get("patient")),
            "role": role,
            "is_primary": 1 if role in {"guardian", "self"} else 0,
        },
    }


def _person(resource: dict) -> dict:
    return {
        "party": {
            "name": _name_text(resource),
            **_telecom_fields(resource),
            **_address_fields(resource),
        },
        "links": [
            link.get("target", {}).get("reference")
            for link in resource.get("link") or []
            if isinstance(link, dict)
        ],
    }


def _encounter(resource: dict) -> dict:
    period = resource.get("period") or {}
    return {
        "consultation": {
            "id": _maybe_int(resource.get("id")),
            "subject_id": _reference_id(resource.get("subject")),
            "consult_at": period.get("start"),
            "clinician_id": _first_participant(resource),
            "is_visit": 1,
        }
    }


def _condition(resource: dict) -> dict:
    code = resource.get("code") or {}
    coding = (code.get("coding") or [{}])[0]
    return {
        "diagnosis": {
            "id": _maybe_int(resource.get("id")),
            "subject_id": _reference_id(resource.get("subject")),
            "consultation_id": _reference_id(resource.get("encounter")),
            "code": coding.get("code"),
            "name": code.get("text") or coding.get("display"),
            "diagnosis_at": resource.get("recordedDate") or resource.get("onsetDateTime"),
        }
    }


def _appointment(resource: dict) -> dict:
    status_map = {
        "booked": "scheduled",
        "pending": "scheduled",
        "arrived": "confirmed",
        "fulfilled": "completed",
        "cancelled": "cancelled",
        "noshow": "cancelled",
    }
    subject_id = None
    clinician_id = None
    for part in resource.get("participant") or []:
        actor = (part or {}).get("actor") or {}
        ref = actor.get("reference") or ""
        if ref.startswith("Patient/"):
            subject_id = _reference_id(actor)
        elif ref.startswith("Practitioner/"):
            clinician_id = _reference_id(actor)
    return {
        "appointment": {
            "subject_id": subject_id,
            "clinician_id": clinician_id,
            "start_at": resource.get("start"),
            "end_at": resource.get("end"),
            "status": status_map.get(resource.get("status") or "", "scheduled"),
            "reason": resource.get("description") or "",
        }
    }


def _consent(resource: dict) -> dict:
    provision = resource.get("provision") or {}
    return {
        "party": {
            "marketing_opt_out": 1 if provision.get("type") == "deny" else 0,
        }
    }


def _bundle(resource: dict) -> dict:
    mapped = []
    for entry in resource.get("entry") or []:
        inner = entry.get("resource") if isinstance(entry, dict) else None
        if inner:
            mapped.append(import_resource(inner))
    return {"entries": mapped}


def _generic(resource: dict) -> dict:
    return {
        "unmapped": {
            "resourceType": resource.get("resourceType"),
            "id": resource.get("id"),
        }
    }


def _issue(severity: str, code: str, diagnostics: str) -> dict:
    return {"severity": severity, "code": code, "diagnostics": diagnostics}


def _name_text(resource: dict) -> str | None:
    names = resource.get("name") or []
    if not names:
        return None
    first = names[0]
    if first.get("text"):
        return first["text"]
    given = " ".join(first.get("given") or [])
    family = first.get("family") or ""
    text = f"{given} {family}".strip()
    return text or None


def _identifier(resource: dict, system: str) -> str | None:
    for ident in resource.get("identifier") or []:
        if ident.get("system") == system and ident.get("value"):
            return str(ident["value"])
    return None


def _identifier_by_type(resource: dict, type_code: str) -> str | None:
    for ident in resource.get("identifier") or []:
        for coding in ((ident.get("type") or {}).get("coding") or []):
            if coding.get("code") == type_code and ident.get("value"):
                return str(ident["value"])
    return None


def _address_fields(resource: dict) -> dict:
    addresses = resource.get("address") or []
    if not addresses:
        return {}
    addr = addresses[0]
    lines = addr.get("line") or []
    return {
        "street_address": lines[0] if lines else None,
        "street_address_2": lines[1] if len(lines) > 1 else None,
        "city": addr.get("city"),
        "zip_code": addr.get("postalCode"),
        "state": addr.get("state"),
        "country_region": addr.get("country"),
    }


def _telecom_fields(resource: dict) -> dict:
    phone = email = None
    for item in resource.get("telecom") or []:
        if item.get("system") == "phone" and not phone:
            phone = item.get("value")
        if item.get("system") == "email" and not email:
            email = item.get("value")
    return {"phone": phone, "email": email}


def _gender_in(value: str | None) -> str | None:
    return {"male": "1", "female": "3"}.get((value or "").lower())


def _role_in(resource: dict) -> str:
    """Map FHIR relationship codings back onto the core role enum."""
    for rel in resource.get("relationship") or []:
        for coding in rel.get("coding") or []:
            code = (coding.get("code") or "").upper()
            system = coding.get("system") or ""
            if "fastclinic.dev/sid/party-role" in system:
                return coding.get("code") or "other"
            if code in {"PRN", "GUARD", "GRD"}:
                return "guardian"
            if code in {"N", "NOK", "NXT"}:
                return "next_of_kin"
            if code in {"PAYOR", "PAYE"}:
                return "payer"
            if code in {"C"} and "0131" in system:
                return "emergency"
            if code in {"FAMMEMB", "FAM"}:
                return "family"
            if code in {"ONESELF", "SELF"}:
                return "self"
        text = (rel.get("text") or "").lower()
        for role in ("guardian", "payer", "carer", "owner", "family", "emergency", "self"):
            if role in text:
                return role
            if role == "carer" and "next of kin" in text:
                return "next_of_kin"
    return "other"


def _reference_id(value) -> int | None:
    if not value:
        return None
    if isinstance(value, dict):
        ref = value.get("reference") or ""
    else:
        ref = str(value)
    tail = ref.rsplit("/", 1)[-1]
    return _maybe_int(tail)


def _maybe_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_participant(resource: dict) -> int | None:
    for part in resource.get("participant") or []:
        ident = _reference_id((part or {}).get("individual") or (part or {}).get("actor"))
        if ident is not None:
            return ident
    return None
