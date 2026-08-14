"""Lithuanian E. sveikata/ESPBI country adapter.

Offline mappings and a persistent synthetic sandbox are implemented. Live
national-system calls remain fail-closed until a clinic completes onboarding,
supplies approved profiles/test identities, and passes acceptance testing.
"""
from __future__ import annotations

from copy import deepcopy

from web.adapters import exchange
from web.adapters.base import AdapterNotAvailable
from web.adapters.lt import live
from web.adapters.lt.documents import clinical_document, validate_document
from web.adapters.lt.identifiers import verify_personal_code
from web.adapters.lt.ipr import appointment_message, validate_appointment
from web.adapters.lt.profiles import e200_order_bundle, validate_e200_shape
from web.adapters.lt.signatures import SandboxSignatureProvider
from web.adapters.lt.synthetic import FIXTURE_ID, outpatient_fixture
from web.adapters.lt.terminology import status as terminology_status

country_code = "LT"
fhir_release = "ESPBI mixed + eLab R5"


class LithuaniaAdapter:
    country_code = country_code
    fhir_release = fhir_release

    def verify_identifier(self, value: str) -> dict:
        return verify_personal_code(value)

    def export_subject(self, subject_id: int, **_kwargs) -> list[dict]:
        """Return a non-conformant LT mapping preview of the core R4 export."""
        from web import fhir
        resources = fhir.export_subject(int(subject_id), include_ops=True)
        return [_preview(resource) for resource in resources]

    def import_record(self, resource: dict) -> dict:
        from web import fhir
        mapped = fhir.import_resource(resource)
        mapped.update({
            "adapter": "lt",
            "warning": "Generic core import only; no live ESPBI write was performed.",
        })
        return mapped

    def push_reminder(self, reminder_id: int) -> dict:
        raise AdapterNotAvailable(
            f"Reminder {reminder_id} has no direct ESPBI projection; use IPR or a "
            "clinic communication workflow with its own lawful basis."
        )

    def fixture(self, *, surface: str = "espbi", document_type: str = "E025") -> dict:
        fixture = outpatient_fixture()
        normalized = surface.strip().lower()
        if normalized == "espbi":
            payload = clinical_document(fixture, document_type)
        elif normalized == "elab":
            payload = e200_order_bundle(fixture)
            document_type = "E200"
        elif normalized == "ipr":
            payload = appointment_message(fixture)
            document_type = "IPR"
        else:
            raise ValueError("surface must be espbi, elab, or ipr")
        return {
            "fixture_id": FIXTURE_ID,
            "synthetic": True,
            "surface": normalized,
            "document_type": document_type.upper(),
            "payload": payload,
        }

    def validate(self, *, surface: str, payload: dict) -> dict:
        normalized = surface.strip().lower()
        if normalized == "espbi":
            return validate_document(payload)
        if normalized == "elab":
            return validate_e200_shape(payload)
        if normalized == "ipr":
            return validate_appointment(payload)
        raise ValueError("surface must be espbi, elab, or ipr")

    def sandbox_submit(
        self, *, surface: str, document_type: str, idempotency_key: str,
        payload: dict | None = None,
    ) -> dict:
        fixture = outpatient_fixture()
        built = self.fixture(surface=surface, document_type=document_type)
        request = payload or built["payload"]
        document_type = built["document_type"]
        outcome = self.validate(surface=surface, payload=request)
        if not outcome["valid"]:
            raise ValueError("Sandbox validation failed: " + "; ".join(outcome["errors"]))
        signed = deepcopy(request)
        signed["_fastclinicSandboxSignature"] = SandboxSignatureProvider().sign(
            request,
            practitioner_role_ref=f"PractitionerRole/{fixture['practitioner_role']['id']}",
            signed_at="2026-08-14T06:25:00Z",
        )
        result = exchange.submit(
            country_code="LT", surface=surface.upper(), document_type=document_type.upper(),
            subject_ref=f"Patient/{fixture['patient']['id']}",
            practitioner_role_ref=f"PractitionerRole/{fixture['practitioner_role']['id']}",
            payload=signed, idempotency_key=idempotency_key,
        )
        result["validation"] = outcome
        return result

    def status(self) -> dict:
        missing = live.missing_live_config()
        return {
            "country_code": self.country_code,
            "national_system": "E. sveikata / ESPBI IS",
            "operator": "Registrų centras (under Ministry of Health governance)",
            "fhir_release": self.fhir_release,
            "mode": "sandbox",
            "surfaces": {
                "espbi_e025_e027_e063_projection": "available_sandbox",
                "elab_fhir_r5_e200_projection": "available_sandbox",
                "ipr_appointment_projection": "available_sandbox",
                "persistent_exchange_ledger": "available",
                "live_espbi": "blocked" if missing or not live.live_enabled() else "configured_but_not_implemented",
            },
            "terminology": terminology_status(),
            "live_enabled": live.live_enabled(),
            "missing_live_config": missing,
            "production_conformant": False,
            "limitations": [
                "No official ESPBI validator or test endpoint has been called.",
                "Synthetic identities are not official Registrų centras test identities.",
                "Sandbox integrity proofs are not qualified electronic signatures.",
                "Production transport remains deliberately unimplemented and fail-closed.",
            ],
        }


def _preview(resource: dict) -> dict:
    out = deepcopy(resource)
    out.setdefault("meta", {}).setdefault("tag", []).append({
        "system": "https://fastclinic.dev/fhir/tag",
        "code": "lt-mapping-preview",
        "display": "Mapping preview only; not an ESPBI submission",
    })
    return out


adapter = LithuaniaAdapter()


def verify_identifier(value: str) -> dict:
    return adapter.verify_identifier(value)


def export_subject(subject_id: int) -> list[dict]:
    return adapter.export_subject(subject_id)


def import_record(resource: dict) -> dict:
    return adapter.import_record(resource)


def push_reminder(reminder_id: int) -> dict:
    return adapter.push_reminder(reminder_id)
