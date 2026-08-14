"""Estonian TEHIK/TIS country adapter with an offline synthetic sandbox."""
from __future__ import annotations

from copy import deepcopy

from web.adapters import exchange
from web.adapters.base import AdapterNotAvailable
from web.adapters.ee import live
from web.adapters.ee.cda import outpatient_epicrisis_xml, validate_cda_shape
from web.adapters.ee.identifiers import verify_personal_code
from web.adapters.ee.mpi import authorization_request, patient_preview, validate_patient_preview
from web.adapters.ee.synthetic import FIXTURE_ID, outpatient_fixture
from web.adapters.ee.xroad import headers as xroad_headers

country_code = "EE"
fhir_release = "TIS CDA/HL7 v3 + MPI FHIR R5"


class EstoniaAdapter:
    country_code = country_code
    fhir_release = fhir_release

    def verify_identifier(self, value: str) -> dict:
        return verify_personal_code(value)

    def export_subject(self, subject_id: int, **_kwargs) -> list[dict]:
        from web import fhir
        return [_preview(resource) for resource in fhir.export_subject(int(subject_id), include_ops=True)]

    def import_record(self, resource: dict) -> dict:
        from web import fhir
        mapped = fhir.import_resource(resource)
        mapped.update({"adapter": "ee", "warning": "Core import only; no TIS write was performed."})
        return mapped

    def push_reminder(self, reminder_id: int) -> dict:
        raise AdapterNotAvailable(
            f"Reminder {reminder_id} is not a TIS clinical document; use the clinic's "
            "consent-aware communication workflow."
        )

    def fixture(self, *, surface: str = "tis") -> dict:
        fixture = outpatient_fixture()
        normalized = surface.strip().lower()
        if normalized == "tis":
            payload = {
                "surface": "TIS",
                "mode": "sandbox",
                "not_production_conformant": True,
                "document_type": "AMBULATORY_EPICRISIS",
                "cda_xml": outpatient_epicrisis_xml(fixture),
            }
            document_type = "AMBULATORY_EPICRISIS"
        elif normalized == "mpi":
            payload = patient_preview(fixture)
            payload["authorization_request"] = authorization_request(fixture)
            document_type = "MPI_PATIENT_PREVIEW"
        else:
            raise ValueError("surface must be tis or mpi")
        return {
            "fixture_id": FIXTURE_ID,
            "synthetic": True,
            "surface": normalized,
            "document_type": document_type,
            "payload": payload,
        }

    def validate(self, *, surface: str, payload: dict) -> dict:
        normalized = surface.strip().lower()
        if normalized == "tis":
            if not payload.get("not_production_conformant"):
                return {"valid": False, "errors": ["sandbox marker is required"], "official_validator_run": False}
            return validate_cda_shape(payload.get("cda_xml", ""))
        if normalized == "mpi":
            return validate_patient_preview(payload)
        raise ValueError("surface must be tis or mpi")

    def sandbox_submit(
        self, *, surface: str, idempotency_key: str, payload: dict | None = None,
    ) -> dict:
        fixture = outpatient_fixture()
        built = self.fixture(surface=surface)
        request = payload or built["payload"]
        validation = self.validate(surface=surface, payload=request)
        if not validation["valid"]:
            raise ValueError("Sandbox validation failed: " + "; ".join(validation["errors"]))
        result = exchange.submit(
            country_code="EE", surface=surface.upper(), document_type=built["document_type"],
            subject_ref=f"Patient/{fixture['patient']['id']}",
            practitioner_role_ref=f"Practitioner/{fixture['practitioner']['id']}",
            payload=request, idempotency_key=idempotency_key,
        )
        result["validation"] = validation
        return result

    def xroad_preview(self) -> dict:
        return {
            "headers": xroad_headers(
                client="ee-dev/COM/SYNTHETIC-REG-001/fastclinic",
                user_personal_code="OFFICIAL-TEHIK-TEST-USER-REQUIRED",
                issue="Synthetic treatment-context integration test",
                request_id="00000000-0000-4000-8000-000000000001",
            ),
            "sent": False,
            "warning": "Preview only; the clinic's X-Road security server supplies the trusted transport.",
        }

    def status(self) -> dict:
        missing = live.missing_live_config()
        return {
            "country_code": "EE",
            "national_system": "Tervise infosüsteem (TIS)",
            "operator": "TEHIK (Ministry of Social Affairs is controller)",
            "fhir_release": self.fhir_release,
            "mode": "sandbox",
            "surfaces": {
                "tis_cda_projection": "available_sandbox",
                "mpi_fhir_r5_preview": "available_sandbox",
                "xroad_request_context": "available_sandbox",
                "persistent_exchange_ledger": "available",
                "live_tis": "blocked" if missing or not live.live_enabled() else "configured_but_not_implemented",
            },
            "live_enabled": live.live_enabled(),
            "missing_live_config": missing,
            "production_conformant": False,
            "limitations": [
                "The CDA template OID is intentionally non-production.",
                "No TEHIK validator, ee-dev service or X-Road security server was called.",
                "The MPI identity is synthetic, not a TEHIK test identity.",
                "Production transport remains deliberately unimplemented and fail-closed.",
            ],
        }


def _preview(resource: dict) -> dict:
    out = deepcopy(resource)
    out.setdefault("meta", {}).setdefault("tag", []).append({
        "system": "https://fastclinic.dev/fhir/tag", "code": "ee-mapping-preview",
        "display": "Mapping preview only; not a TIS submission",
    })
    return out


adapter = EstoniaAdapter()


def verify_identifier(value: str) -> dict:
    return adapter.verify_identifier(value)


def export_subject(subject_id: int) -> list[dict]:
    return adapter.export_subject(subject_id)


def import_record(resource: dict) -> dict:
    return adapter.import_record(resource)


def push_reminder(reminder_id: int) -> dict:
    return adapter.push_reminder(reminder_id)
