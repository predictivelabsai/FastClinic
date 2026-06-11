"""Generate a fully synthetic FastClinic GP-clinic export (.xlsx).

No real patient data ever ships. This builds a realistic-looking 5-sheet export
(patient, Consultationdiagnosis, Consultationnote, Consultationitem, client) that
the normal importer (`python -m pms.importer`) turns into fastclinic.sqlite. Every
column is populated — including the contact fields a real export omits — so the
cockpit, activation engines (due / lapsed / follow-up) and revenue charts all
light up.

    python -m pms.synth [out.xlsx] [n_patients]   # default: data/synthetic_fastclinic.xlsx, 1000

The output is deterministic (seeded) so re-running produces the same dataset.
The xlsx is written with a tiny stdlib OOXML writer — the inverse of pms/xlsx.py
(shared strings for text, serials for dates) — so no openpyxl/pandas is needed.
"""
from __future__ import annotations

import os
import random
import sys
import zipfile
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "data", "synthetic_fastclinic.xlsx")

TODAY = date(2026, 6, 10)            # reference "now" (== max item date)
_EPOCH = date(1899, 12, 30)
_EPOCH_DT = datetime(1899, 12, 30)

# --- reference vocabulary (English GP clinic) ----------------------------------
CITIES = [
    ("London", ["EC1A 1BB", "SE1 7PB", "N1 9GU", "W2 1HB"]),
    ("Manchester", ["M1 1AE", "M14 5PR", "M20 2RN", "M4 1HW"]),
    ("Bristol", ["BS1 4DJ", "BS8 1TH", "BS6 5BX", "BS3 4QY"]),
    ("Leeds", ["LS1 4DY", "LS6 2AA", "LS11 5BD", "LS2 9JT"]),
    ("Sheffield", ["S1 2HE", "S10 2TN", "S6 3BX", "S2 4SU"]),
]
STREETS = [
    "High Street", "Station Road", "Church Lane", "Victoria Road", "Mill Lane",
    "Park Avenue", "Queens Road", "Kings Road", "Manor Way", "Oakfield Grove",
]
MALE_FIRST = ["James", "Oliver", "William", "Thomas", "Daniel", "Harry", "George",
              "Jack", "Charlie", "Noah", "Samuel", "Joseph", "Adam", "Michael", "David"]
FEMALE_FIRST = ["Sophie", "Emily", "Charlotte", "Grace", "Olivia", "Amelia", "Isla",
                "Ava", "Lily", "Freya", "Hannah", "Chloe", "Ruby", "Megan", "Laura"]
LAST = ["Smith", "Jones", "Taylor", "Brown", "Wilson", "Evans", "Walker", "Roberts",
        "Wright", "Thompson", "Robinson", "Clarke", "Hughes", "Edwards", "Green",
        "Hall", "Wood", "Harris", "Patel", "Khan"]

CLINICIANS = [101, 102, 103, 104, 105]    # supervising_clinician_id pool
STAFF = [2, 10, 11, 21, 40, 101, 102, 103]  # created/modified_user_id pool
DIAG_DESCR = [
    "Early presentation, monitoring advised.", "Mild, treatment prescribed.",
    "Moderate, therapy and review arranged.", "Clinically well, prevention.",
    "Recurrent, care plan adjusted.", "Acute episode, symptomatic treatment.",
]
ITEM_CODES = ["CONS", "IMM", "RX", "BLD", "IMG", "PROC", "MED", "REF"]
REMARKS = ["Prefers morning appointments", "Needs interpreter", "Wheelchair access", "Carer present", None, None, None, None]
ALERTS = ["Penicillin allergy", "Anticoagulant therapy", "Chronic kidney disease",
          "Asthma", "Latex allergy", None, None, None]
INSURERS = ["Bupa", "AXA Health", "Vitality", "Aviva"]
BLOOD_GROUPS = ["O+", "A+", "B+", "AB+", "O-", "A-"]

# Service catalogue: drives category classification in catalog.py
CONSULTS = ["GP consultation", "Follow-up appointment", "Urgent same-day appointment",
            "Telephone consultation"]
VACCINES = ["Influenza vaccination", "COVID-19 booster", "Pneumococcal vaccination",
            "Tetanus booster", "Shingles vaccination", "HPV vaccination"]
PLANS = ["Annual health check", "Over-65 health review", "Chronic disease care plan"]
REPEAT_RX = ["Repeat prescription review", "Statin repeat prescription",
             "Blood pressure medication review", "Asthma inhaler review",
             "Contraception review"]
LABS = ["Full blood count", "Lipid profile", "HbA1c (diabetes test)",
        "Thyroid function test", "Urine test", "Liver function test"]
IMAGING = ["Chest X-ray", "Abdominal ultrasound", "ECG"]
PROCEDURES = ["Minor surgery (skin lesion)", "Joint injection",
              "Cryotherapy (wart removal)", "Ear syringing"]
MEDS = ["Antibiotic course", "Pain relief medication", "Steroid cream", "Nasal spray"]
REFERRALS = ["Cardiology referral", "Dermatology referral", "Physiotherapy referral"]

DIAGNOSES = [
    ("J06", "Upper respiratory tract infection"), ("I10", "Hypertension"),
    ("E11", "Type 2 diabetes"), ("M54", "Lower back pain"),
    ("F32", "Depression"), ("J45", "Asthma"),
    ("K21", "Acid reflux (GORD)"), ("N39", "Urinary tract infection"),
    ("L20", "Eczema / dermatitis"), ("H66", "Ear infection"),
    ("M25", "Joint pain"), ("Z00", "General health check — well"),
]
NOTE_TEXTS = [
    "Patient advised on next immunisation. General condition good.",
    "Prescribed a 7-day course; review in one week.",
    "Lifestyle and weight management discussed.",
    "Bloods taken for laboratory analysis. Awaiting results.",
    "Responding well to treatment; continue current therapy.",
    "Blood pressure reviewed; medication continued.",
]


def _serial(d: date) -> int:
    return (d - _EPOCH).days


def _serial_dt(dt: datetime) -> float:
    delta = dt - _EPOCH_DT
    return round(delta.days + delta.seconds / 86400.0, 6)


def _rand_dt(d: date, rng: random.Random) -> datetime:
    return datetime(d.year, d.month, d.day, rng.randint(8, 18), rng.randint(0, 59))


def _hash(rng: random.Random) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(32))


def generate(n_patients: int = 1000, seed: int = 42) -> dict:
    rng = random.Random(seed)
    patients, diagnoses, notes, items, clients = [], [], [], [], []

    diag_id = item_id = note_id = consult_id = 1
    forced_today = False

    # Each person is their own client record (1:1): patient.client_id == person id.
    for idx in range(n_patients):
        pid = 1001 + idx
        cid = 5001 + idx
        is_female = rng.random() < 0.51
        first = rng.choice(FEMALE_FIRST if is_female else MALE_FIRST)
        last = rng.choice(LAST)
        city, zips = rng.choice(CITIES)
        zip_code = rng.choice(zips)
        email = f"{first.lower()}.{last.lower()}{rng.randint(1, 99)}@example.com"
        phone = f"+447{rng.randint(100000000, 999999999)}"

        clients.append({
            "id": cid,
            "name": f"{first} {last}",
            "phone": phone,
            "email": email,
            "marketing_opt_out": 1 if rng.random() < 0.08 else 0,
        })

        dob = TODAY - timedelta(days=rng.randint(365, 32000))   # ~1 to ~88 yrs
        # Registered within the practice's recent data window (~last 8 yrs), always after birth.
        reg = max(dob + timedelta(days=30), TODAY - timedelta(days=rng.randint(30, 3000)))

        # Activity profile decides recency -> drives followup/due/lapsed mix.
        roll = rng.random()
        if roll < 0.52:        # active (squared bias -> many within the 14d window)
            last_activity = TODAY - timedelta(days=int(rng.random() ** 2 * 130))
        elif roll < 0.76:      # due-ish
            last_activity = TODAY - timedelta(days=rng.randint(150, 380))
        else:                  # lapsed
            last_activity = TODAY - timedelta(days=rng.randint(390, 950))
        last_activity = min(max(last_activity, reg + timedelta(days=10)), TODAY)

        # Pin the global max item date to TODAY for the first active patient.
        if not forced_today and roll < 0.52:
            last_activity = TODAY
            forced_today = True

        gender = 3 if is_female else 1   # 1 male, 3 female (see catalog.GENDER_LABELS)
        patients.append({
            "id": pid, "client_id": cid, "gender": gender,
            "date_of_birth": _serial(dob), "date_of_registration": _serial(reg),
            "insurance": 1 if rng.random() < 0.22 else 0,
            "insurance_company": rng.choice(INSURERS) if rng.random() < 0.22 else None,
            "deceased": None,
            "archived": 0,
            "critical_notes": rng.choice(ALERTS),
            "remarks": rng.choice(REMARKS),
            "official_name": f"{first} {last}",
            "city": city, "zip_code": zip_code,
            "street_address": f"{rng.randint(1, 180)} {rng.choice(STREETS)}",
            "street_address_2": None,
            "current_location": None,
            "country_region": "GB", "state": None,
            "last_consultation_id": None,
            "blood_group": rng.choice(BLOOD_GROUPS) if rng.random() < 0.4 else None,
            "nhs_number": f"{rng.randint(400, 699)} {rng.randint(100, 999)} {rng.randint(1000, 9999)}",
            "registered_clinician_id": rng.choice(CLINICIANS),
            "home_department_id": rng.randint(1, 3),
            "old_patient_id": rng.randint(1_000_000, 1_999_999),
            "private": 0,
            "external": 0, "imported": 1,
            "date_imported": _serial_dt(_rand_dt(reg, rng)),
            "created": _serial_dt(_rand_dt(reg, rng)),
            "modified": _serial_dt(_rand_dt(last_activity, rng)),
            "created_user_id": rng.choice(STAFF),
            "modified_user_id": rng.choice(STAFF),
        })

        # Build a consultation history from registration to last_activity.
        span_days = max(1, (last_activity - reg).days)
        n_consults = min(14, max(1, span_days // 110 + rng.randint(0, 3)))
        dates = sorted({reg + timedelta(days=rng.randint(0, span_days)) for _ in range(n_consults)})
        if dates:
            dates[-1] = last_activity
        last_cid = None
        for cdate in dates:
            last_cid = consult_id
            cdt = _rand_dt(cdate, rng)
            clin = rng.choice(CLINICIANS)
            lines = _consult_lines(cdate, reg, rng)
            for name, price_net in lines:
                vat = round(price_net * 1.20, 2)
                items.append({
                    "id": item_id, "consultation_id": consult_id, "patient_id": pid,
                    "code": rng.choice(ITEM_CODES), "name": name,
                    "item_id": rng.randint(4000, 9000), "quantity": 1,
                    "price": round(price_net, 2), "price_with_vat": vat,
                    "vat_percentage": 20, "type_code": str(rng.randint(1, 3)),
                    "performed_by_id": clin if rng.random() < 0.5 else None,
                    "supervising_clinician_id": clin,
                    "created": _serial_dt(cdt), "used": _serial_dt(cdt),
                    "modified": _serial_dt(cdt),
                    "created_user_id": clin, "modified_user_id": clin,
                    "hide_on_consultation": 0, "parent_linked_item_id": None,
                    "template_id": None, "template_item_id": None,
                    "no_department_rates": 0, "no_commissions": 0,
                    "is_dispense_fee_item": 0, "is_injection_fee_item": 0,
                    "patient_group_id": None,
                })
                item_id += 1
            if rng.random() < 0.55:
                code, dname = rng.choice(DIAGNOSES)
                diagnoses.append({
                    "id": diag_id, "consultation_id": consult_id, "patient_id": pid,
                    "code": code, "name": dname, "description": rng.choice(DIAG_DESCR),
                    "category": 0, "type": 1, "diagnosis": f"{code}001",
                    "date": _serial_dt(cdt), "supervising_clinician_id": clin,
                    "additional_info": None, "consultation_item_id": None,
                    "is_custom": 0, "post_consultation": 0,
                    "created": _serial_dt(cdt), "modified": _serial_dt(cdt),
                    "created_user_id": clin, "modified_user_id": clin,
                })
                diag_id += 1
            if rng.random() < 0.4:
                draft = 1 if rng.random() < 0.25 else 0
                notes.append({
                    "id": note_id, "consultation_id": consult_id, "patient_id": pid,
                    "text": rng.choice(NOTE_TEXTS), "text_hash": _hash(rng),
                    "type": 0, "custom_type": None, "draft": draft,
                    "date_added": _serial_dt(cdt), "created_user_id": clin,
                    "approved": 0 if draft else 1,
                    "approved_date": None if draft else _serial_dt(cdt),
                    "approved_user_id": None if draft else clin,
                    "edit_reason": None, "patient_group_id": None,
                    "responsible_user_id": clin, "archived_at": None,
                    "modified_session": None,
                    "created": _serial_dt(cdt), "modified": _serial_dt(cdt),
                    "modified_user_id": clin,
                })
                note_id += 1
            consult_id += 1
        patients[-1]["last_consultation_id"] = last_cid

    return {
        "patient": patients, "Consultationdiagnosis": diagnoses,
        "Consultationnote": notes, "Consultationitem": items, "client": clients,
    }


def _consult_lines(cdate: date, reg: date, rng: random.Random):
    """Return [(item_name, net_price)] for one consultation, biased to recurring care."""
    lines = [(rng.choice(CONSULTS), rng.uniform(20, 45))]
    r = rng.random()
    if r < 0.34:
        lines.append((rng.choice(VACCINES), rng.uniform(15, 30)))
    if r < 0.16:
        lines.append((rng.choice(PLANS), rng.uniform(90, 180)))
    if rng.random() < 0.30:
        lines.append((rng.choice(REPEAT_RX), rng.uniform(12, 40)))
    if rng.random() < 0.22:
        lines.append((rng.choice(LABS), rng.uniform(25, 70)))
    if rng.random() < 0.12:
        lines.append((rng.choice(IMAGING), rng.uniform(40, 110)))
    if rng.random() < 0.06:
        lines.append((rng.choice(PROCEDURES), rng.uniform(120, 400)))
    if rng.random() < 0.08:
        lines.append((rng.choice(REFERRALS), rng.uniform(30, 90)))
    if rng.random() < 0.25:
        lines.append((rng.choice(MEDS), rng.uniform(8, 35)))
    return lines


# --- tiny OOXML (.xlsx) writer: inverse of pms/xlsx.py --------------------------
def _col_letter(idx: int) -> str:
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def write_xlsx(path: str, sheets: "list[tuple[str, list[str], list[dict]]]"):
    """sheets: [(sheet_name, header_keys, list_of_row_dicts)]."""
    shared: dict[str, int] = {}

    def sref(text: str) -> int:
        if text not in shared:
            shared[text] = len(shared)
        return shared[text]

    sheet_xmls = []
    for name, headers, rows in sheets:
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
        # header row
        cells = "".join(
            f'<c r="{_col_letter(ci)}1" t="s"><v>{sref(h)}</v></c>'
            for ci, h in enumerate(headers))
        out.append(f'<row r="1">{cells}</row>')
        for ri, row in enumerate(rows, start=2):
            cell_xml = []
            for ci, h in enumerate(headers):
                v = row.get(h)
                if v is None or v == "":
                    continue
                ref = f"{_col_letter(ci)}{ri}"
                if isinstance(v, bool):
                    v = int(v)
                if isinstance(v, (int, float)):
                    cell_xml.append(f'<c r="{ref}"><v>{v}</v></c>')
                else:
                    cell_xml.append(f'<c r="{ref}" t="s"><v>{sref(str(v))}</v></c>')
            out.append(f'<row r="{ri}">{"".join(cell_xml)}</row>')
        out.append("</sheetData></worksheet>")
        sheet_xmls.append("".join(out))

    # shared strings
    sst = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
           f'count="{len(shared)}" uniqueCount="{len(shared)}">']
    for text, _ in sorted(shared.items(), key=lambda kv: kv[1]):
        sst.append(f"<si><t xml:space=\"preserve\">{_xml_escape(text)}</t></si>")
    sst.append("</sst>")

    n = len(sheets)
    wb_sheets = "".join(
        f'<sheet name="{_xml_escape(s[0])}" sheetId="{i}" r:id="rId{i}"/>'
        for i, s in enumerate(sheets, start=1))
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f'<sheets>{wb_sheets}</sheets></workbook>')
    wb_rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i in range(1, n + 1):
        wb_rels.append(f'<Relationship Id="rId{i}" '
                       'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                       f'Target="worksheets/sheet{i}.xml"/>')
    wb_rels.append(f'<Relationship Id="rId{n + 1}" '
                   'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" '
                   'Target="sharedStrings.xml"/>')
    wb_rels.append("</Relationships>")
    content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
                     '<Default Extension="xml" ContentType="application/xml"/>',
                     '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
                     '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>']
    for i in range(1, n + 1):
        content_types.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                             'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    content_types.append("</Types>")
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" '
                 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                 'Target="xl/workbook.xml"/></Relationships>')

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(content_types))
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", "".join(wb_rels))
        z.writestr("xl/sharedStrings.xml", "".join(sst))
        for i, xml in enumerate(sheet_xmls, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", xml)


# Column order for each sheet. The synthetic generator emits every field the
# importer reads (synth headers == importer xlsx keys -> 100% field coverage).
_HEADERS = {
    "patient": ["id", "client_id", "gender", "date_of_birth", "date_of_registration",
                "deceased", "archived", "critical_notes", "remarks", "official_name",
                "city", "zip_code", "street_address", "street_address_2",
                "current_location", "country_region", "state", "last_consultation_id",
                "insurance", "insurance_company", "blood_group", "nhs_number",
                "registered_clinician_id", "home_department_id", "old_patient_id",
                "private", "external", "imported", "date_imported", "created",
                "modified", "created_user_id", "modified_user_id"],
    "Consultationdiagnosis": ["id", "category", "type", "code", "name", "description",
                              "date", "created", "modified", "consultation_id",
                              "created_user_id", "diagnosis", "modified_user_id",
                              "patient_id", "supervising_clinician_id", "additional_info",
                              "consultation_item_id", "is_custom", "post_consultation"],
    "Consultationnote": ["id", "text", "type", "date_added", "draft", "created", "modified",
                         "modified_session", "consultation_id", "created_user_id",
                         "custom_type", "modified_user_id", "patient_id", "approved",
                         "approved_date", "approved_user_id", "text_hash", "edit_reason",
                         "patient_group_id", "archived_at", "responsible_user_id"],
    "Consultationitem": ["id", "code", "name", "quantity", "price", "price_with_vat",
                         "vat_percentage", "type_code", "used", "created", "modified",
                         "hide_on_consultation", "consultation_id", "created_user_id",
                         "item_id", "modified_user_id", "parent_linked_item_id", "patient_id",
                         "performed_by_id", "supervising_clinician_id", "template_id",
                         "no_department_rates", "no_commissions", "template_item_id",
                         "is_dispense_fee_item", "patient_group_id", "is_injection_fee_item"],
    "client": ["id", "name", "phone", "email", "marketing_opt_out"],
}


def build_xlsx(out_path: str = DEFAULT_OUT, n_patients: int = 1000) -> dict:
    data = generate(n_patients)
    sheets = [(name, _HEADERS[name], data[name]) for name in
              ("patient", "Consultationdiagnosis", "Consultationnote",
               "Consultationitem", "client")]
    write_xlsx(out_path, sheets)
    return {name: len(rows) for name, _, rows in sheets}


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    print(f"Generating {n} synthetic patients -> {out!r}")
    counts = build_xlsx(out, n)
    print("Sheet row counts:")
    for name, c in counts.items():
        print(f"  {name:22} {c}")
