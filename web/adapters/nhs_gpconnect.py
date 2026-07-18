"""NHS / UK adapter — GP Connect + UK Core + PDS.  ★ STUB ONLY — NOT BUILT ★

Nothing here is implemented. Every method raises `AdapterNotAvailable`. This
module exists to pin the interface and record the verified constraints, so that
when (if) the assurance gate below is cleared, the work has a defined shape.

Do NOT wire this into the running app.

────────────────────────────────────────────────────────────────────────────
WHY IT IS A STUB, NOT CODE — the assurance gate (docs/CLINIC_OS_PLAN.md §10 Q1)
────────────────────────────────────────────────────────────────────────────
Building the NHS surface is blocked on a question two research passes could not
answer from public documentation: **can a non-supplier open-source project
obtain GP Connect sandbox credentials, and what does production access require?**
Expected gates: DCB0129/DCB0160 clinical-safety, DTAC, DSPT, possibly GPIT
Futures supplier status. Until answered by direct contact with NHS England API
onboarding, this adapter is *unschedulable* — see the plan. Phases 0–5a of the
roadmap do not depend on it.

────────────────────────────────────────────────────────────────────────────
VERIFIED CONSTRAINTS to honour once it IS built  [V = confirmed vs primary source]
────────────────────────────────────────────────────────────────────────────
• VERSION SPLIT [V]: GP Connect "Access Record: Structured" is **STU3**, whereas
  UK Core is **R4 (4.0.1)**. They are NOT version-compatible. This adapter must
  translate core-R4 ↔ GP-Connect-STU3, and is internally version-split by
  service. Structure it as two sub-packages, not one blob:
      adapters/nhs/gpconnect_stu3/   ← GP Connect capability packs (STU3)
      adapters/nhs/ukcore_r4/        ← UK Core-profiled surfaces, PDS (R4)
• DO NOT trust NHS catalogue prose [V]: its published rationale for GP Connect
  being STU3 ("aligned with UK Core, built on FHIR R3") is factually WRONG — UK
  Core is R4. Verify against the profiles on simplifier.net, not the narrative.
• RELATIONSHIP CODES [V]: RelatedPerson.relationship is PREFERRED-bound only, and
  base R4 ships NO `guardian` code. The core `role` enum is authoritative; map it
  to national codes here, at the boundary — never leak national codes into core.
• RECALL [V]: only the vaccine slice has a canonical "due" resource
  (ImmunizationRecommendation, structure only, EXAMPLE bindings). Screening /
  health-check recalls map to Task / CommunicationRequest.

UNVERIFIED — resolve during onboarding, do not assume:
  other GP Connect packs (Access Record HTML, Appointment Management, Send
  Document) and their FHIR versions; SSP / JWT auth specifics; IM1 tiers
  (Pairing / Bulk / Transactional) and eligibility; NHS App / NHS login; SDS.
"""
from __future__ import annotations

from web.adapters.base import AdapterNotAvailable

country_code = "GB"
fhir_release = "STU3+R4"  # version-split: GP Connect STU3, UK Core / PDS R4

_STUB = (
    "NHS / GP Connect adapter is not implemented. It is blocked on the assurance "
    "gate in docs/CLINIC_OS_PLAN.md §10 Q1 (open-source sandbox access). "
    "See web/adapters/nhs_gpconnect.py for the verified constraints."
)


def verify_identifier(value: str) -> dict:
    """Would trace an NHS Number via PDS (R4). Not implemented."""
    raise AdapterNotAvailable(_STUB)


def export_subject(subject_id: int) -> list[dict]:
    """Would emit UK Core R4 (or GP Connect STU3) resources. Not implemented."""
    raise AdapterNotAvailable(_STUB)


def import_record(resource: dict) -> dict:
    """Would re-normalise inbound GP Connect STU3 / UK Core R4. Not implemented."""
    raise AdapterNotAvailable(_STUB)


def push_reminder(reminder_id: int) -> dict:
    """Would project a reminder onto ImmunizationRecommendation / Task. Not implemented."""
    raise AdapterNotAvailable(_STUB)
