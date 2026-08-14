"""Country interoperability adapters.

The FastClinic core is country-neutral and FHIR R4-shaped (see
`docs/CLINIC_OS_PLAN.md` §2, §9). Everything a country layers *on top* of R4 —
identifier systems, national profiles, auth, terminology bindings, consent
regimes — lives behind a `CountryAdapter` (see `base.py`), never in the core.

Adapters:

  • nhs  — UK / NHS. Mapping, NHS Number check-digit, UK Core R4 export and
           GP Connect STU3 translation are implemented. Live PDS / GP Connect
           / IM1 / SSP calls remain gated on onboarding credentials.

Select an adapter through `web.adapters.registry.get_adapter('GB')`. The core
never imports a national module directly.
"""
from __future__ import annotations

from web.adapters.base import AdapterNotAvailable, CountryAdapter
from web.adapters.registry import available_countries, get_adapter

__all__ = [
    "AdapterNotAvailable",
    "CountryAdapter",
    "available_countries",
    "get_adapter",
]
