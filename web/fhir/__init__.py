"""Clinic OS Phase 5a — FHIR R4 shaping of the FastClinic core.

The core stays normalised (subject / party / role). This package *materialises*
FHIR R4 resources at the boundary. Country profiles, identifier systems, and
national terminology live in `web.adapters`, never here.

    Patient              subject
    RelatedPerson        one party×subject role (not role=self)
    Person               linkage across RelatedPerson instances
    Practitioner         clinician_id
    Encounter            consultation
    Condition            diagnosis
    Procedure/Observation/ServiceRequest/Immunization/MedicationRequest
                         item, by category
    DocumentReference    note
    Appointment          ops appointment
    Consent              party.marketing_opt_out
    ImmunizationRecommendation / Task / CommunicationRequest
                         reminder
    Communication        communication log
"""
from __future__ import annotations

from web.fhir.importing import import_resource, validate_resource
from web.fhir.resources import (
    BASE_URL,
    FHIR_VERSION,
    RESOURCE_TYPES,
    capability_statement,
    core_id,
)

__all__ = [
    "BASE_URL",
    "FHIR_VERSION",
    "RESOURCE_TYPES",
    "NotFound",
    "bundle_subject",
    "capability_statement",
    "export_resource",
    "export_subject",
    "import_resource",
    "validate_resource",
]


class NotFound(LookupError):
    """A requested core row or FHIR resource does not exist."""


def export_subject(subject_id: int, *, include_ops: bool = False) -> list[dict]:
    """Materialise one subject and its related core rows as R4 resources."""
    from web.fhir.assemble import assemble_subject

    resources = assemble_subject(int(subject_id), include_ops=include_ops)
    if not resources:
        raise NotFound(f"Patient/{subject_id} was not found")
    return resources


def bundle_subject(
    subject_id: int,
    *,
    include_ops: bool = False,
    bundle_type: str = "searchset",
) -> dict:
    """Return a Bundle of the subject's R4 projection."""
    from web.fhir.assemble import as_bundle

    resources = export_subject(subject_id, include_ops=include_ops)
    return as_bundle(resources, bundle_type=bundle_type)


def export_resource(resource_type: str, resource_id: str, *, include_ops: bool = False) -> dict:
    """Return one R4 resource by type and FastClinic identity."""
    from web.fhir.assemble import assemble_one

    kind = (resource_type or "").strip()
    if kind not in RESOURCE_TYPES:
        raise NotFound(f"Unsupported resource type {resource_type}")
    resource = assemble_one(kind, str(resource_id), include_ops=include_ops)
    if not resource:
        raise NotFound(f"{kind}/{resource_id} was not found")
    return resource
