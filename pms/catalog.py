"""Treatment classification + recall rules for the FastClinic catalogue.

FastClinic is a **multi-specialty clinic operations platform** — general
practice, surgical specialties (orthopaedics, ophthalmology, ENT, general
surgery, gynaecology, urology, dermatology, plastics), and dental. The
practice-management export gives us free-text line-item names; we classify each
along two independent axes:

  • **category** — what *kind* of activity it is (consultation, surgery, dental,
    diagnostic, procedure, preventive care, …). Drives visit detection, revenue
    breakdowns and the recall engines.
  • **specialty** — which clinical *department* delivered it (orthopaedics,
    ophthalmology, dental, general practice, …). Drives the operations views
    (case mix, theatre/clinic volume and revenue per specialty).

Both are keyword-driven and easy to extend — add service names to the lists
below as the catalogue grows.
"""
from __future__ import annotations

# --- category keyword rules (checked in order; first match wins) ---------------
# Each entry: (category, [lowercase substrings]). Ordering matters: specific
# clinical work (dental, surgery, pre-op) is matched before the generic
# consultation/procedure catch-alls.
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("dental", [
        "dental", "tooth", "teeth", "molar", "filling", "extraction",
        "root canal", "crown", "bridge", "denture", "scale and polish",
        "hygienist", "hygiene visit", "whitening", "orthodontic", "brace",
        "veneer", "gum ", "periodontal",
    ]),
    ("health_plan", ["health check", "health review", "care plan", "well-person",
                     "annual review"]),
    ("vaccine", [
        "vaccination", "vaccine", "booster", "immunis", "immuniz",
        "influenza", "covid", "pneumococcal", "tetanus", "shingles", "hpv",
    ]),
    ("pre_op", ["pre-op", "pre op", "pre-operative", "preoperative",
                "pre-assessment", "pre-admission"]),
    ("surgery", [
        "replacement", "arthroscopy", "arthroplasty", "reconstruction",
        "ectomy", "plasty", "discectomy", "decompression", "fixation",
        "fusion", "grafting", "bypass", "angioplasty", "cataract surgery",
        "hysteroscopy", "sinus surgery", "endoscopic sinus", "stent",
        "keratoplasty", "trabeculectomy", "hysterectomy", "hernia repair",
        "haemorrhoid", "cholecystectomy", "fundoplication", "varicose vein",
        "turp", "turbt", "vasectomy", "ureteroscopy", "cabg", "pacemaker",
        "tonsillectomy", "septoplasty", "bunion", "carpal tunnel",
        "ligament repair", "tumour resection", "mastectomy", "lumpectomy",
    ]),
    ("specialist_consult", [
        "specialist consultation", "consultant review", "outpatient appointment",
        "orthopaedic consultation", "ophthalmology consultation",
        "ent consultation", "gynaecology consultation", "urology consultation",
        "dermatology consultation", "cardiology consultation",
        "surgical consultation", "new patient (specialist)",
    ]),
    ("repeat_prescription", [
        "repeat prescription", "medication review", "inhaler review",
        "contraception review", "statin",
    ]),
    ("lab", [
        "blood count", "lipid", "hba1c", "thyroid", "urine test",
        "liver function", "renal function", "blood test", "swab",
        "screening test", "clotting", "biopsy (histology)",
    ]),
    ("imaging", ["x-ray", "xray", "ultrasound", "echo", "ecg", "scan", "mri",
                 "ct ", "endoscopy", "colonoscopy", "gastroscopy"]),
    ("procedure", ["minor surgery", "skin lesion", "joint injection",
                   "cryotherapy", "ear syringing", "biopsy", "suture",
                   "dressing", "steroid injection", "mole removal",
                   "cyst removal", "cystoscopy"]),
    ("follow_up", ["post-op", "post op", "post-operative", "surgical follow-up",
                   "wound review", "suture removal"]),
    ("referral", ["referral", "refer to"]),
    ("medication", ["antibiotic", "pain relief", "steroid", "spray", "tablet",
                    "cream", "ointment", "injection"]),
    ("consultation", ["consultation", "appointment", "review", "visit", "telephone"]),
]

# --- specialty keyword rules (checked in order; first match wins) --------------
# Maps a treatment name to the clinical department that delivers it. Anatomical /
# procedure cues drive this (knee -> orthopaedics, cataract -> ophthalmology).
SPECIALTY_RULES: list[tuple[str, list[str]]] = [
    ("dental", [
        "dental", "tooth", "teeth", "molar", "filling", "extraction",
        "root canal", "crown", "bridge", "denture", "scale and polish",
        "hygienist", "hygiene visit", "whitening", "orthodontic", "brace",
        "veneer", "periodontal", "gum ",
    ]),
    ("orthopaedics", [
        "knee", "hip", "shoulder", "ankle", "elbow", "wrist", "hand ",
        "foot ", "carpal tunnel", "arthroscopy", "arthroplasty", "joint",
        "acl", "ligament", "bunion", "spinal", "spine", "discectomy",
        "trigger finger", "tennis elbow", "fracture", "orthopaedic",
    ]),
    ("ophthalmology", [
        "cataract", "glaucoma", "cornea", "keratoplasty", "trabecul",
        "retina", "vitrectomy", "ophthalm", "eye ", "lens implant",
    ]),
    ("ent", [
        "tympanoplasty", "septoplasty", "turbinoplasty", "sinus", "tonsil",
        "adenoid", "grommet", "thyroidectomy", "vocal cord", "sinusitis",
        "ent consultation", "ear syringing",
    ]),
    ("gynaecology", [
        "hysterectomy", "oophorectomy", "hysteroscopy", "colporrhaphy",
        "endometri", "ovarian", "myomectomy", "colposuspension", "gynae",
        "pelvic floor",
    ]),
    ("urology", [
        "prostat", "turp", "turbt", "bladder", "vasectomy", "ureteroscopy",
        "kidney stone", "urology", "circumcision", "cystoscopy",
    ]),
    ("gastroenterology", [
        "colonoscopy", "gastroscopy", "endoscopy", "sigmoidoscopy",
        "cholecystectomy", "gallbladder", "hernia", "haemorrhoid",
        "fundoplication", "bowel", "gastro",
    ]),
    ("cardiology", [
        "coronary", "angiography", "angioplasty", "cabg", "pacemaker",
        "defibrillator", "cardiac", "cardiology", "stent", "echocardiogram",
    ]),
    ("dermatology", [
        "skin lesion", "mole", "cyst removal", "cryotherapy", "dermatolog",
        "skin tag", "wart", "rash", "eczema", "psoriasis",
    ]),
    ("plastic_surgery", [
        "rhinoplasty", "otoplasty", "abdominoplasty", "tummy tuck",
        "mammoplasty", "breast", "liposuction", "scar revision",
        "blepharoplasty", "facelift", "reconstruction",
    ]),
    ("general_surgery", [
        "varicose vein", "lump ", "biopsy (histology)", "general surgery",
        "excision", "resection",
    ]),
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
    "consultation", "specialist_consult", "vaccine", "health_plan",
    "procedure", "surgery", "dental", "pre_op", "follow_up",
    "imaging", "lab", "repeat_prescription",
}

# Human-friendly labels for the categories (used across the cockpit UI).
CATEGORY_LABELS = {
    "vaccine": "Immunisation",
    "health_plan": "Health check / care plan",
    "repeat_prescription": "Repeat prescription",
    "consultation": "GP consultation",
    "specialist_consult": "Specialist consultation",
    "surgery": "Surgery",
    "pre_op": "Pre-op assessment",
    "follow_up": "Surgical follow-up",
    "dental": "Dental treatment",
    "lab": "Blood / lab test",
    "imaging": "Imaging",
    "procedure": "Minor procedure",
    "referral": "Referral",
    "medication": "Medication",
    "other": "Other",
}

# --- specialty (department) labels --------------------------------------------
SPECIALTY_LABELS = {
    "general_practice": "General Practice",
    "orthopaedics": "Orthopaedics",
    "ophthalmology": "Ophthalmology",
    "ent": "ENT",
    "gynaecology": "Gynaecology",
    "general_surgery": "General Surgery",
    "urology": "Urology",
    "cardiology": "Cardiology",
    "dermatology": "Dermatology",
    "plastic_surgery": "Plastic & Cosmetic Surgery",
    "gastroenterology": "Gastroenterology",
    "dental": "Dental",
    "diagnostics": "Diagnostics & Imaging",
}

# Category → the specialty it defaults to when no name keyword matches.
_CATEGORY_DEFAULT_SPECIALTY = {
    "lab": "diagnostics", "imaging": "diagnostics",
    "vaccine": "general_practice", "health_plan": "general_practice",
    "repeat_prescription": "general_practice", "consultation": "general_practice",
    "medication": "general_practice", "referral": "general_practice",
    "procedure": "general_practice", "dental": "dental",
}


def categorise(name: str | None) -> str:
    """Map a line-item name to a category slug (what kind of activity)."""
    if not name:
        return "other"
    low = name.lower()
    for category, needles in CATEGORY_RULES:
        if any(n in low for n in needles):
            return category
    return "other"


def specialty_of(name: str | None, category: str | None = None) -> str:
    """Map a line-item name to the clinical specialty that delivers it.

    Anatomical/procedure keywords win; otherwise fall back to a sensible default
    for the category (diagnostics for labs/imaging, general practice for GP work).
    """
    if name:
        low = name.lower()
        for specialty, needles in SPECIALTY_RULES:
            if any(n in low for n in needles):
                return specialty
    if category is None and name is not None:
        category = categorise(name)
    return _CATEGORY_DEFAULT_SPECIALTY.get(category or "", "general_practice")


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").title())


def specialty_label(specialty: str) -> str:
    return SPECIALTY_LABELS.get(specialty, specialty.replace("_", " ").title())


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
