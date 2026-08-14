"""UK Core R4 profiles and GP Connect STU3 translation.

The FastClinic core emits vanilla R4. This module is the country layer:

* UK Core R4 — rewrite identifier systems, meta.profile, relationship codes.
* GP Connect STU3 — translate that UK Core view onto CareConnect STU3
  resources. The two FHIR versions are not compatible; this is a real map,
  not a profile swap.

Live spine I/O is in ``live.py`` and stays gated.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from web.fhir.resources import NATIONAL_ID_SYSTEM

NHS_NUMBER_SYSTEM = "https://fhir.nhs.uk/Id/nhs-number"
UK_CORE = "https://fhir.hl7.org.uk/StructureDefinition"
CARECONNECT = "https://fhir.nhs.uk/STU3/StructureDefinition"
VERIFICATION_EXT = f"{UK_CORE}/Extension-UKCore-NHSNumberVerificationStatus"
VERIFICATION_CS = "https://fhir.hl7.org.uk/CodeSystem/UKCore-NHSNumberVerificationStatusEngland"

UK_CORE_PROFILES = {
    "Patient": f"{UK_CORE}/UKCore-Patient",
    "RelatedPerson": f"{UK_CORE}/UKCore-RelatedPerson",
    "Person": f"{UK_CORE}/UKCore-Person",
    "Practitioner": f"{UK_CORE}/UKCore-Practitioner",
    "PractitionerRole": f"{UK_CORE}/UKCore-PractitionerRole",
    "Organization": f"{UK_CORE}/UKCore-Organization",
    "Encounter": f"{UK_CORE}/UKCore-Encounter",
    "Condition": f"{UK_CORE}/UKCore-Condition",
    "Procedure": f"{UK_CORE}/UKCore-Procedure",
    "Observation": f"{UK_CORE}/UKCore-Observation",
    "Immunization": f"{UK_CORE}/UKCore-Immunization",
    "ImmunizationRecommendation": f"{UK_CORE}/UKCore-ImmunizationRecommendation",
    "Appointment": f"{UK_CORE}/UKCore-Appointment",
    "Consent": f"{UK_CORE}/UKCore-Consent",
    "ServiceRequest": f"{UK_CORE}/UKCore-ServiceRequest",
    "MedicationRequest": f"{UK_CORE}/UKCore-MedicationRequest",
    "DocumentReference": f"{UK_CORE}/UKCore-DocumentReference",
    "Communication": f"{UK_CORE}/UKCore-Communication",
    "CommunicationRequest": f"{UK_CORE}/UKCore-CommunicationRequest",
    "Task": f"{UK_CORE}/UKCore-Task",
}

# CareConnect-GPC profiles that exist for Access Record: Structured (STU3).
STU3_PROFILES = {
    "Patient": f"{CARECONNECT}/CareConnect-GPC-Patient-1",
    "RelatedPerson": f"{CARECONNECT}/CareConnect-GPC-RelatedPerson-1",
    "Practitioner": f"{CARECONNECT}/CareConnect-GPC-Practitioner-1",
    "PractitionerRole": f"{CARECONNECT}/CareConnect-GPC-PractitionerRole-1",
    "Organization": f"{CARECONNECT}/CareConnect-GPC-Organization-1",
    "Encounter": f"{CARECONNECT}/CareConnect-GPC-Encounter-1",
    "Condition": f"{CARECONNECT}/CareConnect-GPC-ProblemHeader-Condition-1",
    "Immunization": f"{CARECONNECT}/CareConnect-GPC-Immunization-1",
    "Observation": f"{CARECONNECT}/CareConnect-GPC-Observation-1",
    "AllergyIntolerance": f"{CARECONNECT}/CareConnect-GPC-AllergyIntolerance-1",
    "MedicationStatement": f"{CARECONNECT}/CareConnect-GPC-MedicationStatement-1",
    "Appointment": f"{CARECONNECT}/CareConnect-GPC-Appointment-1",
}

# Core role → UK relationship coding. Base R4 ships no `guardian` code;
# national codes stay in this adapter.
ROLE_TO_UK = {
    "guardian": [
        {"system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
         "code": "PRN", "display": "parent"},
        {"system": "http://terminology.hl7.org/CodeSystem/v3-RoleClass",
         "code": "GUARD", "display": "guardian"},
    ],
    "next_of_kin": [
        {"system": "http://terminology.hl7.org/CodeSystem/v2-0131",
         "code": "N", "display": "Next-of-Kin"},
    ],
    "payer": [
        {"system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
         "code": "PAYOR", "display": "invoice payor"},
    ],
    "carer": [
        {"system": "http://snomed.info/sct",
         "code": "133932002", "display": "Carer"},
    ],
    "emergency": [
        {"system": "http://terminology.hl7.org/CodeSystem/v2-0131",
         "code": "C", "display": "Emergency Contact"},
    ],
    "family": [
        {"system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
         "code": "FAMMEMB", "display": "family member"},
    ],
    "owner": [
        {"system": "http://terminology.hl7.org/CodeSystem/v3-NullFlavor",
         "code": "OTH", "display": "other"},
    ],
    "other": [
        {"system": "http://terminology.hl7.org/CodeSystem/v3-NullFlavor",
         "code": "OTH", "display": "other"},
    ],
}

STU3_ENCOUNTER_STATUS = {
    "unknown": "finished",
    "triaged": "arrived",
    "onleave": "onleave",
}


def as_uk_core(resource: dict, *, traced: bool = False) -> dict:
    """Copy an R4 resource and apply UK Core profiles + NHS Number system."""
    out = deepcopy(resource)
    kind = out.get("resourceType")
    profile = UK_CORE_PROFILES.get(kind)
    if profile:
        meta = out.setdefault("meta", {})
        meta["profile"] = [profile]
    _rewrite_nhs_number(out, traced=traced)
    if kind == "RelatedPerson":
        _rewrite_relationship(out)
    if kind == "Bundle":
        for entry in out.get("entry") or []:
            inner = entry.get("resource")
            if isinstance(inner, dict):
                entry["resource"] = as_uk_core(inner, traced=traced)
    return out


def as_gpconnect_stu3(resource: dict, *, traced: bool = False) -> dict:
    """Translate a UK-Core-or-core R4 resource to a GP Connect STU3 view."""
    uk = as_uk_core(resource, traced=traced)
    kind = uk.get("resourceType")
    if kind == "Bundle":
        uk["meta"] = {"profile": [f"{CARECONNECT}/GPConnect-StructuredRecord-Bundle-1"]}
        for entry in uk.get("entry") or []:
            inner = entry.get("resource")
            if isinstance(inner, dict):
                entry["resource"] = as_gpconnect_stu3(inner, traced=traced)
        return uk
    if kind in {"ServiceRequest", "MedicationRequest", "Task", "CommunicationRequest"}:
        return _stu3_request_fallback(uk)
    if kind == "ImmunizationRecommendation":
        return _stu3_immunization_recommendation(uk)
    if kind == "Person":
        # Person is R4 linkage; GP Connect Structured has no Person. Drop it
        # from STU3 views — RelatedPerson already carries the relationship.
        uk["meta"] = {"tag": [{"system": "https://fastclinic.dev/fhir/tag",
                               "code": "dropped-for-stu3",
                               "display": "Person is R4 linkage-only; omitted from GP Connect STU3"}]}
        return uk
    profile = STU3_PROFILES.get(kind)
    if profile:
        uk.setdefault("meta", {})["profile"] = [profile]
    if kind == "Encounter":
        status = uk.get("status")
        uk["status"] = STU3_ENCOUNTER_STATUS.get(status, status)
        # STU3 Encounter.class is a required Coding — already is in our R4.
    if kind == "Appointment" and uk.get("status") == "waitlist":
        uk["status"] = "pending"
    uk["meta"]["tag"] = [{
        "system": "http://hl7.org/fhir/ValueSet/FHIR-version",
        "code": "3.0.1",
        "display": "STU3",
    }]
    return uk


def core_role_from_uk(resource: dict) -> str:
    """Inverse of ROLE_TO_UK for inbound GP Connect / UK Core RelatedPerson."""
    for rel in resource.get("relationship") or []:
        for coding in rel.get("coding") or []:
            code = (coding.get("code") or "").upper()
            if code in {"PRN", "GUARD", "GRD"}:
                return "guardian"
            if code in {"N"}:
                return "next_of_kin"
            if code in {"PAYOR"}:
                return "payer"
            if code in {"133932002"}:
                return "carer"
            if code in {"C"}:
                return "emergency"
            if code in {"FAMMEMB"}:
                return "family"
            if code in {"OTH"}:
                return "other"
        text = (rel.get("text") or "").lower()
        if "guardian" in text or "parent" in text:
            return "guardian"
    return "other"


def _rewrite_nhs_number(resource: dict, *, traced: bool) -> None:
    identifiers = resource.get("identifier") or []
    for ident in identifiers:
        if ident.get("system") == NATIONAL_ID_SYSTEM or ident.get("system") == NHS_NUMBER_SYSTEM:
            ident["system"] = NHS_NUMBER_SYSTEM
            ident["use"] = "official"
            status_code = "01" if traced else "02"
            status_display = (
                "Number present and verified" if traced
                else "Number present but not traced"
            )
            ident["extension"] = [{
                "url": VERIFICATION_EXT,
                "valueCodeableConcept": {
                    "coding": [{
                        "system": VERIFICATION_CS,
                        "code": status_code,
                        "display": status_display,
                    }]
                },
            }]


def _rewrite_relationship(resource: dict) -> None:
    current = resource.get("relationship") or []
    role = None
    for rel in current:
        for coding in rel.get("coding") or []:
            if "fastclinic.dev/sid/party-role" in (coding.get("system") or ""):
                role = coding.get("code")
    if not role:
        return
    mapped = ROLE_TO_UK.get(role)
    if not mapped:
        return
    resource["relationship"] = [{
        "coding": mapped,
        "text": role.replace("_", " "),
    }]


def _stu3_immunization_recommendation(resource: dict) -> dict:
    """R4 dateCriterion → STU3 recommendation.date (the structural split)."""
    out = deepcopy(resource)
    out.setdefault("meta", {})["profile"] = [
        f"{CARECONNECT}/CareConnect-GPC-ImmunizationRecommendation-1"
    ]
    recs = []
    for rec in out.get("recommendation") or []:
        mapped = deepcopy(rec)
        criteria = mapped.pop("dateCriterion", None) or []
        if criteria and not mapped.get("date"):
            mapped["date"] = criteria[0].get("value")
        # STU3 uses date (0..1), not dateCriterion.
        recs.append(mapped)
    out["recommendation"] = recs
    return out


def _stu3_request_fallback(resource: dict) -> dict:
    """Resources with no CareConnect-GPC profile become a tagged STU3 Task."""
    out = deepcopy(resource)
    original = out.get("resourceType")
    out["meta"] = {
        "profile": [f"{CARECONNECT}/CareConnect-GPC-Task-1"] if original == "Task"
        else [f"{UK_CORE}/UKCore-{original}"],
        "tag": [{
            "system": "https://fastclinic.dev/fhir/tag",
            "code": "no-gpconnect-profile",
            "display": f"{original} has no CareConnect-GPC STU3 profile; left as translated R4",
        }],
    }
    return out


def relationship_codes(role: str) -> list[dict[str, Any]]:
    return ROLE_TO_UK.get(role, ROLE_TO_UK["other"])
