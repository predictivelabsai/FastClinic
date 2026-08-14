"""Small pinned sandbox terminology set for the Lithuanian adapter.

This is intentionally not a substitute for the versioned ESPBI classifier
download supplied during onboarding. Unknown codes fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass


class UnsupportedTerminology(ValueError):
    pass


@dataclass(frozen=True)
class Term:
    system: str
    code: str
    display: str

    def coding(self) -> dict:
        return {"system": self.system, "code": self.code, "display": self.display}


SANDBOX_CATALOG_VERSION = "fastclinic-lt-sandbox-2026-08-14"
DOCUMENT_TYPES = {
    "E025": Term("http://esveikata.lt/classifiers/DocumentType", "E025", "Ambulatorinio apsilankymo aprašymas"),
    "E027": Term("http://esveikata.lt/classifiers/DocumentType", "E027", "Siuntimas"),
    "E027-ATS": Term("http://esveikata.lt/classifiers/DocumentType", "E027-ATS", "Siuntimo atsakymas"),
    "E063": Term("http://esveikata.lt/classifiers/DocumentType", "E063", "Vakcinacijos įrašas"),
    "E200": Term("http://esveikata.lt/classifiers/DocumentType", "E200", "Laboratorinio tyrimo užsakymas"),
    "IPR": Term("http://esveikata.lt/classifiers/DocumentType", "IPR", "Išankstinė pacientų registracija"),
}


def document_term(code: str) -> Term:
    normalized = str(code or "").strip().upper().replace("_", "-")
    try:
        return DOCUMENT_TYPES[normalized]
    except KeyError as exc:
        raise UnsupportedTerminology(
            f"Unsupported Lithuanian sandbox document type {code!r}; "
            f"supported: {', '.join(DOCUMENT_TYPES)}"
        ) from exc


def status() -> dict:
    return {
        "catalog_version": SANDBOX_CATALOG_VERSION,
        "mode": "sandbox-subset",
        "document_types": sorted(DOCUMENT_TYPES),
        "production_classifier_sync": "not_configured",
    }
