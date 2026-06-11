"""Import a FastClinic PMS export (.xlsx) into a local SQLite database.

Usage:
    python -m pms.importer                      # default: data/*.xlsx -> fastclinic.sqlite
    python -m pms.importer <export.xlsx> <out.sqlite>

The cockpit reads the resulting SQLite read-only. Re-running rebuilds the DB
from scratch (idempotent), so refreshing data = drop in a new export and re-run.

Sheets (in the sample export, in order):
    1 patient            — people registered at the practice
    2 Consultationdiagnosis
    3 Consultationnote
    4 Consultationitem   — billable lines

The four raw tables mirror the PMS export 1:1 — every column from the export is
ingested (see FIELD_MAPS below). A handful of columns are stored under a
business-friendly alias the cockpit queries on (e.g. `deceased` -> `deceased_at`,
`date` -> `diagnosis_at`, `created`/`used` on items -> `item_at`); everything
else keeps its original name. `evals/run_eval.py` asserts 100% field coverage.

Derived tables built here:
    consultation  — one row per consultation_id (date, clinician, revenue, patient)
    client        — one row per client_id (contact columns from an optional
                    `client` sheet, else NULL)
"""
from __future__ import annotations

import glob
import os
import sqlite3
import sys

from pms.xlsx import read_sheet, sheet_names, excel_date, excel_datetime
from pms.catalog import categorise, VISIT_CATEGORIES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "fastclinic.sqlite")


def _num(v):
    if v in (None, "", "NULL"):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _int(v):
    n = _num(v)
    return int(n) if n is not None else None


def _txt(v):
    if v in (None, "", "NULL"):
        return None
    return str(v)


# --- declarative field maps: (model_column, xlsx_key, sql_type, converter) -----
# Every column from the export appears here exactly once, so the raw tables are a
# faithful 1:1 replica. Aliased columns (deceased -> deceased_at, etc.) keep the
# business name the cockpit queries on; all others keep their export name.
_DT, _D = excel_datetime, excel_date

PATIENT_FIELDS = [
    ("id", "id", "INTEGER PRIMARY KEY", _int),
    ("client_id", "client_id", "INTEGER", _int),
    ("gender", "gender", "TEXT", _txt),
    ("date_of_birth", "date_of_birth", "TEXT", _D),
    ("date_of_registration", "date_of_registration", "TEXT", _D),
    ("deceased_at", "deceased", "TEXT", _DT),
    ("archived", "archived", "INTEGER", _int),
    ("critical_notes", "critical_notes", "TEXT", _txt),
    ("remarks", "remarks", "TEXT", _txt),
    ("official_name", "official_name", "TEXT", _txt),
    ("city", "city", "TEXT", _txt),
    ("zip_code", "zip_code", "TEXT", _txt),
    ("street_address", "street_address", "TEXT", _txt),
    ("street_address_2", "street_address_2", "TEXT", _txt),
    ("current_location", "current_location", "TEXT", _txt),
    ("country_region", "country_region", "TEXT", _txt),
    ("state", "state", "TEXT", _txt),
    ("last_consultation_id", "last_consultation_id", "INTEGER", _int),
    ("insurance", "insurance", "INTEGER", _int),
    ("insurance_company", "insurance_company", "TEXT", _txt),
    ("blood_group", "blood_group", "TEXT", _txt),
    ("nhs_number", "nhs_number", "TEXT", _txt),
    ("registered_clinician_id", "registered_clinician_id", "INTEGER", _int),
    ("home_department_id", "home_department_id", "INTEGER", _int),
    ("old_patient_id", "old_patient_id", "INTEGER", _int),
    ("private", "private", "INTEGER", _int),
    ("external", "external", "INTEGER", _int),
    ("imported", "imported", "INTEGER", _int),
    ("date_imported", "date_imported", "TEXT", _DT),
    ("created", "created", "TEXT", _DT),
    ("modified", "modified", "TEXT", _DT),
    ("created_user_id", "created_user_id", "INTEGER", _int),
    ("modified_user_id", "modified_user_id", "INTEGER", _int),
]

DIAGNOSIS_FIELDS = [
    ("id", "id", "INTEGER PRIMARY KEY", _int),
    ("consultation_id", "consultation_id", "INTEGER", _int),
    ("patient_id", "patient_id", "INTEGER", _int),
    ("code", "code", "TEXT", _txt),
    ("name", "name", "TEXT", _txt),
    ("description", "description", "TEXT", _txt),
    ("category", "category", "TEXT", _txt),
    ("type", "type", "TEXT", _txt),
    ("diagnosis", "diagnosis", "TEXT", _txt),
    ("diagnosis_at", "date", "TEXT", _DT),
    ("clinician_id", "supervising_clinician_id", "INTEGER", _int),
    ("additional_info", "additional_info", "TEXT", _txt),
    ("consultation_item_id", "consultation_item_id", "INTEGER", _int),
    ("is_custom", "is_custom", "INTEGER", _int),
    ("post_consultation", "post_consultation", "INTEGER", _int),
    ("created", "created", "TEXT", _DT),
    ("modified", "modified", "TEXT", _DT),
    ("created_user_id", "created_user_id", "INTEGER", _int),
    ("modified_user_id", "modified_user_id", "INTEGER", _int),
]

NOTE_FIELDS = [
    ("id", "id", "INTEGER PRIMARY KEY", _int),
    ("consultation_id", "consultation_id", "INTEGER", _int),
    ("patient_id", "patient_id", "INTEGER", _int),
    ("text", "text", "TEXT", _txt),
    ("text_hash", "text_hash", "TEXT", _txt),
    ("type", "type", "INTEGER", _int),
    ("custom_type", "custom_type", "TEXT", _txt),
    ("draft", "draft", "INTEGER", _int),
    ("note_at", "date_added", "TEXT", _DT),
    ("clinician_id", "created_user_id", "INTEGER", _int),
    ("approved", "approved", "INTEGER", _int),
    ("approved_date", "approved_date", "TEXT", _DT),
    ("approved_user_id", "approved_user_id", "INTEGER", _int),
    ("edit_reason", "edit_reason", "TEXT", _txt),
    ("patient_group_id", "patient_group_id", "INTEGER", _int),
    ("responsible_user_id", "responsible_user_id", "INTEGER", _int),
    ("archived_at", "archived_at", "TEXT", _DT),
    ("modified_session", "modified_session", "TEXT", _txt),
    ("created", "created", "TEXT", _DT),
    ("modified", "modified", "TEXT", _DT),
    ("modified_user_id", "modified_user_id", "INTEGER", _int),
]

ITEM_FIELDS = [
    ("id", "id", "INTEGER PRIMARY KEY", _int),
    ("consultation_id", "consultation_id", "INTEGER", _int),
    ("patient_id", "patient_id", "INTEGER", _int),
    ("code", "code", "TEXT", _txt),
    ("name", "name", "TEXT", _txt),
    ("item_id", "item_id", "INTEGER", _int),
    ("quantity", "quantity", "REAL", _num),
    ("unit_price", "price", "REAL", _num),
    ("unit_price_vat", "price_with_vat", "REAL", _num),
    ("vat_pct", "vat_percentage", "REAL", _num),
    ("type_code", "type_code", "TEXT", _txt),
    ("performed_by_id", "performed_by_id", "INTEGER", _int),
    ("clinician_id", "supervising_clinician_id", "INTEGER", _int),
    ("item_at", "created", "TEXT", _DT),
    ("used", "used", "TEXT", _DT),
    ("modified", "modified", "TEXT", _DT),
    ("created_user_id", "created_user_id", "INTEGER", _int),
    ("modified_user_id", "modified_user_id", "INTEGER", _int),
    ("hide_on_consultation", "hide_on_consultation", "INTEGER", _int),
    ("parent_linked_item_id", "parent_linked_item_id", "INTEGER", _int),
    ("template_id", "template_id", "INTEGER", _int),
    ("template_item_id", "template_item_id", "INTEGER", _int),
    ("no_department_rates", "no_department_rates", "INTEGER", _int),
    ("no_commissions", "no_commissions", "INTEGER", _int),
    ("is_dispense_fee_item", "is_dispense_fee_item", "INTEGER", _int),
    ("is_injection_fee_item", "is_injection_fee_item", "INTEGER", _int),
    ("patient_group_id", "patient_group_id", "INTEGER", _int),
]

# Extra computed item columns (not raw export fields).
ITEM_COMPUTED = [("category", "TEXT"), ("line_total_vat", "REAL")]

_TABLE_FIELDS = {
    "patient": PATIENT_FIELDS, "diagnosis": DIAGNOSIS_FIELDS,
    "note": NOTE_FIELDS, "item": ITEM_FIELDS,
}


def _create_table(name: str, fields: list, extra: list | None = None) -> str:
    cols = [f"{m} {t}" for (m, _x, t, _c) in fields]
    cols += [f"{m} {t}" for (m, t) in (extra or [])]
    return f"CREATE TABLE IF NOT EXISTS {name} (\n  " + ",\n  ".join(cols) + "\n);"


def _ingest(db, table, fields, rows, computed=None):
    """Generic INSERT from a field map. `computed` is a callable(row)->dict of
    extra model_col->value, used for item category/line_total."""
    extra_cols = list(computed(rows[0]).keys()) if (computed and rows) else []
    cols = [m for (m, _x, _t, _c) in fields] + extra_cols
    ph = ",".join("?" * len(cols))
    sql = f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({ph})"
    for r in rows:
        vals = [conv(r.get(xk)) for (_m, xk, _t, conv) in fields]
        if computed:
            ex = computed(r)
            vals += [ex[c] for c in extra_cols]
        db.execute(sql, vals)


def _find_sheets(path: str) -> dict[str, int]:
    """Map known sheet roles to their 1-based index, tolerant of ordering."""
    names = sheet_names(path)
    roles = {}
    for i, n in enumerate(names, start=1):
        low = (n or "").lower().replace(" ", "")
        if low == "patient":
            roles["patient"] = i
        elif "diagnos" in low:
            roles["diagnosis"] = i
        elif "note" in low:
            roles["note"] = i
        elif "item" in low:
            roles["item"] = i
        elif low in ("client", "clients", "contact", "contacts", "owner", "owners"):
            roles["client"] = i
    return roles


def build(export_path: str, out_path: str = DEFAULT_OUT) -> dict:
    roles = _find_sheets(export_path)
    missing = {"patient", "diagnosis", "note", "item"} - set(roles)
    if missing:
        raise SystemExit(f"Export missing expected sheets: {missing}. Found: {sheet_names(export_path)}")

    patients = read_sheet(export_path, roles["patient"])
    diagnoses = read_sheet(export_path, roles["diagnosis"])
    notes = read_sheet(export_path, roles["note"])
    items = read_sheet(export_path, roles["item"])

    if os.path.exists(out_path):
        os.remove(out_path)
    db = sqlite3.connect(out_path)
    db.executescript(_SCHEMA)

    _ingest(db, "patient", PATIENT_FIELDS, patients)
    _ingest(db, "diagnosis", DIAGNOSIS_FIELDS, diagnoses)
    _ingest(db, "note", NOTE_FIELDS, notes)

    def _item_computed(r):
        qty = _num(r.get("quantity")) or 0
        unit_vat = _num(r.get("price_with_vat")) or 0
        return {"category": categorise(r.get("name")),
                "line_total_vat": round(qty * unit_vat, 2)}

    _ingest(db, "item", ITEM_FIELDS, items, computed=_item_computed)

    db.commit()
    _build_derived(db)
    if "client" in roles:
        _import_clients(db, read_sheet(export_path, roles["client"]))
    db.commit()

    counts = {
        t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("patient", "diagnosis", "note", "item", "consultation", "client")
    }
    db.close()
    return counts


def _build_derived(db: sqlite3.Connection):
    """Roll up consultations and clients from the imported line data."""
    visit_cats = ",".join(f"'{c}'" for c in sorted(VISIT_CATEGORIES))

    db.execute("DELETE FROM consultation")
    db.execute(
        f"""
        INSERT INTO consultation (id, patient_id, consult_at, revenue_vat,
                                  item_count, is_visit, clinician_id)
        SELECT
            consultation_id,
            MAX(patient_id),
            MIN(item_at),
            ROUND(SUM(line_total_vat), 2),
            COUNT(*),
            MAX(CASE WHEN category IN ({visit_cats}) THEN 1 ELSE 0 END),
            MAX(clinician_id)
        FROM item
        WHERE consultation_id IS NOT NULL
        GROUP BY consultation_id
        """
    )

    # Clients: distinct client_id from patients. Contact columns stay NULL until
    # a clients/contacts export is ingested (see _import_clients()).
    db.execute("DELETE FROM client")
    db.execute(
        """
        INSERT INTO client (id, patient_count, city, zip_code)
        SELECT client_id, COUNT(*), MAX(city), MAX(zip_code)
        FROM patient
        WHERE client_id IS NOT NULL
        GROUP BY client_id
        """
    )


def _import_clients(db: sqlite3.Connection, rows: list[dict]):
    """Merge patient-contact details (name/phone/email) onto the derived client rows.

    Real PMS exports omit contacts; a synthetic or contacts export can supply a
    `client` sheet keyed by client id to enable direct SMS/email campaigns.
    """
    for c in rows:
        cid = _int(c.get("id"))
        if cid is None:
            continue
        db.execute(
            """INSERT INTO client (id, name, phone, email, marketing_opt_out)
               VALUES (?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name, phone=excluded.phone, email=excluded.email,
                   marketing_opt_out=excluded.marketing_opt_out""",
            (cid, _txt(c.get("name")), _txt(c.get("phone")), _txt(c.get("email")),
             _int(c.get("marketing_opt_out")) or 0),
        )


_SCHEMA = "\n".join([
    _create_table("patient", PATIENT_FIELDS),
    _create_table("diagnosis", DIAGNOSIS_FIELDS),
    _create_table("note", NOTE_FIELDS),
    _create_table("item", ITEM_FIELDS, ITEM_COMPUTED),
    """
CREATE TABLE IF NOT EXISTS consultation (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER, consult_at TEXT, revenue_vat REAL,
    item_count INTEGER, is_visit INTEGER, clinician_id INTEGER
);
CREATE TABLE IF NOT EXISTS client (
    id INTEGER PRIMARY KEY,
    name TEXT, phone TEXT, email TEXT,
    patient_count INTEGER, city TEXT, zip_code TEXT,
    marketing_opt_out INTEGER DEFAULT 0
);
""",
])


def _default_export() -> str:
    candidates = sorted(glob.glob(os.path.join(ROOT, "data", "*.xlsx")))
    if not candidates:
        raise SystemExit("No .xlsx export found in data/. Pass a path explicitly.")
    return candidates[0]


if __name__ == "__main__":
    export = sys.argv[1] if len(sys.argv) > 1 else _default_export()
    out = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    print(f"Importing {export!r} -> {out!r}")
    counts = build(export, out)
    print("Done. Row counts:")
    for t, c in counts.items():
        print(f"  {t:14} {c}")
