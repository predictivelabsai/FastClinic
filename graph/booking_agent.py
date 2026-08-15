"""Patient-safe LangGraph booking conversation.

The graph interprets natural-language scheduling requests and reads live
availability. Mutations stay outside the model: a booking is created only when
the deterministic confirmation node sees an explicit confirmation for a slot
already proposed to the authenticated patient.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from web import appointments
from web.db import reference_date


class BookingState(TypedDict, total=False):
    message: str
    subject_id: int
    actor: str
    pending: dict[str, Any]
    intent: str
    clinician_id: int
    requested_date: str
    requested_time: str
    appointment_type_code: str
    duration_min: int
    sql_context: list[dict]
    slots: list[dict]
    response: str
    booked_id: int


def _date_from_text(text: str) -> date:
    today = date.fromisoformat(reference_date()[:10])
    lowered = text.lower()
    match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if match:
        return date.fromisoformat(match.group(1))
    if "tomorrow" in lowered:
        return today + timedelta(days=1)
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for target, name in enumerate(weekdays):
        if name in lowered:
            delta = (target - today.weekday()) % 7
            return today + timedelta(days=delta or 7)
    return today if today.weekday() < 5 else today + timedelta(days=7 - today.weekday())


def _heuristic_extract(message: str) -> dict[str, Any]:
    lowered = message.lower().strip()
    confirmation = bool(re.fullmatch(r"(yes|yes please|confirm|book it|please book it|ok|okay)[.! ]*", lowered))
    time_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", lowered)
    clinician_match = re.search(r"(?:doctor|practitioner|clinician)\s*#?\s*(\d+)", lowered)
    services = appointments.appointment_types()
    service = next(
        (item for item in services
         if item["code"].replace("-", " ") in lowered or item["name"].lower() in lowered),
        next((item for item in services if item["code"] == "general"),
             {"code": "general", "duration_min": appointments.SLOT_MIN}),
    )
    return {
        "intent": "confirm" if confirmation else "search",
        "requested_date": _date_from_text(message).isoformat(),
        "requested_time": time_match.group(0) if time_match else "",
        "clinician_id": int(clinician_match.group(1)) if clinician_match else 0,
        "appointment_type_code": service["code"],
        "duration_min": int(service["duration_min"]),
    }


def _interpret(state: BookingState) -> BookingState:
    extracted = _heuristic_extract(state.get("message", ""))
    # A configured model may query only the schema-approved booking context.
    # Results are advisory; dates, identifiers and all mutations remain under
    # deterministic validation below.
    try:
        from web import booking_sql
        if extracted["intent"] != "confirm":
            context = booking_sql.ask(state.get("message", ""))
            extracted["sql_context"] = context["rows"][:10]
            matching_type = next(
                (row for row in context["rows"] if row.get("code") and row.get("duration_min")), None)
            if matching_type:
                extracted["appointment_type_code"] = str(matching_type["code"])
                extracted["duration_min"] = int(matching_type["duration_min"])
    except Exception:
        pass
    return {**state, **extracted}


def _route(state: BookingState) -> str:
    return "confirm" if state.get("intent") == "confirm" else "search"


def _search(state: BookingState) -> BookingState:
    clinicians = appointments.clinicians()
    previous = state.get("pending") or {}
    clinician_id = state.get("clinician_id") or previous.get("clinician_id") or clinicians[0]["id"]
    wanted = state.get("requested_time")
    if wanted and previous.get("candidate_slots"):
        exact_start = next(
            (value for value in previous["candidate_slots"] if str(value)[11:16] == wanted), None)
        if exact_start:
            try:
                hold_token = appointments.hold_slot(
                    int(state["subject_id"]), int(clinician_id), str(exact_start),
                    int(state.get("duration_min") or previous.get("duration_min") or appointments.SLOT_MIN))
            except appointments.SlotTaken:
                return {**state, "pending": {}, "response": (
                    "That time is no longer available. Tell me the day again and I’ll refresh the calendar.")}
            pending = {"clinician_id": clinician_id, "start_at": exact_start,
                       "reason": previous.get("reason") or "General consultation",
                       "hold_token": hold_token,
                       "appointment_type_code": previous.get("appointment_type_code") or state.get("appointment_type_code") or "general",
                       "duration_min": int(previous.get("duration_min") or state.get("duration_min") or appointments.SLOT_MIN)}
            return {**state, "pending": pending, "response": (
                f"I’ve selected **{exact_start}** with Practitioner {clinician_id}. "
                "Reply **confirm** and I’ll book it.")}
    requested = date.fromisoformat(state["requested_date"])
    free = [slot for slot in appointments.day_schedule(clinician_id, requested) if slot["free"]]
    if wanted:
        exact = [slot for slot in free if slot["time"] == wanted]
        if exact:
            try:
                hold_token = appointments.hold_slot(
                    int(state["subject_id"]), int(clinician_id), exact[0]["start_at"],
                    int(state.get("duration_min") or appointments.SLOT_MIN))
            except appointments.SlotTaken:
                return {**state, "pending": {}, "response": (
                    "That time is no longer available. Tell me another time and I’ll check it.")}
            pending = {"clinician_id": clinician_id, "start_at": exact[0]["start_at"],
                       "reason": state.get("message", "General consultation")[:240],
                       "hold_token": hold_token,
                       "appointment_type_code": state.get("appointment_type_code") or "general",
                       "duration_min": int(state.get("duration_min") or appointments.SLOT_MIN)}
            return {**state, "slots": free[:8], "pending": pending,
                    "response": (f"I found {wanted} on {requested.strftime('%A %d %B')} with "
                                 f"Practitioner {clinician_id}. Reply **confirm** and I’ll book it.")}
    if not free:
        return {**state, "slots": [], "response": (
            f"There are no free times with Practitioner {clinician_id} on "
            f"{requested.strftime('%A %d %B')}. Tell me another day and I’ll check it.")}
    times = ", ".join(slot["time"] for slot in free[:8])
    return {**state, "slots": free[:8], "pending": {
        "clinician_id": clinician_id, "candidate_slots": [slot["start_at"] for slot in free[:8]],
        "reason": state.get("message", "General consultation")[:240],
        "appointment_type_code": state.get("appointment_type_code") or "general",
        "duration_min": int(state.get("duration_min") or appointments.SLOT_MIN),
    }, "response": (
        f"Practitioner {clinician_id} is available on {requested.strftime('%A %d %B')} at "
        f"**{times}**. Reply with a time, for example **10:20**.")}


def _confirm(state: BookingState) -> BookingState:
    pending = state.get("pending") or {}
    start_at = pending.get("start_at")
    clinician_id = int(pending.get("clinician_id") or 0)
    if not start_at or not clinician_id:
        return {**state, "response": "I don’t have a selected time yet. Tell me the day and preferred time first."}
    try:
        booked_id = appointments.book(
            int(state["subject_id"]), clinician_id, start_at,
            reason=pending.get("reason") or "General consultation",
            duration_min=int(pending.get("duration_min") or appointments.SLOT_MIN),
            appointment_type_code=pending.get("appointment_type_code") or "general",
            hold_token=pending.get("hold_token") or "",
        )
    except appointments.SlotTaken:
        return {**state, "pending": {}, "response": (
            "That time was booked by someone else just now. Tell me the day again and I’ll refresh availability.")}
    return {**state, "pending": {}, "booked_id": booked_id,
            "response": f"Confirmed — your appointment is booked for **{start_at}** with Practitioner {clinician_id}."}


_builder = StateGraph(BookingState)
_builder.add_node("interpret", _interpret)
_builder.add_node("search", _search)
_builder.add_node("confirm", _confirm)
_builder.add_edge(START, "interpret")
_builder.add_conditional_edges("interpret", _route, {"search": "search", "confirm": "confirm"})
_builder.add_edge("search", END)
_builder.add_edge("confirm", END)
BOOKING_GRAPH = _builder.compile()


def respond(message: str, subject_id: int, actor: str, pending: dict | None = None) -> dict:
    state = BOOKING_GRAPH.invoke({
        "message": (message or "").strip(), "subject_id": subject_id,
        "actor": actor, "pending": pending or {},
    })
    return {
        "response": state.get("response", "Tell me which practitioner and day you need."),
        "pending": state.get("pending") or {}, "slots": state.get("slots") or [],
        "booked_id": state.get("booked_id"),
    }
