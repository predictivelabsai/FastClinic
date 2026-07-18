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


# --- cohort-keyed recall schedule (COUNTRY-SPECIFIC — the UK adapter's data) ----
# The flat RECURRING_INTERVALS_DAYS above is the country-neutral default. Real
# recall is keyed on the cohort a *subject* belongs to, so the engine (generic)
# is separated from the schedule (a country adapter owns it). See
# docs/CLINIC_OS_PLAN.md §2/§6. This is a *representative* UK starter set, not the
# full childhood-immunisation / screening schedule — extend per NHS guidance.
#
# Each rule: (category, age_min, age_max, sex, interval_days, label). age bounds
# are inclusive years (None = open); sex is 'F' | 'M' | None (any). First match
# wins; a category with no matching rule falls back to the flat interval.
COHORT_RECALL: list[tuple] = [
    ("vaccine",              65, None, None, 365, "Annual flu (65+)"),
    ("vaccine",              0,   17,  None, 180, "Childhood immunisation"),
    ("health_plan",          40,  74,  None, 365, "NHS Health Check cohort (40–74)"),
    ("repeat_prescription",  65, None, None,  90, "Medication review (65+)"),
    # e.g. add ("cervical_screening", 25, 64, 'F', 1095, "Cervical screening")
    # once such items exist in the catalogue.
]


def _sex_of(gender_code) -> str | None:
    lbl = GENDER_LABELS.get(str(gender_code).strip() if gender_code is not None else "")
    return {"Female": "F", "Male": "M"}.get(lbl)


def recall_interval_days(category: str, age_years=None, gender_code=None) -> int | None:
    """Re-visit interval for a recurring service, cohort-aware.

    Consults the country cohort schedule first (age/sex bands); falls back to the
    flat RECURRING_INTERVALS_DAYS. Returns None for non-recurring categories.
    """
    if age_years is not None:
        sex = _sex_of(gender_code)
        for cat, amin, amax, rsex, days, _lbl in COHORT_RECALL:
            if cat != category:
                continue
            if amin is not None and age_years < amin:
                continue
            if amax is not None and age_years > amax:
                continue
            if rsex is not None and rsex != sex:
                continue
            return days
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
