"""Server-rendered appointment views: day schedule + booking + upcoming."""
from __future__ import annotations

from datetime import date

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
    return Form(
        Div(
            Label("Patient ID", Input(name="subject_id", type="number",
                                      placeholder="e.g. 1206", required=True)),
            Label("Time", time_field),
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
            "cancelled": "warn", "completed": "completed"}.get(s, "neutral")
    return Span(t(s), cls=f"status-pill {tone}")


def _body(clinician_id: int, day: str):
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
                    A("Cancel", href="#", cls="btn",
                      **{"hx-post": f"/appointments/{a['id']}/status?to=cancelled",
                         "hx-target": "#appt-body", "hx-swap": "outerHTML"}),
                    style="display:flex; gap:6px;"),
            ])
        else:
            sched_rows.append([s["time"], Span("— free —", style="color:var(--text-mute);"),
                               "", "", ""])

    up = appt.upcoming(limit=25)
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


def view(clinician_id: int | None = None, day: str | None = None):
    if not db_exists():
        from web.dashboards import _no_data_view
        return _no_data_view()
    clinician_id = clinician_id or _default_clinician()
    day = day or reference_date()[:10]
    return Div(
        Div(Div(H1("Appointments"),
                Div("Book into real availability — no double-booking", cls="sub")),
            cls="page-title"),
        _body(clinician_id, day),
    )


def body(clinician_id: int, day: str):
    """Swappable body for htmx responses."""
    return _body(clinician_id, day)
