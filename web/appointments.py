"""Appointments + availability — Phase 3 of the Clinic OS plan.

Greenfield: nothing in the Fast* estate had booking with real availability
(FastMeet only inserts rows). This provides slot generation from a clinician
working pattern, conflict detection, RSVP-style confirmation states, and a hook
that queues a Phase-2 reminder for the booked visit.

Appointments are operational state and live in the writable ops DB alongside
reminders / communications (web/activation_loop.py owns the connection).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from web.activation_loop import _connect, query, _now, resolve_by_phone  # noqa: F401
from web.db import query as _main_query, reference_date

# --- clinician working pattern (a country/clinic-config concern; kept simple) ---
WORKING_DAYS = {0, 1, 2, 3, 4}          # Mon–Fri
DAY_START, DAY_END = time(9, 0), time(17, 0)
LUNCH_START, LUNCH_END = time(13, 0), time(14, 0)
SLOT_MIN = 20                            # default appointment length
ACTIVE_STATUSES = ("scheduled", "confirmed")   # occupy a slot; 'cancelled' frees it
STATUSES = ("scheduled", "confirmed", "cancelled", "completed")


def clinicians() -> list[dict]:
    """Clinicians known to the clinic, from consultation history."""
    rows = _main_query(
        "SELECT DISTINCT clinician_id FROM consultation "
        "WHERE clinician_id IS NOT NULL ORDER BY clinician_id")
    return [{"id": r["clinician_id"], "name": f"Clinician {r['clinician_id']}"} for r in rows]


def _parse(dt: str) -> datetime:
    return datetime.fromisoformat(dt.replace("T", " ")[:16])


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def _day_slots(d: date) -> list[datetime]:
    """All candidate slot start-times for a working day (empty if not a work day)."""
    if d.weekday() not in WORKING_DAYS:
        return []
    slots, cur = [], datetime.combine(d, DAY_START)
    end = datetime.combine(d, DAY_END)
    while cur + timedelta(minutes=SLOT_MIN) <= end:
        t = cur.time()
        if not (LUNCH_START <= t < LUNCH_END):
            slots.append(cur)
        cur += timedelta(minutes=SLOT_MIN)
    return slots


def appointments_for(clinician_id: int, d: date) -> list[dict]:
    day = d.isoformat()
    return query(
        "SELECT * FROM appointment WHERE clinician_id=? AND substr(start_at,1,10)=? "
        "AND status IN ('scheduled','confirmed','completed') ORDER BY start_at",
        (clinician_id, day))


def day_schedule(clinician_id: int, d: date) -> list[dict]:
    """Every slot for a clinician on a day, each tagged free / booked (+ who)."""
    booked = {}
    for a in appointments_for(clinician_id, d):
        booked[_parse(a["start_at"]).strftime("%H:%M")] = a
    out = []
    for s in _day_slots(d):
        hhmm = s.strftime("%H:%M")
        a = booked.get(hhmm)
        out.append({"start_at": _fmt(s), "time": hhmm,
                    "free": a is None, "appointment": a})
    return out


def _overlaps(
    conn,
    clinician_id: int,
    start: datetime,
    end: datetime,
    *,
    exclude_id: int | None = None,
) -> bool:
    sql = (
        f"SELECT id, start_at, end_at FROM appointment WHERE clinician_id=? "
        f"AND status IN {ACTIVE_STATUSES}"
    )
    params: list = [clinician_id]
    if exclude_id is not None:
        sql += " AND id <> ?"
        params.append(exclude_id)
    rows = conn.execute(sql, tuple(params)).fetchall()
    for r in rows:
        if r["start_at"] and r["end_at"]:
            es, ee = _parse(r["start_at"]), _parse(r["end_at"])
            if start < ee and end > es:      # half-open overlap
                return True
    return False


class SlotTaken(Exception):
    """Raised when a booking would double-book a clinician."""


def book(subject_id: int | None, clinician_id: int, start_at: str, *,
         duration_min: int = SLOT_MIN, reason: str = "", room: str = "",
         with_reminder: bool = True) -> int:
    """Book an appointment, refusing to double-book. Returns the appointment id."""
    start = _parse(start_at)
    end = start + timedelta(minutes=duration_min)
    rows = _main_query(
        "SELECT party_id FROM subject_party_role WHERE subject_id=? "
        "ORDER BY is_primary DESC LIMIT 1", (subject_id,))
    party_id = rows[0]["party_id"] if rows else None
    with _connect() as conn:
        # Serialize the overlap check and insert so concurrent clients cannot
        # reserve the same clinician slot between those two operations.
        conn.execute("BEGIN IMMEDIATE")
        if _overlaps(conn, clinician_id, start, end):
            raise SlotTaken(f"Clinician {clinician_id} is busy at {_fmt(start)}")
        cur = conn.execute(
            """INSERT INTO appointment (subject_id, party_id, clinician_id, start_at,
                   end_at, status, reason, room, created_at)
               VALUES (?,?,?,?,?, 'scheduled', ?, ?, ?)""",
            (subject_id, party_id, clinician_id, _fmt(start), _fmt(end),
             reason, room, _now()))
        appt_id = cur.lastrowid
        conn.commit()
    if with_reminder:
        _queue_appointment_reminder(subject_id, start, reason)
    return appt_id


def _queue_appointment_reminder(subject_id: int, start: datetime, reason: str) -> None:
    from web.activation_loop import create_reminder
    create_reminder(
        subject_id, "appointment", source_engine="appointments",
        due_date=(start - timedelta(days=1)).date().isoformat(),
        sms_text=(f"Reminder: you have an appointment at FastClinic on "
                  f"{start.strftime('%a %d %b %H:%M')}"
                  + (f" ({reason})" if reason else "") + "."))


def set_status(appt_id: int, status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    with _connect() as conn:
        conn.execute("UPDATE appointment SET status=? WHERE id=?", (status, appt_id))
        conn.commit()


def update(
    appt_id: int,
    *,
    subject_id: int | None = None,
    clinician_id: int | None = None,
    start_at: str | None = None,
    duration_min: int | None = None,
    reason: str | None = None,
    room: str | None = None,
    status: str | None = None,
) -> dict | None:
    """Update an appointment atomically, preserving conflict detection."""
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM appointment WHERE id=?", (appt_id,)).fetchone()
        if not row:
            return None
        current_start = _parse(row["start_at"])
        current_end = _parse(row["end_at"])
        next_start = _parse(start_at) if start_at is not None else current_start
        current_duration = max(1, int((current_end - current_start).total_seconds() // 60))
        next_duration = duration_min if duration_min is not None else current_duration
        if next_duration < 10 or next_duration > 240:
            raise ValueError("duration_min must be between 10 and 240")
        next_end = next_start + timedelta(minutes=next_duration)
        next_clinician = clinician_id if clinician_id is not None else row["clinician_id"]
        next_status = status if status is not None else row["status"]
        if next_status not in STATUSES:
            raise ValueError(f"unknown status {next_status!r}")
        if next_status in ACTIVE_STATUSES and _overlaps(
            conn, next_clinician, next_start, next_end, exclude_id=appt_id
        ):
            raise SlotTaken(f"Clinician {next_clinician} is busy at {_fmt(next_start)}")
        next_subject = subject_id if subject_id is not None else row["subject_id"]
        party_id = row["party_id"]
        if subject_id is not None:
            parties = _main_query(
                "SELECT party_id FROM subject_party_role WHERE subject_id=? "
                "ORDER BY is_primary DESC LIMIT 1",
                (subject_id,),
            )
            party_id = parties[0]["party_id"] if parties else None
        conn.execute(
            """UPDATE appointment
               SET subject_id=?, party_id=?, clinician_id=?, start_at=?, end_at=?,
                   status=?, reason=?, room=? WHERE id=?""",
            (
                next_subject,
                party_id,
                next_clinician,
                _fmt(next_start),
                _fmt(next_end),
                next_status,
                row["reason"] if reason is None else reason,
                row["room"] if room is None else room,
                appt_id,
            ),
        )
        conn.commit()
    return get(appt_id)


def upcoming(limit: int = 100) -> list[dict]:
    today = reference_date()
    return query(
        "SELECT * FROM appointment WHERE substr(start_at,1,10) >= ? "
        "AND status IN ('scheduled','confirmed') ORDER BY start_at LIMIT ?",
        (today, limit))


def get(appt_id: int) -> dict | None:
    rows = query("SELECT * FROM appointment WHERE id=?", (appt_id,))
    return rows[0] if rows else None


def appointment_counts() -> dict:
    rows = query("SELECT status, COUNT(*) AS n FROM appointment GROUP BY status")
    return {r["status"]: r["n"] for r in rows}
