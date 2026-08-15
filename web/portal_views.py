"""Patient portal — appointments, invoices, messages, records, intake."""
from __future__ import annotations

from datetime import date, timedelta

from fasthtml.common import A, Button, Div, Form, H3, Input, Label, Option, P, Select, Span, Textarea

from web import access, appointments, billing, clinical, fhir_portal
from web.db import reference_date
from web.dashboards import _page_title, _table
from web.i18n import preserve, t


def portal_view(email: str, notice: str = "", week: str = "", clinician_id: int = 0,
                mode: str = "chat", booking_messages: list[dict] | None = None,
                appointment_type_code: str = "general"):
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

    clinicians = appointments.clinicians()
    appointment_types = appointments.appointment_types()
    selected_type = next(
        (item for item in appointment_types if item["code"] == appointment_type_code),
        appointment_types[0] if appointment_types else {"code": "general", "name": "General consultation"},
    )
    clinician_id = clinician_id or clinicians[0]["id"]
    today = date.fromisoformat(reference_date()[:10])
    ref = date.fromisoformat(week) if week else today
    ref -= timedelta(days=ref.weekday())
    if not week and ref + timedelta(days=4) < today:
        ref += timedelta(days=7)
    previous_week = (ref - timedelta(days=7)).isoformat()
    next_week = (ref + timedelta(days=7)).isoformat()
    week_slots = []
    if sid:
        for offset in range(5):
            day = ref + timedelta(days=offset)
            free = [s for s in appointments.day_schedule(clinician_id, day) if s["free"]][:12]
            week_slots.append((day, free))

    chooser = Form(
        Input(type="hidden", name="mode", value="classical"),
        Label(t("Practitioner"), Select(
            *[Option(c["name"], value=str(c["id"]), selected=c["id"] == clinician_id)
              for c in clinicians], name="clinician_id")),
        Label(t("Treatment"), Select(
            *[Option(item["name"], value=item["code"],
                     selected=item["code"] == selected_type["code"]) for item in appointment_types],
            name="appointment_type_code")),
        Input(type="hidden", name="week", value=ref.isoformat()),
        Button(t("View availability"), cls="btn", type="submit"),
        method="get", action="/portal", cls="record-actions",
    )
    calendar = Div(
        Div(
            A("←", href=f"/portal?mode=classical&week={previous_week}&clinician_id={clinician_id}&appointment_type_code={selected_type['code']}", cls="btn"),
            Span(f"{ref.strftime('%d %b')} – {(ref + timedelta(days=4)).strftime('%d %b %Y')}",
                 style="font-weight:700;"),
            A("→", href=f"/portal?mode=classical&week={next_week}&clinician_id={clinician_id}&appointment_type_code={selected_type['code']}", cls="btn"),
            cls="record-actions", style="justify-content:space-between;margin:12px 0;",
        ),
        Div(*[
            Div(
                H3(day.strftime("%a %d"), style="font-size:13px;"),
                *[
                    Form(
                        Input(type="hidden", name="clinician_id", value=str(clinician_id)),
                        Input(type="hidden", name="start_at", value=slot["start_at"]),
                        Input(type="hidden", name="appointment_type_code", value=selected_type["code"]),
                        Input(type="hidden", name="reason", value=selected_type["name"]),
                        Button(slot["time"], cls="btn", type="submit", title=t("Book this time")),
                        method="post", action="/portal/book",
                    ) for slot in free
                ] or [P(t("No free slots"), style="color:var(--text-mute);font-size:12px;")],
                cls="calendar-day",
            ) for day, free in week_slots
        ], cls="booking-week"),
    ) if sid else P(t("Ask the clinic to link this account to a patient record."))

    intake = Form(
        Label(t("Allergies"), Input(name="allergies", placeholder=t("None known"))),
        Label(t("Current medications"), Input(name="medications")),
        Label(t("Reason for visit"), Textarea(name="reason", rows=3)),
        Button(t("Submit intake"), cls="btn primary", type="submit"),
        method="post", action="/portal/intake",
        cls="sms-form",
    ) if sid else None

    upcoming_rows = []
    for appointment in appts:
        alternatives = []
        for offset in range(5):
            day = ref + timedelta(days=offset)
            alternatives.extend(
                slot for slot in appointments.day_schedule(appointment["clinician_id"], day)
                if slot["free"]
            )
        reschedule = Form(
            Select(*[Option(slot["start_at"], value=slot["start_at"])
                     for slot in alternatives[:20]] or [Option(t("No free slots"), value="")],
                   name="start_at", required=True),
            Button(t("Reschedule"), cls="btn", type="submit", disabled=not alternatives),
            method="post", action=f"/portal/appointments/{appointment['id']}/reschedule",
            cls="record-actions",
        )
        cancel = Form(
            Button(t("Cancel"), cls="btn", type="submit"), method="post",
            action=f"/portal/appointments/{appointment['id']}/cancel",
        )
        upcoming_rows.append([
            (appointment.get("start_at") or "")[:16], appointment.get("clinician_id") or "—",
            preserve(appointment.get("reason") or "—"), appointment.get("status"),
            Div(reschedule, cancel, cls="record-actions"),
        ])

    booking_messages = booking_messages or []
    chat = Div(
        Div(*[
            Div(preserve(message.get("content") or ""),
                cls=f"booking-message {message.get('role', 'assistant')}")
            for message in booking_messages
        ] or [Div(
            H3(t("How can I help with your appointment?")),
            P(t("Tell me the practitioner, treatment, or day you need. I’ll check live availability and confirm before booking.")),
            cls="booking-welcome",
        )], id="booking-chat-messages", cls="booking-chat-messages"),
        Form(
            Textarea(name="message", rows=2,
                     placeholder=t("For example: I need a general practitioner next Tuesday morning"),
                     required=True, autofocus=True),
            Button(t("Ask booking assistant"), cls="btn primary", type="submit"),
            method="post", action="/portal/booking/chat", cls="booking-composer",
        ),
        cls="card booking-chat", data_section="booking-assistant",
    )
    classical = Div(
        Div(H3(t("Book an appointment")), cls="card-header"),
        P(t("Choose a practitioner and an available time. Booking is confirmed immediately.")),
        chooser, calendar,
        cls="card", data_section="patient-booking",
    )
    tabs = Div(
        A(t("Assistant"), href="/portal", cls=f"btn{' primary' if mode != 'classical' else ''}"),
        A(t("Classical"), href="/portal?mode=classical", cls=f"btn{' primary' if mode == 'classical' else ''}"),
        cls="record-actions", style="margin-bottom:12px;",
    )
    return Div(
        _page_title(t("Patient portal"), email),
        P(notice, style="color:var(--ok);") if notice else None,
        tabs, classical if mode == "classical" else chat,
        Div(
            Div(H3(t("Upcoming appointments")), cls="card-header"),
            _table(["When", "Practitioner", "Reason", "Status", "Actions"],
                   upcoming_rows) if appts else P(t("No upcoming appointments.")),
            cls="card", data_section="patient-upcoming",
        ),
        Div(
            Div(H3(t("Invoices")), cls="card-header"),
            _table(["Code", "Total", "Paid", "Status"],
                   [[i.get("code"), i.get("total"), i.get("paid"), i.get("status")]
                    for i in invoices]) if invoices else P(t("No invoices.")),
            cls="card", data_section="patient-invoices", data_collapsed="true",
        ),
        Div(
            Div(H3(t("Coverage")), cls="card-header"),
            _table(["Payor", "Member ID", "Status"],
                   [[c.get("payor"), c.get("member_id") or "—", c.get("status")]
                    for c in coverages]) if coverages else P(t("No coverage on file.")),
            cls="card", data_section="patient-coverage", data_collapsed="true",
        ),
        Div(
            Div(H3(t("Messages")), cls="card-header"),
            _table(["Conversation", "Started"],
                   [[A(preserve(th["title"]), href=f"/messages?thread_id={th['id']}"),
                     (th.get("created_at") or "")[:16]]
                    for th in threads]) if threads else P(t("No messages.")),
            A(t("Open inbox"), href="/messages", cls="btn"),
            cls="card", data_section="patient-messages", data_collapsed="true",
        ),
        Div(
            Div(H3(t("Health records")), cls="card-header"),
            P(t("{n} imported documents", n=len(records))),
            A(t("Open my records"), href="/my-records", cls="btn"),
            cls="card", data_section="patient-records", data_collapsed="true",
        ),
        Div(Div(H3(t("Intake questionnaire")), cls="card-header"), intake, cls="card",
            data_section="patient-intake", data_collapsed="true") if intake else None,
    )


def booking_calendar_panel(email: str, week: str = "", clinician_id: int = 0):
    """Compact live calendar for the conversational booking right pane."""
    clinicians = appointments.clinicians()
    clinician_id = clinician_id or clinicians[0]["id"]
    today = date.fromisoformat(reference_date()[:10])
    start = date.fromisoformat(week) if week else today
    start -= timedelta(days=start.weekday())
    if not week and start + timedelta(days=4) < today:
        start += timedelta(days=7)
    columns = []
    for offset in range(5):
        day = start + timedelta(days=offset)
        free = [slot for slot in appointments.day_schedule(clinician_id, day) if slot["free"]][:8]
        columns.append(Div(
            H3(day.strftime("%a %d"), style="font-size:13px;"),
            *[Span(slot["time"], cls="calendar-time") for slot in free]
            or [P(t("Full"), style="color:var(--text-mute);font-size:12px;")],
            cls="calendar-day",
        ))
    return Div(
        Div(H3(t("Live availability")), cls="card-header"),
        P(t("Practitioner {id}", id=clinician_id), style="color:var(--text-mute);"),
        Div(*columns, cls="booking-calendar-rail"),
        A(t("Open classical booking"), href="/portal?mode=classical", cls="btn"),
        cls="right-pane booking-right-panel",
    )
