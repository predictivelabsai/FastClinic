"""Country interoperability adapters.

The FastClinic core is country-neutral and FHIR R4-shaped (see
`docs/CLINIC_OS_PLAN.md` §2, §9). Everything a country layers *on top* of R4 —
identifier systems, national profiles, auth, terminology bindings, consent
regimes — lives behind a `CountryAdapter` (see `base.py`), never in the core.

Adapters implemented / stubbed:

  • nhs_gpconnect  — UK / NHS.  STUB ONLY.  Not built. See the module docstring
                     and docs/adapters/NHS_GP_CONNECT.md for why, and for the
                     assurance gate that blocks building it.

No adapter is wired into the running app. Importing one and calling it raises
`NotImplementedError` by design — the seam is defined, the implementation is not.
"""
from __future__ import annotations

from web.adapters.base import CountryAdapter, AdapterNotAvailable

__all__ = ["CountryAdapter", "AdapterNotAvailable"]
