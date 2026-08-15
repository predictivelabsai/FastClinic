"""Server-rendered charting, orders, tasks, messages, staff, and audit views."""
from __future__ import annotations

from fasthtml.common import (
    A, Button, Div, Form, H3, Input, Label, Option, P, Select, Span, Textarea,
)

from web import access, clinical
from web import clinic_queries as q
from web.dashboards import _page_title, _table
from web.i18n import preserve, t


def _pill(status: str):
    tone = {
        "in-progress": "neutral", "active": "neutral", "requested": "neutral",
        "finished": "completed", "completed": "completed",
        "cancelled": "warn", "draft": "neutral", "planned": "neutral",
    }.get(status, "neutral")
    return Span(t(status), cls=f"status-pill {tone}")


def chart_view(pid: int, notice: str = ""):
    patient = q.patient_detail(pid)
    if not patient:
        return Div(_page_title("Patient not found"),
                   Div(P(t("No patient #{id}.", id=pid)), A("← Patients", href="/patients"), cls="card"))
    name = patient.get("official_name") or f"#{pid}"
    open_enc = clinical.active_encounter(pid)
    encounters = clinical.encounters_for(pid)
    notes = clinical.notes_for(pid)
    orders = clinical.orders(subject_id=pid, limit=20)
    tasks = clinical.tasks(subject_id=pid, limit=20)
    coverages = clinical.coverages_for(pid)
    imported = q.patient_consultations(pid)[:8]

    open_form = Form(
        Input(name="reason", placeholder=t("Reason for visit"),
              style="padding:8px 12px;border:1px solid var(--border);border-radius:8px;width:260px;"),
        Input(name="clinician_id", type="number", placeholder=t("Clinician ID"),
              style="padding:8px 12px;border:1px solid var(--border);border-radius:8px;width:140px;"),
        Button(t("Open encounter"), cls="btn primary", type="submit"),
        method="post", action=f"/patients/{pid}/chart/open",
        style="display:flex;gap:8px;flex-wrap:wrap;",
    ) if not open_enc else Form(
        Button(t("Finish encounter"), cls="btn", type="submit"),
        method="post", action=f"/patients/{pid}/chart/finish",
    )

    soap = Form(
        Input(type="hidden", name="encounter_id", value=str(open_enc["id"]) if open_enc else ""),
        Label(t("Subjective"), Textarea(name="subjective", rows=3)),
        Label(t("Objective"), Textarea(name="objective", rows=3)),
        Label(t("Assessment"), Textarea(name="assessment", rows=3)),
        Label(t("Plan"), Textarea(name="plan", rows=3)),
        Button(t("Save note"), cls="btn primary", type="submit"),
        method="post", action=f"/patients/{pid}/chart/note",
        cls="sms-form",
    )

    order_form = Form(
        Select(*[Option(k, value=k) for k in clinical.ORDER_KINDS], name="kind"),
        Input(name="name", placeholder=t("Order name"), required=True),
        Input(name="code", placeholder=t("Code")),
        Input(type="hidden", name="encounter_id", value=str(open_enc["id"]) if open_enc else ""),
        Button(t("Place order"), cls="btn primary", type="submit"),
        method="post", action=f"/patients/{pid}/chart/order",
        style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;",
    )

    task_form = Form(
        Input(name="title", placeholder=t("Task"), required=True),
        Input(name="due_date", type="date"),
        Input(type="hidden", name="encounter_id", value=str(open_enc["id"]) if open_enc else ""),
        Button(t("Add task"), cls="btn", type="submit"),
        method="post", action=f"/patients/{pid}/chart/task",
        style="display:flex;gap:8px;flex-wrap:wrap;",
    )

    cover_form = Form(
        Input(name="payor", placeholder=t("Insurer / payor"), required=True),
        Input(name="member_id", placeholder=t("Member ID")),
        Button(t("Add coverage"), cls="btn", type="submit"),
        method="post", action=f"/patients/{pid}/chart/coverage",
        style="display:flex;gap:8px;flex-wrap:wrap;",
    )

    enc_rows = [
        [e["started_at"][:16] if e.get("started_at") else "—",
         preserve(e.get("reason") or "—"), _pill(e["status"]),
         e.get("clinician_id") or "—"]
        for e in encounters
    ]
    note_rows = [
        [(n.get("created_at") or "")[:16],
         preserve((n.get("assessment") or n.get("subjective") or n.get("plan") or "—")[:160])]
        for n in notes
    ]
    order_rows = [
        [o["kind"], preserve(o["name"]), _pill(o["status"]),
         Form(Button(t("Complete"), cls="btn", type="submit"),
              method="post", action=f"/orders/{o['id']}/complete")
         if o["status"] == "active" else ""]
        for o in orders
    ]
    task_rows = [
        [preserve(tk["title"]), _pill(tk["status"]), tk.get("due_date") or "—",
         Form(Button(t("Done"), cls="btn", type="submit"),
              method="post", action=f"/tasks/{tk['id']}/complete")
         if tk["status"] != "completed" else ""]
        for tk in tasks
    ]
    cover_rows = [[preserve(c["payor"]), c.get("member_id") or "—", _pill(c["status"])] for c in coverages]
    imported_rows = [[c["consult_at"][:10] if c.get("consult_at") else "—",
                      c.get("item_count") or 0, preserve((c.get("diagnoses") or "—")[:80])]
                     for c in imported]

    return Div(
        _page_title(
            t("Chart"), name,
            actions=A(t("Patient record"), href=f"/patients/{pid}", cls="btn"),
        ),
        P(notice, style="color:var(--ok);") if notice else None,
        Div(
            Div(H3(t("Encounter")), cls="card-header"),
            P(t("Open encounter #{id}", id=open_enc["id"]) if open_enc else t("No active encounter.")),
            open_form,
            cls="card",
        ),
        Div(Div(H3(t("SOAP note")), cls="card-header"), soap, cls="card"),
        Div(Div(H3(t("Orders")), cls="card-header"), order_form,
            _table(["Kind", "Name", "Status", ""], order_rows) if order_rows else P(t("No orders.")),
            cls="card"),
        Div(Div(H3(t("Tasks")), cls="card-header"), task_form,
            _table(["Task", "Status", "Due", ""], task_rows) if task_rows else P(t("No tasks.")),
            cls="card"),
        Div(Div(H3(t("Coverage")), cls="card-header"), cover_form,
            _table(["Payor", "Member ID", "Status"], cover_rows) if cover_rows else P(t("No coverage on file.")),
            cls="card"),
        Div(Div(H3(t("Chart encounters")), cls="card-header"),
            _table(["Started", "Reason", "Status", "Clinician"], enc_rows) if enc_rows else P(t("None yet.")),
            cls="card"),
        Div(Div(H3(t("Saved notes")), cls="card-header"),
            _table(["When", "Summary"], note_rows) if note_rows else P(t("No chart notes.")),
            cls="card"),
        Div(Div(H3(t("Imported consultations")), cls="card-header"),
            _table(["Date", "Items", "Diagnoses"], imported_rows) if imported_rows else P(t("None.")),
            cls="card"),
    )


def orders_view(kind: str = "", status: str = "active",
                allowed_subject_ids: set[int] | frozenset[int] | None = None):
    rows = clinical.orders(kind=kind or None, status=status or None, limit=200)
    if allowed_subject_ids is not None:
        rows = [row for row in rows if row.get("subject_id") in allowed_subject_ids]
        counts = {state: sum(row["status"] == state for row in rows)
                  for state in clinical.ORDER_STATUSES}
    else:
        counts = clinical.order_counts()
    table = [
        [A(f"#{r['subject_id']}", href=f"/patients/{r['subject_id']}/chart"),
         r["kind"], preserve(r["name"]), _pill(r["status"]),
         (r.get("created_at") or "")[:16],
         Form(Button(t("Complete"), cls="btn", type="submit"),
              method="post", action=f"/orders/{r['id']}/complete")
         if r["status"] == "active" else ""]
        for r in rows
    ]
    return Div(
        _page_title(t("Orders"), t("Labs, imaging, referrals, and medications")),
        Div(
            Div(H3(t("Queue")), cls="card-header"),
            P(t("{n} active", n=counts.get("active", 0))),
            Form(
                Select(Option(t("All kinds"), value="", selected=not kind),
                       *[Option(k, value=k, selected=k == kind) for k in clinical.ORDER_KINDS],
                       name="kind"),
                Select(Option(t("All statuses"), value="", selected=not status),
                       *[Option(s, value=s, selected=s == status) for s in clinical.ORDER_STATUSES],
                       name="status"),
                Button(t("Filter"), cls="btn", type="submit"),
                method="get", action="/orders",
                style="display:flex;gap:8px;flex-wrap:wrap;",
            ),
            _table(["Patient", "Kind", "Name", "Status", "Created", ""], table) if table else P(t("No orders match.")),
            cls="card",
        ),
    )


def tasks_view(status: str = "requested",
               allowed_subject_ids: set[int] | frozenset[int] | None = None):
    rows = clinical.tasks(status=status or None, limit=200)
    if allowed_subject_ids is not None:
        rows = [row for row in rows if row.get("subject_id") in allowed_subject_ids]
    table = [
        [A(f"#{r['subject_id']}", href=f"/patients/{r['subject_id']}/chart"),
         preserve(r["title"]), _pill(r["status"]), r.get("due_date") or "—",
         Form(Button(t("Complete"), cls="btn", type="submit"),
              method="post", action=f"/tasks/{r['id']}/complete")
         if r["status"] != "completed" else ""]
        for r in rows
    ]
    return Div(
        _page_title(t("Tasks"), t("Care coordination")),
        Div(
            Div(H3(t("Board")), cls="card-header"),
            Form(
                Select(Option(t("All statuses"), value="", selected=not status),
                       *[Option(s, value=s, selected=s == status) for s in clinical.TASK_STATUSES],
                       name="status"),
                Button(t("Filter"), cls="btn", type="submit"),
                method="get", action="/tasks",
                style="display:flex;gap:8px;",
            ),
            _table(["Patient", "Task", "Status", "Due", ""], table) if table else P(t("No tasks.")),
            cls="card",
        ),
    )


def messages_view(subject_id: int | None = None, thread_id: int | None = None, notice: str = "",
                  allowed_subject_ids: set[int] | frozenset[int] | None = None):
    items = clinical.threads(subject_id=subject_id)
    if allowed_subject_ids is not None:
        items = [item for item in items if item.get("subject_id") in allowed_subject_ids]
    current = clinical.thread(thread_id) if thread_id else (items[0] if items else None)
    if current and allowed_subject_ids is not None and current.get("subject_id") not in allowed_subject_ids:
        current = None
    msgs = clinical.messages(current["id"]) if current else []
    thread_rows = [
        [A(preserve(th["title"]), href=f"/messages?thread_id={th['id']}"),
         th.get("subject_id") or "—", (th.get("created_at") or "")[:16]]
        for th in items
    ]
    msg_rows = [
        [m.get("sender_email") or "—", preserve(m["body"]), (m.get("created_at") or "")[:16]]
        for m in msgs
    ]
    compose = Form(
        Input(name="title", placeholder=t("Subject"), required=True),
        Input(name="subject_id", type="number", placeholder=t("Patient ID"),
              value=str(subject_id or "")),
        Textarea(name="body", placeholder=t("Message"), required=True, rows=3),
        Button(t("Start conversation"), cls="btn primary", type="submit"),
        method="post", action="/messages/new",
        cls="sms-form",
    )
    reply = None
    if current:
        reply = Form(
            Textarea(name="body", placeholder=t("Reply"), required=True, rows=3),
            Button(t("Send"), cls="btn primary", type="submit"),
            method="post", action=f"/messages/{current['id']}/reply",
            cls="sms-form",
        )
    return Div(
        _page_title(t("Messages"), t("In-clinic conversations")),
        P(notice, style="color:var(--ok);") if notice else None,
        Div(Div(H3(t("New thread")), cls="card-header"), compose, cls="card"),
        Div(Div(H3(t("Threads")), cls="card-header"),
            _table(["Title", "Patient", "Started"], thread_rows) if thread_rows else P(t("No conversations.")),
            cls="card"),
        Div(Div(H3(current["title"] if current else t("Conversation")), cls="card-header"),
            _table(["From", "Message", "When"], msg_rows) if msg_rows else P(t("Select a thread.")),
            reply,
            cls="card"),
    )


def staff_view(notice: str = ""):
    rows = [
        [preserve(p["email"]), p["role"], p.get("subject_id") or "—", p.get("clinician_id") or "—"]
        for p in access.list_profiles()
    ]
    form = Form(
        Input(name="email", type="email", placeholder=t("Email"), required=True),
        Select(*[Option(r, value=r) for r in access.ROLES], name="role"),
        Input(name="subject_id", type="number", placeholder=t("Patient ID")),
        Input(name="clinician_id", type="number", placeholder=t("Clinician ID")),
        Button(t("Save role"), cls="btn primary", type="submit"),
        method="post", action="/settings/roles",
        style="display:flex;gap:8px;flex-wrap:wrap;",
    )
    return Div(
        _page_title(t("Role settings"), t("Choose which FastClinic workspace each account can access")),
        P(notice, style="color:var(--ok);") if notice else None,
        Div(Div(H3(t("Assign")), cls="card-header"), form, cls="card"),
        Div(Div(H3(t("Profiles")), cls="card-header"),
            _table(["Email", "Role", "Patient", "Clinician"], rows) if rows else P(t("No accounts yet.")),
            cls="card"),
    )


def audit_view():
    rows = [
        [(r.get("created_at") or "")[:19], r.get("actor_email") or "—",
         r.get("action") or "—", f"{r.get('resource')} {r.get('item_id') or ''}".strip()]
        for r in access.recent_audit(150)
    ]
    return Div(
        _page_title(t("Access audit"), t("Chart, order, message, and role changes")),
        Div(Div(H3(t("Recent events")), cls="card-header"),
            _table(["When", "Who", "Action", "Resource"], rows) if rows else P(t("No events yet.")),
            cls="card"),
    )


def medbackend_oauth_view(email: str, notice: str = ""):
    from web import medbackend_oauth
    latest = medbackend_oauth.latest(email)
    rows = [
        ["Configuration", "Ready" if medbackend_oauth.configured() else "Incomplete"],
        ["OAuth flow", "Authorization Code + PKCE"],
        ["Test account", medbackend_oauth.TEST_EMAIL],
        ["Last status", (latest or {}).get("status") or "Not tested"],
        ["Patient records visible", (latest or {}).get("patient_count") if latest else "—"],
    ]
    return Div(
        _page_title(t("MedBackend OAuth"), t("Patient-authorized connectivity test")),
        P(notice, style="color:var(--ok);") if notice else None,
        Div(
            Div(H3(t("OAuth 2.0 status")), cls="card-header"),
            _table(["Field", "Value"], rows),
            P(t("The access token is used once for Me and PatientList and is not stored.")),
            A(t("Connect MedBackend as patient"), href="/integrations/medbackend/patient/start",
              cls="btn primary") if email.strip().lower() == medbackend_oauth.TEST_EMAIL else
            P(t("Sign in with the configured patient test account to start OAuth.")),
            cls="card",
        ),
    )
