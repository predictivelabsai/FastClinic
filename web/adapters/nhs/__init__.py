"""NHS / UK country adapter — Clinic OS Phase 5b.

Internally version-split:

* ``ukcore_r4`` — UK Core profiles + PDS identifier systems (R4)
* ``gpconnect_stu3`` — GP Connect Access Record: Structured (STU3)

Live PDS / GP Connect / IM1 / SSP calls raise ``AdapterNotAvailable`` until
onboarding credentials exist. Mapping, NHS Number check-digits, export,
import, and reminder projection work fully offline against synthetic data.
"""
from __future__ import annotations

from web.adapters.base import AdapterNotAvailable
from web.adapters.nhs import live
from web.adapters.nhs.identifiers import format_nhs_number, verify_nhs_number
from web.adapters.nhs.profiles import (
    NHS_NUMBER_SYSTEM,
    as_gpconnect_stu3,
    as_uk_core,
    core_role_from_uk,
)

country_code = "GB"
fhir_release = "STU3+R4"


class NhsAdapter:
    """Concrete ``CountryAdapter`` for the UK."""

    country_code = country_code
    fhir_release = fhir_release

    def verify_identifier(self, value: str) -> dict:
        result = verify_nhs_number(value)
        result["system"] = NHS_NUMBER_SYSTEM
        result["formatted"] = result.get("formatted") or format_nhs_number(value)
        if result["valid"] and live.live_enabled() and not live.missing_live_config()["pds"]:
            # Onboarding is the only thing that turns a check-digit into a trace.
            traced = live.pds_lookup(result["nhs_number"])
            result.update(traced)
            result["traced"] = True
            result["source"] = "pds"
        return result

    def export_subject(self, subject_id: int, *, release: str = "r4") -> list[dict]:
        from web import fhir

        resources = fhir.export_subject(int(subject_id), include_ops=True)
        traced = False
        if release and str(release).lower() in {"stu3", "st3", "gpc", "gpconnect"}:
            return [as_gpconnect_stu3(resource, traced=traced) for resource in resources]
        return [as_uk_core(resource, traced=traced) for resource in resources]

    def import_record(self, resource: dict) -> dict:
        from web import fhir

        inbound = dict(resource)
        if inbound.get("resourceType") == "RelatedPerson":
            # Re-assert the core role before the generic importer sees UK codes.
            inbound = dict(inbound)
            inbound.setdefault("relationship", [])
            inbound["relationship"] = [{
                "coding": [{
                    "system": "https://fastclinic.dev/sid/party-role",
                    "code": core_role_from_uk(resource),
                }]
            }] + list(inbound.get("relationship") or [])
        mapped = fhir.import_resource(inbound)
        if inbound.get("resourceType") == "Patient":
            nhs = None
            for ident in inbound.get("identifier") or []:
                if ident.get("system") == NHS_NUMBER_SYSTEM and ident.get("value"):
                    nhs = ident["value"]
            if nhs and mapped.get("core", {}).get("subject") is not None:
                mapped["core"]["subject"]["nhs_number"] = nhs
        mapped["adapter"] = "nhs"
        mapped["fhir_release"] = inbound.get("meta", {}).get("tag", [{}])
        return mapped

    def push_reminder(self, reminder_id: int) -> dict:
        from web import activation_loop
        from web.fhir.resources import reminder_resource

        row = activation_loop.get_reminder(int(reminder_id))
        if not row:
            raise AdapterNotAvailable(f"Reminder {reminder_id} was not found")
        projected = reminder_resource(row)
        uk = as_uk_core(projected)
        # A real spine write would go through live.push_to_spine. That stays
        # gated; the projection itself is the adapter's job and is offline.
        return {
            "reminder_id": int(reminder_id),
            "projected": uk,
            "stu3": as_gpconnect_stu3(projected),
            "live": False,
            "reason": "NHS spine write-back is not onboarded",
        }

    def status(self) -> dict:
        cfg = live.missing_live_config()
        return {
            "country_code": self.country_code,
            "fhir_release": self.fhir_release,
            "surfaces": {
                "nhs_number_modulus_11": "available",
                "uk_core_r4_mapping": "available",
                "gpconnect_stu3_translation": "available",
                "reminder_projection": "available",
                "pds": "blocked" if cfg["pds"] or not cfg["live_enabled"] else "configured",
                "gpconnect": "blocked" if cfg["gpconnect"] or not cfg["live_enabled"] else "configured",
            },
            "missing": cfg,
        }


adapter = NhsAdapter()


def verify_identifier(value: str) -> dict:
    return adapter.verify_identifier(value)


def export_subject(subject_id: int, release: str = "r4") -> list[dict]:
    return adapter.export_subject(subject_id, release=release)


def import_record(resource: dict) -> dict:
    return adapter.import_record(resource)


def push_reminder(reminder_id: int) -> dict:
    return adapter.push_reminder(reminder_id)
