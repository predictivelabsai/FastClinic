"""Item categorisation + activation rules for the FastClinic GP catalogue.

The PMS export only gives us free-text line-item names. To power dashboards and
the activation engines we classify each item into a category and flag the
recurring services (immunisations, health checks, repeat prescriptions) that
patients must come back for.

Everything here is keyword-driven and intentionally easy to extend — drop new
service names into the lists below as the catalogue grows.
"""
from __future__ import annotations

# --- category keyword rules (checked in order; first match wins) ---------------
# Each entry: (category, [lowercase substrings]).
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("health_plan", ["health check", "health review", "care plan"]),
    ("vaccine", [
        "vaccination", "vaccine", "booster", "immunis", "immuniz",
        "influenza", "covid", "pneumococcal", "tetanus", "shingles", "hpv",
    ]),
    ("repeat_prescription", [
        "repeat prescription", "medication review", "inhaler review",
        "contraception review", "statin",
    ]),
    ("lab", [
        "blood count", "lipid", "hba1c", "thyroid", "urine test",
        "liver function", "blood test", "swab", "screening test",
    ]),
    ("imaging", ["x-ray", "xray", "ultrasound", "ecg", "scan", "mri", "ct "]),
    ("procedure", ["minor surgery", "joint injection", "cryotherapy",
                   "ear syringing", "biopsy", "suture", "dressing"]),
    ("referral", ["referral", "refer to"]),
    ("medication", ["antibiotic", "pain relief", "steroid", "spray", "tablet",
                    "cream", "ointment", "injection"]),
    ("consultation", ["consultation", "appointment", "review", "visit", "telephone"]),
]

# --- recurring services that drive patient activation --------------------------
# Default re-visit interval (days) used to compute "due / overdue" status.
RECURRING_INTERVALS_DAYS = {
    "vaccine": 365,               # annual immunisations / boosters
    "health_plan": 365,           # annual health check / care-plan review
    "repeat_prescription": 60,    # repeat medication review cycle
}

# Categories that count as a genuine clinical "visit" for lapsed detection.
VISIT_CATEGORIES = {
    "consultation", "vaccine", "health_plan", "procedure",
    "imaging", "lab", "repeat_prescription",
}

# Human-friendly labels for the recurring categories (used by the cockpit UI).
CATEGORY_LABELS = {
    "vaccine": "Immunisation",
    "health_plan": "Health check / care plan",
    "repeat_prescription": "Repeat prescription",
    "consultation": "Consultation",
    "lab": "Blood / lab test",
    "imaging": "Imaging",
    "procedure": "Procedure",
    "referral": "Referral",
    "medication": "Medication",
    "other": "Other",
}


def categorise(name: str | None) -> str:
    """Map a line-item name to a category slug."""
    if not name:
        return "other"
    low = name.lower()
    for category, needles in CATEGORY_RULES:
        if any(n in low for n in needles):
            return category
    return "other"


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").title())


def is_recurring(category: str) -> bool:
    return category in RECURRING_INTERVALS_DAYS


def interval_days(category: str) -> int | None:
    return RECURRING_INTERVALS_DAYS.get(category)


# --- lightweight code lookups -------------------------------------------------
GENDER_LABELS = {
    "1": "Male",
    "2": "Male",
    "3": "Female",
    "4": "Female",
}


def gender_label(code) -> str:
    return GENDER_LABELS.get(str(code).strip() if code is not None else "", "—")
