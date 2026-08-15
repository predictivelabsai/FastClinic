"""Appointments + availability — Phase 3 of the Clinic OS plan.

Greenfield: nothing in the Fast* estate had booking with real availability
(FastMeet only inserts rows). This provides slot generation from a clinician
working pattern, conflict detection, RSVP-style confirmation states, and a hook
that queues a Phase-2 reminder for the booked visit.

Appointments are operational state and live in the writable ops DB alongside
reminders / communications (web/activation_loop.py owns the connection).
"""
from __future__ import annotations

import hashlib
import secrets
import time as clock
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from web.activation_loop import _connect, query, _now, resolve_by_phone  # noqa: F401
from web.db import query as _main_query, reference_date

# --- clinician working pattern (a country/clinic-config concern; kept simple) ---
WORKING_DAYS = {0, 1, 2, 3, 4}          # Mon–Fri
DAY_START, DAY_END = time(9, 0), time(17, 0)
LUNCH_START, LUNCH_END = time(13, 0), time(14, 0)
SLOT_MIN = 20                            # default appointment length
ACTIVE_STATUSES = ("scheduled", "confirmed", "checked-in")   # occupy a slot; cancelled/no-show free it
STATUSES = ("scheduled", "confirmed", "checked-in", "cancelled", "completed", "no-show")


def clinicians() -> list[dict]:
    """Clinicians known to the clinic, from consultation history."""
    rows = _main_query(
        "SELECT DISTINCT clinician_id FROM consultation "
        "WHERE clinician_id IS NOT NULL ORDER BY clinician_id")
    found = [{"id": r["clinician_id"], "name": f"Practitioner {r['clinician_id']}"} for r in rows]
    return found or [{"id": 1, "name": "Practitioner 1"}]


def appointment_types() -> list[dict]:
    return query("SELECT * FROM appointment_type WHERE active=1 ORDER BY name")


def appointment_type(code: str) -> dict:
    rows = query("SELECT * FROM appointment_type WHERE code=? AND active=1", (code,))
    return rows[0] if rows else {"code": "general", "name": "General consultation", "duration_min": SLOT_MIN}


def locations() -> list[dict]:
    return query("SELECT * FROM clinic_location WHERE active=1 ORDER BY name")


def rooms(location_id: int | None = None) -> list[dict]:
    if location_id is None:
        return query("SELECT * FROM clinic_room WHERE active=1 ORDER BY name")
    return query(
        "SELECT * FROM clinic_room WHERE active=1 AND location_id=? ORDER BY name",
        (location_id,),
    )


def booking_policy(code: str = "default") -> dict:
    rows = query("SELECT * FROM booking_policy WHERE code=? AND active=1", (code,))
    return rows[0] if rows else {
        "hold_seconds": 300, "minimum_notice_minutes": 0,
        "cancellation_notice_minutes": 120, "timezone": "Europe/Tallinn",
    }


def availability_rules(clinician_id: int) -> list[dict]:
    return query(
        "SELECT * FROM practitioner_availability_rule WHERE clinician_id=? "
        "ORDER BY weekday,start_time", (clinician_id,))


def save_availability_rule(clinician_id: int, weekday: int, start_time: str,
                           end_time: str, slot_minutes: int = SLOT_MIN) -> int:
    if weekday not in range(7):
        raise ValueError("weekday must be between 0 and 6")
    start, end = time.fromisoformat(start_time[:5]), time.fromisoformat(end_time[:5])
    if start >= end or slot_minutes < 10 or slot_minutes > 240:
        raise ValueError("invalid availability window")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO practitioner_availability_rule "
            "(clinician_id,weekday,start_time,end_time,slot_minutes,active) VALUES(?,?,?,?,?,1)",
            (clinician_id, weekday, start.strftime("%H:%M"), end.strftime("%H:%M"), slot_minutes),
        )
        conn.commit()
        return cur.lastrowid


def delete_availability_rule(rule_id: int, clinician_id: int | None = None) -> bool:
    with _connect() as conn:
        if clinician_id is None:
            row = conn.execute("SELECT id FROM practitioner_availability_rule WHERE id=?", (rule_id,)).fetchone()
            conn.execute("DELETE FROM practitioner_availability_rule WHERE id=?", (rule_id,))
        else:
            row = conn.execute(
                "SELECT id FROM practitioner_availability_rule WHERE id=? AND clinician_id=?",
                (rule_id, clinician_id),
            ).fetchone()
            conn.execute(
                "DELETE FROM practitioner_availability_rule WHERE id=? AND clinician_id=?",
                (rule_id, clinician_id),
            )
        conn.commit()
        return bool(row)


def _parse(dt: str) -> datetime:
    return datetime.fromisoformat(dt.replace("T", " ")[:16])


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def _utc_fmt(dt: datetime, timezone: str = "Europe/Tallinn") -> str:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("unknown appointment timezone") from exc
    return dt.replace(tzinfo=zone).astimezone(ZoneInfo("UTC")).isoformat()


def _day_slots(d: date, clinician_id: int = 1) -> list[datetime]:
    """All candidate slot start-times for a working day (empty if not a work day)."""
    exceptions = query(
        "SELECT * FROM practitioner_availability_exception "
        "WHERE clinician_id=? AND exception_date=? ORDER BY id", (clinician_id, d.isoformat()))
    if exceptions and not any(bool(row["available"]) for row in exceptions):
        return []
    rules = query(
        "SELECT * FROM practitioner_availability_rule WHERE clinician_id=? "
        "AND weekday=? AND active=1 ORDER BY start_time", (clinician_id, d.weekday()))
    custom_rules = bool(rules)
    if not rules:
        if d.weekday() not in WORKING_DAYS:
            return []
        rules = [{"start_time": DAY_START.strftime("%H:%M"),
                  "end_time": DAY_END.strftime("%H:%M"), "slot_minutes": SLOT_MIN}]
    slots = []
    for rule in rules:
        start_time = time.fromisoformat(str(rule["start_time"])[:5])
        end_time = time.fromisoformat(str(rule["end_time"])[:5])
        step = max(10, int(rule.get("slot_minutes") or SLOT_MIN))
        cur, end = datetime.combine(d, start_time), datetime.combine(d, end_time)
        while cur + timedelta(minutes=step) <= end:
            t = cur.time()
            if custom_rules or not (LUNCH_START <= t < LUNCH_END):
                slots.append(cur)
            cur += timedelta(minutes=step)
    return slots


def appointments_for(clinician_id: int, d: date) -> list[dict]:
    day = d.isoformat()
    return query(
        "SELECT * FROM appointment WHERE clinician_id=? AND substr(start_at,1,10)=? "
        "AND status IN ('scheduled','confirmed','checked-in','completed') ORDER BY start_at",
        (clinician_id, day))


def day_schedule(clinician_id: int, d: date) -> list[dict]:
    """Every slot for a clinician on a day, each tagged free / booked (+ who)."""
    booked = {}
    for a in appointments_for(clinician_id, d):
        booked[_parse(a["start_at"]).strftime("%H:%M")] = a
    held = query(
        "SELECT start_at FROM appointment_hold WHERE clinician_id=? AND substr(start_at,1,10)=? "
        "AND expires_at>? AND consumed_at IS NULL", (clinician_id, d.isoformat(), int(clock.time())))
    for row in held:
        booked.setdefault(_parse(row["start_at"]).strftime("%H:%M"), {
            "id": 0, "subject_id": "—", "reason": "Temporarily held", "status": "held",
        })
    out = []
    for s in _day_slots(d, clinician_id):
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
    room: str = "",
) -> bool:
    sql = (
        f"SELECT id, start_at, end_at FROM appointment WHERE clinician_id=? "
        f"AND status IN {ACTIVE_STATUSES}"
    )
    params: list = [clinician_id]
    if exclude_id is not None:
        sql += " AND id <> ?"
        params.append(exclude_id)
    rows = list(conn.execute(sql, tuple(params)).fetchall())
    if room:
        room_sql = f"SELECT id,start_at,end_at FROM appointment WHERE room=? AND status IN {ACTIVE_STATUSES}"
        room_params: list = [room]
        if exclude_id is not None:
            room_sql += " AND id <> ?"
            room_params.append(exclude_id)
        known = {row["id"] for row in rows}
        rows.extend(row for row in conn.execute(room_sql, tuple(room_params)).fetchall()
                    if row["id"] not in known)
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
         appointment_type_code: str = "general", location: str = "",
         timezone: str = "Europe/Tallinn", hold_token: str = "",
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
        if _overlaps(conn, clinician_id, start, end, room=room):
            raise SlotTaken(f"Clinician {clinician_id} is busy at {_fmt(start)}")
        hold_hash = hashlib.sha256(hold_token.encode()).hexdigest() if hold_token else ""
        if hold_hash:
            held = conn.execute(
                "SELECT * FROM appointment_hold WHERE token_hash=? AND subject_id=? "
                "AND clinician_id=? AND start_at=? AND expires_at>? AND consumed_at IS NULL",
                (hold_hash, subject_id, clinician_id, _fmt(start), int(clock.time())),
            ).fetchone()
            if not held:
                raise SlotTaken("The temporary slot hold has expired")
        cur = conn.execute(
            """INSERT INTO appointment (subject_id, party_id, clinician_id, start_at,
                   end_at, status, reason, room, appointment_type_code, location,
                   timezone, start_at_utc, end_at_utc, created_at)
               VALUES (?,?,?,?,?, 'scheduled', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (subject_id, party_id, clinician_id, _fmt(start), _fmt(end),
             reason, room, appointment_type_code, location, timezone,
             _utc_fmt(start, timezone), _utc_fmt(end, timezone), _now()))
        appt_id = cur.lastrowid
        conn.execute(
            "INSERT INTO appointment_participant(appointment_id,participant_type,"
            "participant_ref,response_status,created_at) VALUES(?,?,?,?,?)",
            (appt_id, "patient", f"Patient/{subject_id}", "accepted", _now()),
        )
        conn.execute(
            "INSERT INTO appointment_participant(appointment_id,participant_type,"
            "participant_ref,response_status,created_at) VALUES(?,?,?,?,?)",
            (appt_id, "practitioner", f"Practitioner/{clinician_id}", "accepted", _now()),
        )
        if with_reminder:
            conn.execute(
                "INSERT INTO appointment_notification(appointment_id,channel,status,"
                "scheduled_at,created_at) VALUES(?,?,?,?,?)",
                (appt_id, "sms", "queued",
                 _fmt(start - timedelta(days=1)), _now()),
            )
        if hold_hash:
            conn.execute("UPDATE appointment_hold SET consumed_at=? WHERE token_hash=?",
                         (int(clock.time()), hold_hash))
        conn.commit()
    if with_reminder:
        _queue_appointment_reminder(subject_id, start, reason)
    return appt_id


def hold_slot(subject_id: int, clinician_id: int, start_at: str,
              duration_min: int = SLOT_MIN, ttl_seconds: int | None = None) -> str:
    start = _parse(start_at)
    end = start + timedelta(minutes=duration_min)
    now = int(clock.time())
    ttl_seconds = int(ttl_seconds or booking_policy()["hold_seconds"])
    if ttl_seconds < 30 or ttl_seconds > 1800:
        raise ValueError("slot hold must be between 30 and 1800 seconds")
    token = secrets.token_urlsafe(24)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM appointment_hold WHERE expires_at<=?", (now,))
        if _overlaps(conn, clinician_id, start, end):
            raise SlotTaken(f"Clinician {clinician_id} is busy at {_fmt(start)}")
        other = conn.execute(
            "SELECT start_at,end_at FROM appointment_hold WHERE clinician_id=? "
            "AND expires_at>? AND consumed_at IS NULL", (clinician_id, now)).fetchall()
        for row in other:
            if start < _parse(row["end_at"]) and end > _parse(row["start_at"]):
                raise SlotTaken("The slot is temporarily held")
        conn.execute(
            "INSERT INTO appointment_hold(token_hash,subject_id,clinician_id,start_at,end_at,expires_at,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (token_hash, subject_id, clinician_id, _fmt(start), _fmt(end), now + ttl_seconds, _now()),
        )
        conn.commit()
    return token


def _queue_appointment_reminder(subject_id: int, start: datetime, reason: str) -> None:
    from web.activation_loop import create_reminder
    create_reminder(
        subject_id, "appointment", source_engine="appointments",
        due_date=(start - timedelta(days=1)).date().isoformat(),
        sms_text=(f"Reminder: you have an appointment at FastClinic on "
                  f"{start.strftime('%a %d %b %H:%M')}"
                  + (f" ({reason})" if reason else "") + "."))


def set_status(appt_id: int, status: str, *, actor: str = "", reason: str = "") -> None:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    with _connect() as conn:
        row = conn.execute("SELECT status FROM appointment WHERE id=?", (appt_id,)).fetchone()
        if not row:
            return
        conn.execute("UPDATE appointment SET status=? WHERE id=?", (status, appt_id))
        conn.execute(
            "INSERT INTO appointment_status_history(appointment_id,from_status,to_status,actor_email,reason,changed_at) "
            "VALUES(?,?,?,?,?,?)",
            (appt_id, row["status"], status, actor, reason, _now()),
        )
        conn.commit()


def cancel_for_subject(appt_id: int, subject_id: int, *, actor: str = "") -> bool:
    row = get(appt_id)
    if not row or row.get("subject_id") != subject_id or row.get("status") not in ACTIVE_STATUSES:
        return False
    set_status(appt_id, "cancelled", actor=actor, reason="patient cancellation")
    return True


def reschedule_for_subject(appt_id: int, subject_id: int, start_at: str,
                           *, actor: str = "") -> bool:
    row = get(appt_id)
    if not row or row.get("subject_id") != subject_id or row.get("status") not in ACTIVE_STATUSES:
        return False
    updated = update(appt_id, start_at=start_at)
    if updated:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO appointment_status_history(appointment_id,from_status,to_status,actor_email,reason,changed_at) "
                "VALUES(?,?,?,?,?,?)",
                (appt_id, row["status"], updated["status"], actor, "patient reschedule", _now()),
            )
            conn.commit()
    return bool(updated)


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
        next_room = row["room"] if room is None else room
        if next_status in ACTIVE_STATUSES and _overlaps(
            conn, next_clinician, next_start, next_end, exclude_id=appt_id, room=next_room
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
                   status=?, reason=?, room=?, start_at_utc=?, end_at_utc=?,
                   version=version+1 WHERE id=?""",
            (
                next_subject,
                party_id,
                next_clinician,
                _fmt(next_start),
                _fmt(next_end),
                next_status,
                row["reason"] if reason is None else reason,
                next_room,
                _utc_fmt(next_start, row["timezone"] or "Europe/Tallinn"),
                _utc_fmt(next_end, row["timezone"] or "Europe/Tallinn"),
                appt_id,
            ),
        )
        conn.commit()
    return get(appt_id)


def upcoming(limit: int = 100, clinician_id: int | None = None) -> list[dict]:
    today = reference_date()
    clinician_clause = " AND clinician_id=?" if clinician_id is not None else ""
    params = (today, clinician_id, limit) if clinician_id is not None else (today, limit)
    return query(
        "SELECT * FROM appointment WHERE substr(start_at,1,10) >= ? "
        "AND status IN ('scheduled','confirmed','checked-in')" + clinician_clause
        + " ORDER BY start_at LIMIT ?",
        params)


def get(appt_id: int) -> dict | None:
    rows = query("SELECT * FROM appointment WHERE id=?", (appt_id,))
    return rows[0] if rows else None


def appointment_counts() -> dict:
    rows = query("SELECT status, COUNT(*) AS n FROM appointment GROUP BY status")
    return {r["status"]: r["n"] for r in rows}
