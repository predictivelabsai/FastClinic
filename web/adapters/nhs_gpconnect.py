"""Backward-compatible facade for the NHS adapter.

The implementation lives in ``web.adapters.nhs`` (version-split: UK Core R4 +
GP Connect STU3). This module keeps the original import path working.
"""
from __future__ import annotations

from web.adapters.nhs import (
    adapter,
    country_code,
    export_subject,
    fhir_release,
    import_record,
    push_reminder,
    verify_identifier,
)

__all__ = [
    "adapter",
    "country_code",
    "export_subject",
    "fhir_release",
    "import_record",
    "push_reminder",
    "verify_identifier",
]
