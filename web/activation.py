"""Patient-activation engines for the FastClinic cockpit.

Three engines that turn clinic history into outreach lists that bring patients
back through the door — the core activation goal:

  • reminders  — patients due / overdue for immunisations, health checks, repeat prescriptions
  • lapsed     — patients with no visit in N months (win-back)
  • followup   — recent visits to follow up (recovery / review / rebook)

Each engine produces a reviewable list, drafted English message copy, and a
downloadable CSV. Nothing is sent automatically — the lists feed the SMS
Broadcaster or an export for the clinic to action.
"""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from fasthtml.common import (
    Div, H1, H3, P, Span, A, Table, Thead, Tbody, Tr, Th, Td, NotStr,
)

from web.db import query, reference_date, db_exists
from web.layout import kpi_card
from pms.catalog import RECURRING_INTERVALS_DAYS, category_label, gender_label

CLINIC_PHONE = "+44 20 7946 0123"  # FastClinic (placeholder — update to live number)
CLINIC_NAME = "FastClinic"

RECUR_LABELS = {
    "vaccine": "Immunisation",
    "health_plan": "Health check",
    "repeat_prescription": "Repeat prescription",
}


def _ref() -> date:
    return date.fromisoformat(reference_date())


def _date(s) -> str:
    return (s or "")[:10] or "—"


def _status(due: date, today: date) -> str:
    if due < today:
        return "overdue"
    if due <= today + timedelta(days=30):
        return "due-soon"
    return "ok"


def _name(r: dict) -> str:
    """Patient's display name, falling back to the contact record."""
    return r.get("patient_name") or r.get("contact_name") or "there"


# ============================================================ data ============
def due_rows(cat_filter: str = "all") -> list[dict]:
    """Patients due / overdue for a recurring service, most urgent first."""
    today = _ref()
    cats = list(RECURRING_INTERVALS_DAYS) if cat_filter == "all" else [cat_filter]
    cats = [c for c in cats if c in RECURRING_INTERVALS_DAYS]
    if not cats:
        return []
    placeholders = ",".join("?" for _ in cats)
    rows = query(
        f"""
        SELECT i.patient_id, i.category, MAX(i.item_at) AS last_at,
               p.client_id, p.official_name AS patient_name, p.gender,
               p.critical_notes, p.deceased_at,
               c.name AS contact_name, c.phone AS contact_phone
        FROM item i JOIN patient p ON p.id = i.patient_id
        LEFT JOIN client c ON c.id = p.client_id
        WHERE i.category IN ({placeholders}) AND p.deceased_at IS NULL
        GROUP BY i.patient_id, i.category
        """,
        tuple(cats),
    )
    out = []
    for r in rows:
        interval = RECURRING_INTERVALS_DAYS[r["category"]]
        last = date.fromisoformat(r["last_at"][:10])
        due = last + timedelta(days=interval)
        status = _status(due, today)
        if status == "ok":
            continue
        out.append({
            **r,
            "last_date": last.isoformat(),
            "due_date": due.isoformat(),
            "days_overdue": (today - due).days,
            "status": status,
            "service": RECUR_LABELS.get(r["category"], category_label(r["category"])),
        })
    out.sort(key=lambda x: -x["days_overdue"])
    return out


def lapsed_rows(months: int = 12) -> list[dict]:
    today = _ref()
    cutoff = (today - timedelta(days=30 * months)).isoformat()
    rows = query(
        """
        SELECT p.id AS patient_id, p.client_id, p.official_name AS patient_name,
               p.gender, p.critical_notes,
               cl.name AS contact_name, cl.phone AS contact_phone,
               MAX(c.consult_at) AS last_visit,
               (SELECT ROUND(SUM(line_total_vat),2) FROM item i WHERE i.patient_id=p.id) AS lifetime_value,
               (SELECT COUNT(*) FROM consultation c2 WHERE c2.patient_id=p.id) AS visits
        FROM patient p JOIN consultation c ON c.patient_id = p.id
        LEFT JOIN client cl ON cl.id = p.client_id
        WHERE p.deceased_at IS NULL
        GROUP BY p.id
        HAVING last_visit < ?
        ORDER BY lifetime_value DESC
        """,
        (cutoff,),
    )
    for r in rows:
        last = date.fromisoformat(r["last_visit"][:10])
        r["months_since"] = round((today - last).days / 30)
    return rows


def followup_rows(days: int = 14) -> list[dict]:
    today = _ref()
    cutoff = (today - timedelta(days=days)).isoformat()
    return query(
        """
        SELECT c.id AS consultation_id, c.patient_id, c.consult_at, c.revenue_vat,
               p.client_id, p.official_name AS patient_name, p.gender,
               cl.name AS contact_name, cl.phone AS contact_phone,
               (SELECT GROUP_CONCAT(DISTINCT cat) FROM
                   (SELECT category AS cat FROM item i WHERE i.consultation_id=c.id)) AS categories,
               (SELECT GROUP_CONCAT(d.name, '; ') FROM diagnosis d WHERE d.consultation_id=c.id) AS diagnoses
        FROM consultation c JOIN patient p ON p.id = c.patient_id
        LEFT JOIN client cl ON cl.id = p.client_id
        WHERE c.is_visit = 1 AND c.consult_at >= ?
        ORDER BY c.consult_at DESC
        """,
        (cutoff,),
    )


# ====================================================== message drafts =========
def draft_reminder(r: dict) -> str:
    return (
        f"Hi {_name(r)}, our records at {CLINIC_NAME} show your "
        f"{r['service'].lower()} is due (last seen {r['last_date']}). "
        f"Please book an appointment: {CLINIC_PHONE}."
    )


def draft_lapsed(r: dict) -> str:
    return (
        f"Hi {_name(r)}, we miss you at {CLINIC_NAME}! It's been ~{r['months_since']} "
        f"months since your last visit. We'd love to see you for a health check — "
        f"book or re-register any time: {CLINIC_PHONE}."
    )


def draft_followup(r: dict) -> str:
    return (
        f"Hi {_name(r)}, thank you for visiting {CLINIC_NAME} on {_date(r['consult_at'])}. "
        f"How are you feeling? Reply or call {CLINIC_PHONE} if you have any concerns."
    )


# ============================================================ views ============
def _table(headers, rows):
    return Table(Thead(Tr(*[Th(h) for h in headers])),
                 Tbody(*[Tr(*[Td(c) for c in r]) for r in rows]), cls="tbl")


def _dl_btns(csv_href: str, n: int):
    """CSV + XLS download buttons (xlsx route mirrors the csv one)."""
    xls_href = csv_href.replace("/csv", "/xlsx", 1)
    return Div(
        A(f"⬇ CSV ({n})", href=csv_href, cls="btn"),
        A("⬇ XLS", href=xls_href, cls="btn primary"),
        style="display:flex; gap:8px;",
    )


def _has_contacts() -> bool:
    row = query("SELECT COUNT(*) AS n FROM client WHERE phone IS NOT NULL AND phone <> ''")
    return bool(row and row[0]["n"])


def _contacts_note():
    if _has_contacts():
        row = query("SELECT COUNT(*) AS n FROM client WHERE phone IS NOT NULL AND phone <> ''")
        return P(NotStr(
            f"<strong>{row[0]['n']}</strong> patients have a phone on file — lists below "
            "include name &amp; phone, ready for the SMS Broadcaster or CSV export."),
            style="color:var(--text-mute);font-size:12px;margin:0 0 14px;")
    return P(NotStr(
        "Lists key on <strong>Client ID</strong>. Paste a drafted message into the "
        "<a href='/ops/sms'>SMS</a> or <a href='/ops/email'>Email</a> Broadcaster to send, "
        "or download the CSV. Provide a patient contacts export (name / phone / email) to "
        "enable bulk sends — see Admin → Data &amp; Import."),
        style="color:var(--text-mute);font-size:12px;margin:0 0 14px;")


def reminders_view(cat: str = "all"):
    if not db_exists():
        from web.dashboards import _no_data_view
        return _no_data_view()
    rows = due_rows(cat)
    overdue = sum(1 for r in rows if r["status"] == "overdue")
    cards = Div(
        kpi_card("Due / overdue", len(rows), warn=True),
        kpi_card("Overdue", overdue, warn=True),
        kpi_card("Due soon (30d)", len(rows) - overdue, neutral=True),
        cls="kpi-grid", style="grid-template-columns:repeat(3,1fr);",
    )
    seg = Div(
        *[A(lbl, href=f"/activation/reminders?cat={c}",
            cls="active" if cat == c else "")
          for c, lbl in [("all", "All"), ("vaccine", "Immunisations"),
                         ("health_plan", "Health checks"),
                         ("repeat_prescription", "Repeat prescriptions")]],
        cls="seg",
    )
    table_rows = [[
        A(f"#{r['patient_id']}", href=f"/patients/{r['patient_id']}", style="font-weight:600;"),
        r.get("patient_name") or "—",
        r.get("contact_phone") or "—",
        gender_label(r.get("gender")),
        Span(r["service"], cls=f"status-pill {r['category']}"),
        _date(r["last_date"]),
        _date(r["due_date"]),
        Span("overdue" if r["status"] == "overdue" else "due soon",
             cls=f"status-pill {r['status']}"),
        f"{r['days_overdue']}d" if r["days_overdue"] > 0 else "—",
    ] for r in rows]

    sample = rows[0] if rows else None
    return Div(
        Div(Div(H1("Immunisations & Checks Due"),
                Div("Patients due or overdue for a recurring service", cls="sub")),
            _dl_btns(f"/activation/reminders/csv?cat={cat}", len(rows)),
            cls="page-title"),
        cards, seg, _contacts_note(),
        Div(Div(H3(f"{len(rows)} patients to contact"), cls="card-header"),
            _table(["Patient", "Name", "Phone", "Gender", "Service", "Last", "Due", "Status", "Overdue"],
                   table_rows) if table_rows else P("Nothing due — all caught up. 🎉"),
            cls="card"),
        Div(Div(H3("Drafted message (sample)"), cls="card-header"),
            Div(draft_reminder(sample), cls="msg-draft") if sample
            else P("No drafts."), cls="card") if sample else None,
    )


def lapsed_view(months: int = 12):
    if not db_exists():
        from web.dashboards import _no_data_view
        return _no_data_view()
    rows = lapsed_rows(months)
    value_at_risk = sum(r["lifetime_value"] or 0 for r in rows)
    cards = Div(
        kpi_card("Lapsed patients", len(rows), warn=True),
        kpi_card("Value at risk", f"£{value_at_risk:,.0f}", warn=True),
        kpi_card("Threshold", f"{months} months", neutral=True),
        cls="kpi-grid", style="grid-template-columns:repeat(3,1fr);",
    )
    seg = Div(
        *[A(f"{m} mo", href=f"/activation/lapsed?months={m}",
            cls="active" if months == m else "")
          for m in (6, 9, 12, 18, 24)],
        cls="seg",
    )
    table_rows = [[
        A(f"#{r['patient_id']}", href=f"/patients/{r['patient_id']}", style="font-weight:600;"),
        r.get("patient_name") or "—",
        r.get("contact_phone") or "—",
        gender_label(r.get("gender")),
        _date(r["last_visit"]),
        f"{r['months_since']} mo",
        r["visits"],
        f"£{(r['lifetime_value'] or 0):,.0f}",
    ] for r in rows]
    sample = rows[0] if rows else None
    return Div(
        Div(Div(H1("Lapsed Reactivation"),
                Div("Patients to win back before they're gone", cls="sub")),
            _dl_btns(f"/activation/lapsed/csv?months={months}", len(rows)),
            cls="page-title"),
        cards, seg, _contacts_note(),
        Div(Div(H3(f"{len(rows)} lapsed patients"), cls="card-header"),
            _table(["Patient", "Name", "Phone", "Gender", "Last visit", "Lapsed", "Visits", "Lifetime £"],
                   table_rows) if table_rows else P("No lapsed patients at this threshold. 🎉"),
            cls="card"),
        Div(Div(H3("Drafted message (sample)"), cls="card-header"),
            Div(draft_lapsed(sample), cls="msg-draft"), cls="card") if sample else None,
    )


def followup_view(days: int = 14):
    if not db_exists():
        from web.dashboards import _no_data_view
        return _no_data_view()
    rows = followup_rows(days)
    cards = Div(
        kpi_card("Recent visits", len(rows)),
        kpi_card("Window", f"{days} days", neutral=True),
        cls="kpi-grid", style="grid-template-columns:repeat(2,1fr);",
    )
    seg = Div(
        *[A(f"{d} days", href=f"/activation/followup?days={d}",
            cls="active" if days == d else "")
          for d in (7, 14, 30, 60)],
        cls="seg",
    )
    table_rows = [[
        A(f"#{r['patient_id']}", href=f"/patients/{r['patient_id']}", style="font-weight:600;"),
        r.get("patient_name") or "—",
        r.get("contact_phone") or "—",
        _date(r["consult_at"]),
        (r["categories"] or "—").replace(",", ", "),
        ((r["diagnoses"] or "—")[:80]),
        f"£{(r['revenue_vat'] or 0):,.0f}",
    ] for r in rows]
    sample = rows[0] if rows else None
    return Div(
        Div(Div(H1("Post-Visit Follow-up"),
                Div("Recent visits to check in on — recovery, reviews, rebooking", cls="sub")),
            _dl_btns(f"/activation/followup/csv?days={days}", len(rows)),
            cls="page-title"),
        cards, seg, _contacts_note(),
        Div(Div(H3(f"{len(rows)} recent visits"), cls="card-header"),
            _table(["Patient", "Name", "Phone", "Visit date", "Done", "Diagnoses", "Revenue"],
                   table_rows) if table_rows else P("No visits in this window."),
            cls="card"),
        Div(Div(H3("Drafted message (sample)"), cls="card-header"),
            Div(draft_followup(sample), cls="msg-draft"), cls="card") if sample else None,
    )


# ============================================================ CSV ==============
def _campaign_table(engine: str, cat: str = "all", months: int = 12, days: int = 14):
    """Return (headers, rows, filename_base) for an engine, or (None, None, None).

    Shared by both the CSV and XLSX exports so they never drift apart.
    """
    today = reference_date()
    if engine == "reminders":
        headers = ["patient_id", "client_id", "patient_name", "contact_phone", "gender",
                   "service", "category", "last_date", "due_date", "days_overdue",
                   "status", "message"]
        rows = [[r["patient_id"], r["client_id"], r.get("patient_name"), r.get("contact_phone"),
                 gender_label(r.get("gender")), r["service"], r["category"], r["last_date"],
                 r["due_date"], r["days_overdue"], r["status"], draft_reminder(r)]
                for r in due_rows(cat)]
        return headers, rows, f"fastclinic_reminders_{cat}_{today}"
    if engine == "lapsed":
        headers = ["patient_id", "client_id", "patient_name", "contact_phone", "gender",
                   "last_visit", "months_since", "visits", "lifetime_value", "message"]
        rows = [[r["patient_id"], r["client_id"], r.get("patient_name"), r.get("contact_phone"),
                 gender_label(r.get("gender")), _date(r["last_visit"]), r["months_since"],
                 r["visits"], r["lifetime_value"], draft_lapsed(r)]
                for r in lapsed_rows(months)]
        return headers, rows, f"fastclinic_lapsed_{months}mo_{today}"
    if engine == "followup":
        headers = ["patient_id", "client_id", "patient_name", "contact_phone", "consultation_id",
                   "consult_at", "categories", "diagnoses", "revenue_vat", "message"]
        rows = [[r["patient_id"], r["client_id"], r.get("patient_name"), r.get("contact_phone"),
                 r["consultation_id"], _date(r["consult_at"]), r["categories"], r["diagnoses"],
                 r["revenue_vat"], draft_followup(r)]
                for r in followup_rows(days)]
        return headers, rows, f"fastclinic_followup_{days}d_{today}"
    return None, None, None


def campaign_csv(engine: str, cat: str = "all", months: int = 12, days: int = 14):
    """Return (csv_text, filename) for an engine, or (None, None) if unknown."""
    headers, rows, fname = _campaign_table(engine, cat, months, days)
    if headers is None:
        return None, None
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    return buf.getvalue(), f"{fname}.csv"


def campaign_xlsx(engine: str, cat: str = "all", months: int = 12, days: int = 14):
    """Return (xlsx_bytes, filename) for an engine, or (None, None) if unknown."""
    from web.exports import build_xlsx
    headers, rows, fname = _campaign_table(engine, cat, months, days)
    if headers is None:
        return None, None
    return build_xlsx(headers, rows, sheet_name=engine.capitalize()), f"{fname}.xlsx"
