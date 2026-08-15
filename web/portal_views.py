"""Patient portal — appointments, invoices, messages, records, intake."""
from __future__ import annotations

from datetime import date, timedelta

from fasthtml.common import A, Button, Div, Form, H3, Input, Label, Option, P, Select, Textarea

from web import access, appointments, billing, clinical, fhir_portal
from web.db import reference_date
from web.dashboards import _page_title, _table
from web.i18n import preserve, t


def portal_view(email: str, notice: str = ""):
    prof = access.profile(email)
    sid = prof.get("subject_id")
    appts = []
    invoices = []
    threads = []
    coverages = []
    if sid:
        appts = [a for a in appointments.upcoming(200) if a.get("subject_id") == sid][:12]
        invoices = [i for i in billing.invoices(200) if i.get("subject_id") == sid][:12]
        threads = clinical.threads(subject_id=sid)
        coverages = clinical.coverages_for(sid)
    records = fhir_portal.records_for_email(email)

    ref = date.fromisoformat(reference_date()[:10])
    while ref.weekday() != 0:
        ref += timedelta(days=1)
    slots = []
    if sid:
        try:
            slots = [s for s in appointments.day_schedule(1, ref) if s["free"]][:8]
        except Exception:
            slots = []

    book = Form(
        Input(type="hidden", name="clinician_id", value="1"),
        Select(*[Option(s["start_at"], value=s["start_at"]) for s in slots] or [Option(t("No free slots"), value="")],
               name="start_at"),
        Input(name="reason", placeholder=t("Reason")),
        Button(t("Book"), cls="btn primary", type="submit", disabled=not slots),
        method="post", action="/portal/book",
        style="display:flex;gap:8px;flex-wrap:wrap;",
    ) if sid else P(t("Ask the clinic to link this account to a patient record."))

    intake = Form(
        Label(t("Allergies"), Input(name="allergies", placeholder=t("None known"))),
        Label(t("Current medications"), Input(name="medications")),
        Label(t("Reason for visit"), Textarea(name="reason", rows=3)),
        Button(t("Submit intake"), cls="btn primary", type="submit"),
        method="post", action="/portal/intake",
        cls="sms-form",
    ) if sid else None

    return Div(
        _page_title(t("Patient portal"), email),
        P(notice, style="color:var(--ok);") if notice else None,
        Div(
            Div(H3(t("Book an appointment")), cls="card-header"),
            book,
            cls="card",
        ),
        Div(
            Div(H3(t("Upcoming appointments")), cls="card-header"),
            _table(["When", "Clinician", "Reason", "Status"],
                   [[(a.get("start_at") or "")[:16], a.get("clinician_id") or "—",
                     preserve(a.get("reason") or "—"), a.get("status")]
                    for a in appts]) if appts else P(t("No upcoming appointments.")),
            cls="card",
        ),
        Div(
            Div(H3(t("Invoices")), cls="card-header"),
            _table(["Code", "Total", "Paid", "Status"],
                   [[i.get("code"), i.get("total"), i.get("paid"), i.get("status")]
                    for i in invoices]) if invoices else P(t("No invoices.")),
            cls="card",
        ),
        Div(
            Div(H3(t("Coverage")), cls="card-header"),
            _table(["Payor", "Member ID", "Status"],
                   [[c.get("payor"), c.get("member_id") or "—", c.get("status")]
                    for c in coverages]) if coverages else P(t("No coverage on file.")),
            cls="card",
        ),
        Div(
            Div(H3(t("Messages")), cls="card-header"),
            _table(["Conversation", "Started"],
                   [[A(preserve(th["title"]), href=f"/messages?thread_id={th['id']}"),
                     (th.get("created_at") or "")[:16]]
                    for th in threads]) if threads else P(t("No messages.")),
            A(t("Open inbox"), href="/messages", cls="btn"),
            cls="card",
        ),
        Div(
            Div(H3(t("Health records")), cls="card-header"),
            P(t("{n} imported documents", n=len(records))),
            A(t("Open my records"), href="/my-records", cls="btn"),
            cls="card",
        ),
        Div(Div(H3(t("Intake questionnaire")), cls="card-header"), intake, cls="card") if intake else None,
    )
