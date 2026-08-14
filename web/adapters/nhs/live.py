"""Live NHS spine calls — gated until onboarding credentials exist.

GP Connect, PDS, IM1, SSP, and NHS login stay unschedulable without sandbox
access (docs/CLINIC_OS_PLAN.md §10 Q1). Every function here raises
``AdapterNotAvailable`` unless the matching env vars are present *and*
``NHS_LIVE_ENABLED=true``. Even then, this module refuses to invent a client:
the first live implementation must follow the official implementation guides
in force at onboarding time.
"""
from __future__ import annotations

import os

from web.adapters.base import AdapterNotAvailable

_LIVE_FLAG = "NHS_LIVE_ENABLED"
_PDS_VARS = ("NHS_PDS_BASE_URL", "NHS_PDS_API_KEY")
_GPCONNECT_VARS = (
    "NHS_GPCONNECT_ENDPOINT",
    "NHS_GPCONNECT_FROM_ASID",
    "NHS_GPCONNECT_TO_ASID",
)


def live_enabled() -> bool:
    return (os.getenv(_LIVE_FLAG) or "").strip().lower() in {"1", "true", "yes"}


def missing_live_config() -> dict:
    return {
        "pds": [name for name in _PDS_VARS if not (os.getenv(name) or "").strip()],
        "gpconnect": [name for name in _GPCONNECT_VARS if not (os.getenv(name) or "").strip()],
        "live_enabled": live_enabled(),
    }


def pds_lookup(nhs_number: str) -> dict:
    """Trace an NHS Number on PDS (UK Core R4). Not onboarded."""
    raise AdapterNotAvailable(_blocked("PDS Patient retrieval", _PDS_VARS))


def gpconnect_structured_record(nhs_number: str) -> dict:
    """GP Connect Access Record: Structured (STU3). Not onboarded."""
    raise AdapterNotAvailable(_blocked("GP Connect Access Record: Structured", _GPCONNECT_VARS))


def gpconnect_appointment_slots(*_args, **_kwargs) -> dict:
    raise AdapterNotAvailable(_blocked("GP Connect Appointment Management", _GPCONNECT_VARS))


def push_to_spine(_resource: dict) -> dict:
    raise AdapterNotAvailable(_blocked("NHS spine write-back", _GPCONNECT_VARS + _PDS_VARS))


def _blocked(surface: str, required: tuple[str, ...]) -> str:
    missing = [name for name in required if not (os.getenv(name) or "").strip()]
    enabled = live_enabled()
    return (
        f"{surface} is not connected. Live NHS calls require {_LIVE_FLAG}=true "
        f"and onboarding credentials ({', '.join(required)}). "
        f"live_enabled={enabled}; missing={missing or 'none'}. "
        "See docs/adapters/NHS_GP_CONNECT.md and Clinic OS §10 Q1."
    )
