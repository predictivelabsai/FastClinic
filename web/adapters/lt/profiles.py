"""Lithuanian eLab FHIR R5 sandbox projections.

These builders follow the public profile shape closely enough for deterministic
contract tests. Only the official validator and the profile package version
assigned during onboarding can establish production conformance.
"""
from __future__ import annotations

from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

PROFILE_BASE = "http://esveikata.lt/fhir/StructureDefinition"
PROFILES = {
    "Patient": f"{PROFILE_BASE}/lt-patient",
    "Organization": f"{PROFILE_BASE}/lt-organization",
    "Practitioner": f"{PROFILE_BASE}/lt-practitioner",
    "PractitionerRole": f"{PROFILE_BASE}/lt-practitionerRole",
    "Encounter": f"{PROFILE_BASE}/lt-encounter",
    "ServiceRequest": f"{PROFILE_BASE}/lt-serviceRequest",
    "Provenance": f"{PROFILE_BASE}/lt-provenance",
    "Composition": f"{PROFILE_BASE}/e200-composition",
}
E200_BUNDLE_PROFILE = f"{PROFILE_BASE}/e200-bundle"
FHIR_RELEASE = "5.0.0"
SANDBOX_IG_VERSION = "0.3.36-shape-snapshot"


def apply_lt_profile(resource: dict) -> dict:
    out = deepcopy(resource)
    profile = PROFILES.get(out.get("resourceType"))
    if profile:
        out.setdefault("meta", {})["profile"] = [profile]
    out.setdefault("meta", {}).setdefault("tag", []).append({
        "system": "https://fastclinic.dev/fhir/tag",
        "code": "synthetic-sandbox",
        "display": "Synthetic sandbox data; not production-conformant",
    })
    return out


def e200_order_bundle(fixture: dict, *, recorded_at: str | None = None) -> dict:
    """Build an R5 transaction-shaped E200 laboratory order bundle."""
    stamp = recorded_at or "2026-08-14T06:25:00Z"
    resources = [
        fixture["patient"], fixture["organization"], fixture["practitioner"],
        fixture["practitioner_role"], fixture["encounter"], fixture["lab_order"],
    ]
    composition = {
        "resourceType": "Composition",
        "id": "lt-e200-composition-sandbox-001",
        "status": "final",
        "type": {"coding": [{"system": "http://esveikata.lt/classifiers/DocumentType", "code": "E200"}]},
        "subject": [{"reference": f"Patient/{fixture['patient']['id']}"}],
        "encounter": {"reference": f"Encounter/{fixture['encounter']['id']}"},
        "date": stamp,
        "author": [{"reference": f"PractitionerRole/{fixture['practitioner_role']['id']}"}],
        "title": "Synthetic E200 laboratory order",
        "section": [{
            "title": "Laboratory orders",
            "entry": [{"reference": f"ServiceRequest/{fixture['lab_order']['id']}"}],
        }],
    }
    resources.append(composition)
    provenance = {
        "resourceType": "Provenance",
        "id": "lt-provenance-sandbox-001",
        "target": [
            {"reference": f"Composition/{composition['id']}"},
            {"reference": f"ServiceRequest/{fixture['lab_order']['id']}"},
        ],
        "recorded": stamp,
        "activity": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-DataOperation", "code": "CREATE"}]},
        "agent": [{"who": {"reference": f"PractitionerRole/{fixture['practitioner_role']['id']}"}}],
    }
    resources.append(provenance)
    entries = []
    for resource in resources:
        profiled = apply_lt_profile(resource)
        stable = uuid5(NAMESPACE_URL, f"fastclinic-lt:{profiled['resourceType']}:{profiled['id']}")
        entries.append({
            "fullUrl": f"urn:uuid:{stable}",
            "resource": profiled,
            "request": {"method": "PUT", "url": f"{profiled['resourceType']}/{profiled['id']}"},
        })
    return {
        "resourceType": "Bundle",
        "id": "lt-e200-bundle-sandbox-001",
        "meta": {
            "profile": [E200_BUNDLE_PROFILE],
            "tag": [{"system": "https://fastclinic.dev/fhir/tag", "code": "synthetic-sandbox"}],
        },
        "identifier": {"system": "https://fastclinic.dev/sid/lt/exchange", "value": "LT-E200-SANDBOX-001"},
        "type": "transaction",
        "timestamp": stamp,
        "entry": entries,
    }


def validate_e200_shape(bundle: dict) -> dict:
    errors: list[str] = []
    if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "transaction":
        errors.append("E200 must be a FHIR transaction Bundle")
    resources = [entry.get("resource", {}) for entry in bundle.get("entry") or []]
    kinds = {resource.get("resourceType") for resource in resources}
    required = {"Patient", "Organization", "Practitioner", "PractitionerRole", "Encounter", "ServiceRequest", "Composition", "Provenance"}
    for kind in sorted(required - kinds):
        errors.append(f"missing required {kind}")
    for entry in bundle.get("entry") or []:
        if not str(entry.get("fullUrl", "")).startswith("urn:uuid:"):
            errors.append("every transaction entry requires a urn:uuid fullUrl")
        if entry.get("request", {}).get("method") not in {"POST", "PUT"}:
            errors.append("every transaction entry requires a POST or PUT request")
    provenance = next((r for r in resources if r.get("resourceType") == "Provenance"), {})
    if not provenance.get("target") or not provenance.get("agent"):
        errors.append("Provenance requires target and agent")
    return {
        "valid": not errors,
        "fhir_release": FHIR_RELEASE,
        "sandbox_ig_version": SANDBOX_IG_VERSION,
        "errors": errors,
        "official_validator_run": False,
    }
