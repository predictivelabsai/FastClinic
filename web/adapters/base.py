"""The country-adapter port — the seam between the core and a national surface.

This is an *interface*, not an implementation. It exists so the shape of a
country adapter is pinned down before any one of them is built, and so the core
never grows a national dependency.

Design rule (docs/CLINIC_OS_PLAN.md §9): FHIR R4 is international and belongs in
the core; an adapter carries only what a country adds on top of R4 — identifier
systems (NHS Number vs MRN), national profiles (UK Core vs US Core), auth
(NHS login / SSP vs SMART on FHIR), terminology bindings (SNOMED CT + dm+d vs
RxNorm), and consent regimes.

The core is **normalised** (one `party`, N `subject_party_role` rows). FHIR's
wire format is **denormalised** (one `RelatedPerson` per party×subject pair, plus
a `Person` link record). Converting between the two is the adapter's job, not the
core's — see `export_subject`.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


class AdapterNotAvailable(RuntimeError):
    """Raised when an adapter is referenced but not implemented / not onboarded."""


@runtime_checkable
class CountryAdapter(Protocol):
    """A pluggable national interoperability surface.

    Every method maps a core concept to / from a country's FHIR flavour. A method
    that a country does not support raises `AdapterNotAvailable`.
    """

    #: ISO-3166 alpha-2, e.g. "GB". Selected by clinic configuration.
    country_code: str

    #: FHIR release this adapter's primary record surface speaks, e.g. "R4",
    #: "STU3". Not assumed to be R4 — GP Connect is STU3 while UK Core is R4
    #: (see docs/CLINIC_OS_PLAN.md §9), so a single adapter may be version-split
    #: internally.
    fhir_release: str

    def verify_identifier(self, value: str) -> dict:
        """Validate / trace a national patient identifier (e.g. NHS Number via
        PDS). Returns a normalised demographic match, or raises."""
        ...

    def export_subject(self, subject_id: int) -> list[dict]:
        """Materialise a core `subject` and its `party` roles as national-profile
        FHIR resources — denormalising to N `RelatedPerson` + 1 `Person` as the
        wire format requires. Returns a list of FHIR resource dicts."""
        ...

    def import_record(self, resource: dict) -> dict:
        """Translate an inbound national-profile FHIR resource into core rows.
        The inverse of `export_subject`; re-normalises RelatedPerson/Person."""
        ...

    def push_reminder(self, reminder_id: int) -> dict:
        """Project a core `reminder` onto the country's canonical
        due/recall representation (e.g. ImmunizationRecommendation for the
        vaccine slice; Task / CommunicationRequest otherwise)."""
        ...
