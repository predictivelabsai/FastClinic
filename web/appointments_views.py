"""Server-rendered appointment views: day schedule + booking + upcoming."""
from __future__ import annotations

from datetime import date, timedelta

from fasthtml.common import (
    Div, H1, H3, P, A, Form, Label, Input, Select, Option, Button,
    Table, Thead, Tbody, Tr, Th, Td, Span,
)

from web.db import db_exists, reference_date
from web.i18n import format_date, format_number, preserve, t
from web.layout import kpi_card
from web import appointments as appt


def _clinician_options(sel: int):
    return [Option(c["name"], value=str(c["id"]), selected=(c["id"] == sel))
            for c in appt.clinicians()]


def _booking_form(clinician_id: int, day: str, free_slots: list[dict]):
    if free_slots:
        time_field = Select(*[Option(s["time"], value=s["start_at"]) for s in free_slots],
                            name="start_at", required=True)
    else:
        time_field = Span(t("No free slots on this day"), style="color:var(--text-mute);")
    types = appt.appointment_types()
    rooms = appt.rooms()
    return Form(
        Div(
            Label("Patient ID", Input(name="subject_id", type="number",
                                      placeholder="e.g. 1206", required=True)),
            Label("Time", time_field),
            Label(t("Treatment"), Select(*[
                Option(item["name"], value=item["code"]) for item in types
            ], name="appointment_type_code")),
            Label(t("Room"), Select(
                Option(t("No room"), value=""),
                *[Option(item["name"], value=item["code"]) for item in rooms],
                name="room",
            )),
            Label("Reason", Input(name="reason", placeholder="e.g. Immunisation")),
            Input(type="hidden", name="clinician_id", value=str(clinician_id)),
            Input(type="hidden", name="day", value=day),
            Button("Book", cls="btn primary", type="submit"),
            style="display:flex; gap:10px; align-items:end; flex-wrap:wrap;",
        ),
        **{"hx-post": "/appointments/book", "hx-target": "#appt-body", "hx-swap": "outerHTML"},
    )


def _status_pill(s: str):
    tone = {"scheduled": "neutral", "confirmed": "completed",
            "checked-in": "completed", "cancelled": "warn",
            "completed": "completed", "no-show": "warn"}.get(s, "neutral")
    return Span(t(s), cls=f"status-pill {tone}")


def _availability_editor(clinician_id: int, can_manage: bool):
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    rules = appt.availability_rules(clinician_id)
    rows = [[weekdays[int(r["weekday"])], r["start_time"], r["end_time"],
             f"{r['slot_minutes']} min",
             Form(Button(t("Remove"), cls="btn", type="submit"), method="post",
                  action=f"/appointments/availability/{r['id']}/delete") if can_manage else ""]
            for r in rules]
    form = Form(
        Input(type="hidden", name="clinician_id", value=str(clinician_id)),
        Label(t("Weekday"), Select(*[Option(t(name), value=str(index))
                                     for index, name in enumerate(weekdays)], name="weekday")),
        Label(t("Start"), Input(type="time", name="start_time", value="09:00", required=True)),
        Label(t("End"), Input(type="time", name="end_time", value="17:00", required=True)),
        Label(t("Slot length"), Input(type="number", name="slot_minutes", value="20", min="10", max="240")),
        Button(t("Add availability"), cls="btn primary", type="submit"),
        method="post", action="/appointments/availability", cls="record-actions",
    ) if can_manage else None
    table = Table(
        Thead(Tr(*[Th(t(h)) for h in ["Day", "Start", "End", "Slot", ""]])),
        Tbody(*[Tr(*[Td(c) for c in row]) for row in rows]), cls="tbl",
    ) if rows else P(t("Default clinic hours apply until custom availability is added."))
    return Div(Div(H3(t("Practitioner availability")), cls="card-header"), form, table,
               cls="card", data_section="practitioner-availability", data_collapsed="true")


def _week_overview(clinician_id: int, selected_day: date):
    monday = selected_day - timedelta(days=selected_day.weekday())
    rows = []
    for offset in range(7):
        current = monday + timedelta(days=offset)
        schedule = appt.day_schedule(clinician_id, current)
        free = sum(slot["free"] for slot in schedule)
        rows.append([
            A(format_date(current.isoformat()),
              href=f"/appointments?clinician_id={clinician_id}&day={current.isoformat()}&mode=day"),
            len(schedule) - free, free,
        ])
    return Div(
        Div(H3(t("Week overview")), cls="card-header"),
        Table(Thead(Tr(Th(t("Day")), Th(t("Booked")), Th(t("Free")))),
              Tbody(*[Tr(*[Td(value) for value in row]) for row in rows]), cls="tbl"),
        cls="card", data_section="week-overview",
    )


def _body(clinician_id: int, day: str, can_manage_availability: bool = True,
          mode: str = "day"):
    d = date.fromisoformat(day)
    schedule = appt.day_schedule(clinician_id, d)
    free = [s for s in schedule if s["free"]]
    counts = appt.appointment_counts()

    cards = Div(
        kpi_card("Scheduled", counts.get("scheduled", 0)),
        kpi_card("Confirmed", counts.get("confirmed", 0)),
        kpi_card("Free slots today", len(free), neutral=True),
        kpi_card("Cancelled", counts.get("cancelled", 0), neutral=True),
        cls="kpi-grid", style="grid-template-columns:repeat(4,1fr);",
    )

    sched_rows = []
    for s in schedule:
        a = s["appointment"]
        if a:
            sched_rows.append([
                s["time"],
                A(f"#{a['subject_id']}", href=f"/patients/{a['subject_id']}"),
                preserve(a.get("reason") or "—"),
                _status_pill(a["status"]),
                Div(
                    A("Confirm", href="#", cls="btn",
                      **{"hx-post": f"/appointments/{a['id']}/status?to=confirmed",
                         "hx-target": "#appt-body", "hx-swap": "outerHTML"}),
                    A("Check in", href="#", cls="btn",
                      **{"hx-post": f"/appointments/{a['id']}/status?to=checked-in",
                         "hx-target": "#appt-body", "hx-swap": "outerHTML"}),
                    A("Complete", href="#", cls="btn",
                      **{"hx-post": f"/appointments/{a['id']}/status?to=completed",
                         "hx-target": "#appt-body", "hx-swap": "outerHTML"}),
                    A("No-show", href="#", cls="btn",
                      **{"hx-post": f"/appointments/{a['id']}/status?to=no-show",
                         "hx-target": "#appt-body", "hx-swap": "outerHTML"}),
                    A("Cancel", href="#", cls="btn",
                      **{"hx-post": f"/appointments/{a['id']}/status?to=cancelled",
                         "hx-target": "#appt-body", "hx-swap": "outerHTML"}),
                    style="display:flex; gap:6px;") if a.get("id") else "",
            ])
        else:
            sched_rows.append([s["time"], Span("— free —", style="color:var(--text-mute);"),
                               "", "", ""])

    up = appt.upcoming(limit=100 if mode == "agenda" else 25, clinician_id=clinician_id)
    up_rows = [[f"{format_date(u['start_at'])} {u['start_at'][11:16]}",
                t("Clinician {id}", id=u["clinician_id"]),
                A(f"#{u['subject_id']}", href=f"/patients/{u['subject_id']}"),
                preserve(u.get("reason") or "—"), _status_pill(u["status"])] for u in up]

    return Div(
        cards,
        Form(
            Div(
                Label("Clinician", Select(*_clinician_options(clinician_id),
                                          name="clinician_id")),
                Label("Date", Input(name="day", type="date", value=day)),
                Button("View", cls="btn", type="submit"),
                style="display:flex; gap:10px; align-items:end;",
            ),
            method="get", action="/appointments",
        ),
        Div(
            A(t("Day"), href=f"/appointments?clinician_id={clinician_id}&day={day}&mode=day",
              cls=f"btn{' primary' if mode == 'day' else ''}"),
            A(t("Week"), href=f"/appointments?clinician_id={clinician_id}&day={day}&mode=week",
              cls=f"btn{' primary' if mode == 'week' else ''}"),
            A(t("Agenda"), href=f"/appointments?clinician_id={clinician_id}&day={day}&mode=agenda",
              cls=f"btn{' primary' if mode == 'agenda' else ''}"),
            cls="record-actions",
        ),
        _week_overview(clinician_id, d) if mode == "week" else None,
        _availability_editor(clinician_id, can_manage_availability),
        Div(Div(H3(t("Book — Clinician {id}, {date}", id=clinician_id,
                       date=format_date(day))), cls="card-header"),
            _booking_form(clinician_id, day, free), cls="card"),
        Div(Div(H3(t("Schedule — {date}", date=format_date(day))), cls="card-header"),
            Table(Thead(Tr(*[Th(t(h)) for h in ["Time", "Patient", "Reason", "Status", ""]])),
                  Tbody(*[Tr(*[Td(c) for c in r]) for r in sched_rows]), cls="tbl")
            if sched_rows else P("Not a working day."), cls="card"),
        Div(Div(H3(t("Upcoming ({count})", count=format_number(len(up)))), cls="card-header"),
            Table(Thead(Tr(*[Th(t(h)) for h in ["When", "Clinician", "Patient", "Reason", "Status"]])),
                  Tbody(*[Tr(*[Td(c) for c in r]) for r in up_rows]), cls="tbl")
            if up_rows else P("No upcoming appointments."), cls="card"),
        id="appt-body",
    )


def _default_clinician() -> int:
    cs = appt.clinicians()
    return cs[0]["id"] if cs else 1


def view(clinician_id: int | None = None, day: str | None = None,
         can_manage_availability: bool = True, mode: str = "day"):
    if not db_exists():
        from web.dashboards import _no_data_view
        return _no_data_view()
    clinician_id = clinician_id or _default_clinician()
    day = day or reference_date()[:10]
    mode = mode if mode in {"day", "week", "agenda"} else "day"
    return Div(
        Div(Div(H1("Appointments"),
                Div("Book into real availability — no double-booking", cls="sub")),
            cls="page-title"),
        _body(clinician_id, day, can_manage_availability, mode),
    )


def body(clinician_id: int, day: str, can_manage_availability: bool = True):
    """Swappable body for htmx responses."""
    return _body(clinician_id, day, can_manage_availability)
