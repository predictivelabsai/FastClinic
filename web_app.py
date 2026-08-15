"""FastClinic Cockpit — human GP / general-practice clinic business cockpit.

FastHTML dashboards + customer-activation engines + AI chat, branded for FastClinic.

Run:
    python web_app.py            # http://localhost:5005

Sign in through the canonical account/Google flow at /login.
"""
from __future__ import annotations

import os
import asyncio
import re
import secrets
import uuid
import logging
from urllib.parse import quote_plus, urlsplit

from dotenv import load_dotenv
load_dotenv()

from fasthtml.common import (
    fast_app, serve, Div, H1, P, A, NotStr, RedirectResponse, Script, Style,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, StreamingResponse
from starlette.responses import JSONResponse

from web.layout import page, right_pane_reference, LAYOUT_CSS
from web.landing import landing_page
from web.compliance import compliance_page
from web.seo import register_seo_routes
from web.developer import developer_page
from web import account_auth, google_auth
from web.i18n import (
    LANGUAGES, get_lang, localize_tree, safe_return_path, set_lang, t, using_lang,
)
from web import dashboards as dash
from web import activation as act
from web import commands as cmd
from web import consent
from web import activation_loop as aloop
from web import appointments as appt
from web import appointments_views as appt_views
from web import billing
from web import billing_views
from web import seo, seo_views
from web import help_views
from web import fhir_views
from web import fhir_portal
from web import access
from web import clinical
from web import clinical_views
from web import portal_views
from web import medbackend_oauth
from web.api import api

logger = logging.getLogger("fastclinic")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

# --- config ---
CLINIC_ENV = os.getenv("FASTCLINIC_ENV_LABEL", "FastClinic")
SECRET = os.getenv("FASTCLINIC_SECRET", os.getenv("MMG_COCKPIT_SECRET", secrets.token_hex(32)))
PORT = int(os.getenv("FASTCLINIC_PORT", os.getenv("MMG_COCKPIT_PORT", "5005")))
PUBLIC_URL = os.getenv("FASTSME_PUBLIC_URL", "https://fastclinic.dev").rstrip("/")
PUBLIC_HOSTS = {"fastclinic.dev", "www.fastclinic.dev", "clinic.fastsme.com"}

# FastClinic favicon — clinical blue mark (repo-root favicon.svg / favicon.ico,
# served by FastHTML's static handler).
FAVICON_HREF = "/favicon.svg"

app, rt = fast_app(
    live=False,
    pico=False,
    secret_key=SECRET,
    hdrs=[Style(LAYOUT_CSS)],
)
app.mount("/api", api)


async def redirect_public_aliases(request, call_next):
    """Keep legacy and www traffic on the canonical OAuth/session host."""
    forwarded = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    host = forwarded.split(",", 1)[0].strip().split(":", 1)[0].lower()
    canonical_host = urlsplit(PUBLIC_URL).hostname
    if host in PUBLIC_HOSTS and canonical_host and host != canonical_host:
        destination = f"{PUBLIC_URL}{request.url.path}"
        if request.url.query:
            destination += f"?{request.url.query}"
        return RedirectResponse(destination, status_code=308)
    return await call_next(request)


app.add_middleware(BaseHTTPMiddleware, dispatch=redirect_public_aliases)


@rt("/swagger.json", methods=["GET"])
def swagger_schema():
    return JSONResponse(api.openapi())


@rt("/developers", methods=["GET"])
def developers(session, request):
    return developer_page(get_lang(session, request))


@rt("/compliance", methods=["GET"])
def compliance(session, request):
    return compliance_page(get_lang(session, request))


# --- helpers ---
account_auth.register_fasthtml_routes(rt, app_name="FastClinic", session_key="user_email", success_path="/")


@rt("/set-lang/{code}")
def set_language(code: str, session, next: str = "/"):
    if code in LANGUAGES:
        set_lang(session, code)
    return RedirectResponse(safe_return_path(next), status_code=303)


def _auth(session) -> str | None:
    return session.get("user_email")


def _thread(session) -> str:
    tid = session.get("thread_id")
    if not tid:
        tid = f"fastclinic_{uuid.uuid4().hex[:12]}"
        session["thread_id"] = tid
    return tid


def _denied(session, email: str):
    if access.role_of(email) == "patient":
        return RedirectResponse("/portal", status_code=303)
    lang = get_lang(session)
    with using_lang(lang):
        return page(
            "dashboard", CLINIC_ENV, email, _thread(session),
            Div(H1(t("Not allowed")),
                P(t("This page is not available for your role."))),
            lang=lang,
        )


def _require(session, perm: str):
    email = _auth(session)
    if not email:
        return None, RedirectResponse("/login", status_code=303)
    if not access.can(email, perm):
        return email, _denied(session, email)
    return email, None


def _guarded(active: str, builder, perm: str | None = None):
    def handler(session):
        email, denied = _require(session, perm or active)
        if denied:
            return denied
        lang = get_lang(session)
        with using_lang(lang):
            return page(active, CLINIC_ENV, email, _thread(session), builder(), lang=lang)
    return handler


def _localized(session, value):
    """Localise full pages and HTMX fragments under the session language."""
    lang = get_lang(session)
    with using_lang(lang):
        built = value() if callable(value) else value
        return localize_tree(built, lang)


# --- auth ---
@rt("/login")
def get(session, request, error: str = ""):
    if _auth(session):
        return RedirectResponse("/", status_code=303)
    lang = get_lang(session, request)
    message = t("Invalid credentials", lang) if error else ""
    return landing_page(lang, auth_open=True, auth_error=message)



@rt("/auth/google")
def google_start(session, request):
    if not google_auth.enabled():
        return RedirectResponse("/login?error=Google+sign-in+is+not+configured", status_code=303)
    state = google_auth.new_state()
    session["google_oauth_state"] = state
    return RedirectResponse(google_auth.authorize_url(request, state), status_code=303)


@rt("/auth/google/callback")
def google_callback(session, request, code: str = "", state: str = "", error: str = ""):
    if error or not code or state != session.pop("google_oauth_state", None):
        return RedirectResponse("/login?error=Google+sign-in+failed", status_code=303)
    identity = google_auth.exchange(request, code)
    if not identity:
        return RedirectResponse("/login?error=Google+account+is+not+authorised", status_code=303)
    account_auth.accounts.link_google(identity["email"], identity["name"])
    session["user_email"] = identity["email"]
    return RedirectResponse("/", status_code=303)


@rt("/logout")
def get(session):
    session.pop("user_email", None)
    session.pop("thread_id", None)
    return RedirectResponse("/login", status_code=303)


# Favicon (favicon.svg + favicon.ico) is served from the app root by FastHTML's
# static handler; the FastClinic mark lives at repo root and web/static/.


# --- overview ---
@rt("/")
def get(session, request):
    if not _auth(session):
        return landing_page(get_lang(session, request))
    if access.role_of(_auth(session)) == "patient":
        return RedirectResponse("/portal", status_code=303)
    return _guarded("dashboard", dash.overview_view)(session)


# --- clinic ---
@rt("/patients")
def get(session, q: str = ""):
    return _guarded("patients", lambda: dash.patients_view(q))(session)


@rt("/patients/{pid}")
def get(session, pid: int):
    if not _auth(session):
        return RedirectResponse("/login", status_code=303)
    lang = get_lang(session)
    with using_lang(lang):
        email = _auth(session)
        if not access.can(email, "patients"):
            return _denied(session, email)
        access.audit(email, "read", "subject", pid)
        return page("patients", CLINIC_ENV, email, _thread(session),
                    dash.patient_detail_view(pid), lang=lang)


@rt("/my-records")
def get(session):
    email, denied = _require(session, "my-records")
    if denied:
        return denied
    lang = get_lang(session)
    with using_lang(lang):
        return page("my-records", CLINIC_ENV, email, _thread(session),
                    fhir_portal.records_view(email), lang=lang)


@rt("/my-records/{bundle_id}/download")
def get(session, bundle_id: str):
    email, denied = _require(session, "my-records")
    if denied:
        return denied
    content = fhir_portal.xml_for_email(email, bundle_id)
    if content is None:
        return Response("Not found", status_code=404)
    filename = re.sub(r"[^A-Za-z0-9._-]", "-", bundle_id) + ".fhir.xml"
    return Response(
        content,
        media_type=fhir_portal.FHIR_XML_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@rt("/my-records/{bundle_id}")
def get(session, bundle_id: str):
    email, denied = _require(session, "my-records")
    if denied:
        return denied
    view = fhir_portal.record_view(email, bundle_id)
    if view is None:
        return Response("Not found", status_code=404)
    lang = get_lang(session)
    with using_lang(lang):
        return page("my-records", CLINIC_ENV, email, _thread(session), view, lang=lang)


@rt("/patients/{pid}/chart")
def get(session, pid: int, notice: str = ""):
    email, denied = _require(session, "chart")
    if denied:
        return denied
    access.audit(email, "read", "chart", pid)
    lang = get_lang(session)
    with using_lang(lang):
        return page("chart", CLINIC_ENV, email, _thread(session),
                    clinical_views.chart_view(pid, notice), lang=lang)


@rt("/patients/{pid}/chart/open")
def post(session, pid: int, reason: str = "", clinician_id: int = 0):
    email, denied = _require(session, "chart")
    if denied:
        return denied
    try:
        clinical.open_encounter(
            pid, clinician_id=clinician_id or None, reason=reason, actor=email,
        )
        notice = "Encounter opened"
    except clinical.ClinicalError as exc:
        notice = str(exc)
    return RedirectResponse(f"/patients/{pid}/chart?notice={notice}", status_code=303)


@rt("/patients/{pid}/chart/finish")
def post(session, pid: int):
    email, denied = _require(session, "chart")
    if denied:
        return denied
    open_enc = clinical.active_encounter(pid)
    if open_enc:
        clinical.finish_encounter(open_enc["id"], actor=email)
    return RedirectResponse(f"/patients/{pid}/chart?notice=Encounter+finished", status_code=303)


@rt("/patients/{pid}/chart/note")
def post(session, pid: int, encounter_id: int = 0, subjective: str = "",
         objective: str = "", assessment: str = "", plan: str = ""):
    email, denied = _require(session, "chart")
    if denied:
        return denied
    try:
        clinical.add_note(
            pid, encounter_id=encounter_id or None, subjective=subjective,
            objective=objective, assessment=assessment, plan=plan, actor=email,
        )
        notice = "Note saved"
    except clinical.ClinicalError as exc:
        notice = str(exc)
    return RedirectResponse(f"/patients/{pid}/chart?notice={notice}", status_code=303)


@rt("/patients/{pid}/chart/order")
def post(session, pid: int, kind: str = "lab", name: str = "", code: str = "",
         encounter_id: int = 0):
    email, denied = _require(session, "orders")
    if denied:
        return denied
    try:
        clinical.place_order(
            pid, kind, name, encounter_id=encounter_id or None, code=code, actor=email,
        )
        notice = "Order placed"
    except clinical.ClinicalError as exc:
        notice = str(exc)
    return RedirectResponse(f"/patients/{pid}/chart?notice={notice}", status_code=303)


@rt("/patients/{pid}/chart/task")
def post(session, pid: int, title: str = "", due_date: str = "", encounter_id: int = 0):
    email, denied = _require(session, "tasks")
    if denied:
        return denied
    try:
        clinical.add_task(
            pid, title, encounter_id=encounter_id or None, due_date=due_date, actor=email,
        )
        notice = "Task added"
    except clinical.ClinicalError as exc:
        notice = str(exc)
    return RedirectResponse(f"/patients/{pid}/chart?notice={notice}", status_code=303)


@rt("/patients/{pid}/chart/coverage")
def post(session, pid: int, payor: str = "", member_id: str = ""):
    email, denied = _require(session, "chart")
    if denied:
        return denied
    try:
        clinical.add_coverage(pid, payor, member_id=member_id, actor=email)
        notice = "Coverage saved"
    except clinical.ClinicalError as exc:
        notice = str(exc)
    return RedirectResponse(f"/patients/{pid}/chart?notice={notice}", status_code=303)


@rt("/orders")
def get(session, kind: str = "", status: str = "active"):
    return _guarded("orders", lambda: clinical_views.orders_view(kind, status))(session)


@rt("/orders/{order_id}/complete")
def post(session, order_id: int):
    email, denied = _require(session, "orders")
    if denied:
        return denied
    try:
        row = clinical.set_order_status(order_id, "completed", actor=email)
        return RedirectResponse(f"/patients/{row['subject_id']}/chart?notice=Order+completed", status_code=303)
    except clinical.ClinicalError:
        return RedirectResponse("/orders", status_code=303)


@rt("/tasks")
def get(session, status: str = "requested"):
    return _guarded("tasks", lambda: clinical_views.tasks_view(status))(session)


@rt("/tasks/{task_id}/complete")
def post(session, task_id: int):
    email, denied = _require(session, "tasks")
    if denied:
        return denied
    try:
        row = clinical.set_task_status(task_id, "completed", actor=email)
        return RedirectResponse(f"/patients/{row['subject_id']}/chart?notice=Task+completed", status_code=303)
    except clinical.ClinicalError:
        return RedirectResponse("/tasks", status_code=303)


@rt("/messages")
def get(session, thread_id: int = 0, notice: str = ""):
    email, denied = _require(session, "messages")
    if denied:
        return denied
    prof = access.profile(email)
    sid = prof["subject_id"] if prof["role"] == "patient" else None
    lang = get_lang(session)
    with using_lang(lang):
        return page(
            "messages", CLINIC_ENV, email, _thread(session),
            clinical_views.messages_view(sid, thread_id or None, notice),
            lang=lang,
        )


@rt("/messages/new")
def post(session, title: str = "", body: str = "", subject_id: int = 0):
    email, denied = _require(session, "messages")
    if denied:
        return denied
    prof = access.profile(email)
    sid = subject_id or prof.get("subject_id")
    try:
        th = clinical.start_thread(
            title, subject_id=sid or None, body=body,
            sender_email=email, sender_role=prof["role"],
        )
        return RedirectResponse(f"/messages?thread_id={th['id']}&notice=Sent", status_code=303)
    except clinical.ClinicalError as exc:
        return RedirectResponse(f"/messages?notice={exc}", status_code=303)


@rt("/messages/{thread_id}/reply")
def post(session, thread_id: int, body: str = ""):
    email, denied = _require(session, "messages")
    if denied:
        return denied
    prof = access.profile(email)
    if prof["role"] == "patient":
        th = clinical.thread(thread_id)
        if not th or th.get("subject_id") != prof.get("subject_id"):
            return _denied(session, email)
    try:
        clinical.post_message(thread_id, body, sender_email=email, sender_role=prof["role"])
        return RedirectResponse(f"/messages?thread_id={thread_id}&notice=Sent", status_code=303)
    except clinical.ClinicalError as exc:
        return RedirectResponse(f"/messages?notice={exc}", status_code=303)


@rt("/portal")
def get(session, notice: str = ""):
    email, denied = _require(session, "portal")
    if denied:
        return denied
    lang = get_lang(session)
    with using_lang(lang):
        return page("portal", CLINIC_ENV, email, _thread(session),
                    portal_views.portal_view(email, notice), lang=lang)


@rt("/portal/book")
def post(session, clinician_id: int = 1, start_at: str = "", reason: str = ""):
    email, denied = _require(session, "portal")
    if denied:
        return denied
    sid = access.profile(email).get("subject_id")
    if not sid or not start_at:
        return RedirectResponse("/portal?notice=Unable+to+book", status_code=303)
    try:
        appt.book(sid, clinician_id, start_at, reason=reason)
        notice = "Appointment booked"
    except Exception as exc:
        notice = str(exc)
    return RedirectResponse(f"/portal?notice={notice}", status_code=303)


@rt("/portal/intake")
def post(session, allergies: str = "", medications: str = "", reason: str = ""):
    email, denied = _require(session, "portal")
    if denied:
        return denied
    sid = access.profile(email).get("subject_id")
    if not sid:
        return RedirectResponse("/portal?notice=Account+is+not+linked", status_code=303)
    clinical.save_intake(
        sid,
        {"allergies": allergies, "medications": medications, "reason": reason},
        actor=email,
    )
    return RedirectResponse("/portal?notice=Intake+submitted", status_code=303)


@rt("/settings/roles")
def get(session, notice: str = ""):
    return _guarded("settings-roles", lambda: clinical_views.staff_view(notice))(session)


@rt("/settings/roles")
def post(session, email: str = "", role: str = "patient",
         subject_id: int = 0, clinician_id: int = 0):
    actor, denied = _require(session, "settings-roles")
    if denied:
        return denied
    try:
        access.set_profile(
            email, role,
            subject_id=subject_id or None,
            clinician_id=clinician_id or None,
        )
        access.audit(actor, "assign", "access_profile", email)
        notice = "Role saved"
    except ValueError as exc:
        notice = str(exc)
    return RedirectResponse(f"/settings/roles?notice={notice}", status_code=303)


@rt("/admin/staff")
def get(session):
    _, denied = _require(session, "settings-roles")
    return denied or RedirectResponse("/settings/roles", status_code=303)


@rt("/settings/medbackend")
def get(session, notice: str = ""):
    email, denied = _require(session, "settings-medbackend")
    if denied:
        return denied
    lang = get_lang(session)
    with using_lang(lang):
        return page(
            "settings-medbackend", CLINIC_ENV, email, _thread(session),
            clinical_views.medbackend_oauth_view(email, notice), lang=lang,
        )


@rt("/integrations/medbackend/patient/start")
def get(session):
    email, denied = _require(session, "settings-medbackend")
    if denied:
        return denied
    try:
        return RedirectResponse(medbackend_oauth.begin(email), status_code=303)
    except medbackend_oauth.MedBackendOAuthError as exc:
        return RedirectResponse(
            f"/settings/medbackend?notice={quote_plus(str(exc))}", status_code=303,
        )


@rt("/integrations/medbackend/patient/callback")
def get(session, code: str = "", state: str = "", error: str = ""):
    email, denied = _require(session, "settings-medbackend")
    if denied:
        return denied
    if error or not code or not state:
        notice = "MedBackend authorization was cancelled or incomplete"
    else:
        try:
            result = medbackend_oauth.complete(code, state, email)
            notice = f"Connected; {result['patient_count']} patient record(s) visible"
            access.audit(email, "connect", "medbackend_patient_oauth")
        except medbackend_oauth.MedBackendOAuthError as exc:
            notice = str(exc)
    return RedirectResponse(
        f"/settings/medbackend?notice={quote_plus(notice)}", status_code=303,
    )


@rt("/admin/audit")
def get(session):
    return _guarded("audit", clinical_views.audit_view)(session)


@rt("/treatments")
def get(session):
    return _guarded("treatments", dash.treatments_view)(session)


@rt("/clinical")
def get(session):
    return _guarded("clinical", dash.clinical_view)(session)


@rt("/revenue")
def get(session):
    return _guarded("revenue", dash.revenue_view)(session)


# --- activation engines ---
@rt("/activation/reminders")
def get(session, cat: str = "all"):
    return _guarded("act-reminders", lambda: act.reminders_view(cat))(session)


@rt("/activation/lapsed")
def get(session, months: int = 12):
    return _guarded("act-lapsed", lambda: act.lapsed_view(months))(session)


@rt("/activation/followup")
def get(session, days: int = 14):
    return _guarded("act-followup", lambda: act.followup_view(days))(session)


@rt("/billing")
def get(session):
    return _guarded("billing", billing_views.view)(session)


@rt("/billing/invoice")
def post(session, consultation_id: int = 0):
    _, denied = _require(session, "billing")
    if denied:
        return ""
    if consultation_id:
        billing.raise_invoice(consultation_id)
    return _localized(session, billing_views.body)


@rt("/billing/{invoice_id}/pay")
def post(session, invoice_id: int, amount: float = 0.0):
    _, denied = _require(session, "billing")
    if denied:
        return ""
    inv = billing.query("SELECT total, paid FROM invoice WHERE id=?", (invoice_id,))
    pay = amount if amount > 0 else (inv[0]["total"] - inv[0]["paid"] if inv else 0)
    if pay > 0:
        billing.record_payment(invoice_id, pay)
    return _localized(session, billing_views.body)


@rt("/activation/loop")
def get(session):
    return _guarded("act-loop", act.loop_view)(session)


@rt("/activation/reminders/enqueue")
def post(session):
    _, denied = _require(session, "act-loop")
    if denied:
        return ""
    n = aloop.enqueue_due_reminders()
    logger.info("Enqueued %s reminders", n)
    return _localized(session, act._loop_body)


@rt("/appointments")
def get(session, clinician_id: int = 0, day: str = ""):
    return _guarded("appointments",
                    lambda: appt_views.view(clinician_id or None, day or None))(session)


@rt("/appointments/book")
def post(session, subject_id: int = 0, clinician_id: int = 0, start_at: str = "",
         reason: str = "", day: str = ""):
    _, denied = _require(session, "appointments")
    if denied:
        return ""
    day = day or (start_at[:10] if start_at else act.reference_date()[:10])
    if subject_id and clinician_id and start_at:
        try:
            appt.book(subject_id, clinician_id, start_at, reason=reason.strip())
        except appt.SlotTaken as e:
            logger.warning("Booking refused: %s", e)
    return _localized(session, lambda: appt_views.body(clinician_id or 1, day))


@rt("/appointments/{appt_id}/status")
def post(session, appt_id: int, to: str = "", clinician_id: int = 0, day: str = ""):
    _, denied = _require(session, "appointments")
    if denied:
        return ""
    row = appt.get(appt_id)
    if to:
        try:
            appt.set_status(appt_id, to)
        except ValueError:
            pass
    cid = clinician_id or (row["clinician_id"] if row else 1)
    d = day or (row["start_at"][:10] if row and row.get("start_at") else act.reference_date()[:10])
    return _localized(session, lambda: appt_views.body(cid, d))


@rt("/activation/{engine}/csv")
def get(session, engine: str, cat: str = "all", months: int = 12, days: int = 14):
    _, denied = _require(session, f"act-{engine}")
    if denied:
        return denied
    with using_lang(get_lang(session)):
        body, fname = act.campaign_csv(engine, cat=cat, months=months, days=days)
    if body is None:
        return Response("Unknown engine", status_code=404, media_type="text/plain")
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@rt("/activation/{engine}/xlsx")
def get(session, engine: str, cat: str = "all", months: int = 12, days: int = 14):
    _, denied = _require(session, f"act-{engine}")
    if denied:
        return denied
    with using_lang(get_lang(session)):
        body, fname = act.campaign_xlsx(engine, cat=cat, months=months, days=days)
    if body is None:
        return Response("Unknown engine", status_code=404, media_type="text/plain")
    from web.exports import XLSX_MIME
    return Response(body, media_type=XLSX_MIME,
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# --- marketing: SMS ---
@rt("/ops/sms")
def get(session):
    return _guarded("sms", dash.sms_broadcaster_view)(session)


@rt("/api/sms/send")
def post(session, provider: str = "", phone: str = "", message: str = ""):
    _, denied = _require(session, "sms")
    if denied:
        return ""
    phone, message = phone.strip(), message.strip()
    if not phone or not message:
        return _localized(session, lambda: dash.sms_send_result(
            False, provider or "—", error=t("Phone number and message are required.")))
    if not provider:
        return _localized(session, lambda: dash.sms_send_result(
            False, "—", error=t("No SMS provider selected.")))
    party_id, subject_id = aloop.resolve_by_phone(phone)
    blocked = consent.check_phone(phone)
    if blocked:
        aloop.log_communication(channel="sms", to_addr=phone, body=message,
                                status="blocked", party_id=party_id,
                                subject_id=subject_id, provider=provider,
                                error="opted_out")
        logger.warning("SMS send BLOCKED — recipient opted out: to=%s", phone)
        return _localized(session, lambda: dash.sms_send_result(False, provider, error=blocked))
    from util.sms import send
    result = send(phone, message, provider)
    aloop.log_communication(channel="sms", to_addr=phone, body=message,
                            status="sent" if result.ok else "failed",
                            party_id=party_id, subject_id=subject_id,
                            provider=result.provider,
                            provider_message_id=result.message_id or "",
                            error=result.error or "")
    logger.info("SMS send: provider=%s to=%s ok=%s", provider, phone, result.ok)
    return _localized(session, lambda: dash.sms_send_result(
        result.ok, result.provider, result.message_id, result.error))


@rt("/ops/email")
def get(session):
    return _guarded("email", dash.email_broadcaster_view)(session)


@rt("/api/email/send")
def post(session, to: str = "", subject: str = "", body: str = ""):
    _, denied = _require(session, "email")
    if denied:
        return ""
    to, subject, body = to.strip(), subject.strip(), body.strip()
    if not to or not subject or not body:
        return _localized(session, lambda: dash.email_send_result(
            False, error=t("Recipient, subject, and message are required.")))
    party_id, subject_id = aloop.resolve_by_email(to)
    blocked = consent.check_email(to)
    if blocked:
        aloop.log_communication(channel="email", to_addr=to, body=body,
                                status="blocked", party_id=party_id,
                                subject_id=subject_id, error="opted_out")
        logger.warning("Email send BLOCKED — recipient opted out: to=%s", to)
        return _localized(session, lambda: dash.email_send_result(False, error=blocked))
    from util.email import send as send_email
    result = send_email(to, subject, body)
    aloop.log_communication(channel="email", to_addr=to, body=body,
                            status="sent" if result.ok else "failed",
                            party_id=party_id, subject_id=subject_id,
                            provider="postmark",
                            provider_message_id=result.message_id or "",
                            error=result.error or "")
    logger.info("Email send: to=%s ok=%s", to, result.ok)
    return _localized(session, lambda: dash.email_send_result(
        result.ok, result.message_id, result.error))


# --- help ---
@rt("/help/shortcuts")
def get(session):
    return _guarded("help-shortcuts", help_views.shortcuts_view)(session)


@rt("/help/guide")
def get(session):
    return _guarded("help-guide", help_views.user_guide_view)(session)


# Guide images + PDF are served by FastHTML's static handler from docs/.

# --- admin ---
@rt("/admin/data")
def get(session):
    return _guarded("data-admin", dash.data_admin_view)(session)


@rt("/admin/fhir")
def get(session, subject_id: int = 0, nhs_number: str = "", release: str = "r4"):
    email, denied = _require(session, "fhir-admin")
    if denied:
        return denied
    lang = get_lang(session)
    with using_lang(lang):
        return page(
            "fhir-admin", CLINIC_ENV, email, _thread(session),
            fhir_views.fhir_admin_view(
                subject_id=subject_id or None,
                nhs_number=nhs_number,
                release=release or "r4",
            ),
            lang=lang,
        )


# --- AI assistant ---
@rt("/ai")
def get(session):
    email, denied = _require(session, "chat-full")
    if denied:
        return denied
    tid = _thread(session)
    lang = get_lang(session)
    with using_lang(lang):
        return page("chat-full", CLINIC_ENV, email, tid,
                    dash.ai_full_view(tid), right_override=right_pane_reference(), lang=lang)


@rt("/ai/prompt")
def get(session):
    return _guarded("prompt", dash.prompt_view)(session)


# --- SEO audit ---
SEO_SITE = os.getenv("FASTCLINIC_SEO_SITE", "https://fastclinic.dev")


@rt("/seo")
def get(session):
    return _guarded("seo", seo_views.index_view)(session)


@rt("/seo/run-all")
def post(session, site_url: str = SEO_SITE):
    _, denied = _require(session, "seo")
    if denied:
        return denied
    logger.info(f"Running full SEO audit suite for {site_url}")
    content = seo.fetch_site_context(site_url)
    for comp in seo.load_config():
        try:
            seo.run_component(comp["slug"], site_url, content)
        except Exception:
            logger.exception(f"  {comp['slug']} crashed")
    return RedirectResponse("/seo", status_code=303)


@rt("/seo/{slug}")
def get(session, slug: str):
    email, denied = _require(session, "seo")
    if denied:
        return denied
    if not seo.component(slug):
        return RedirectResponse("/seo", status_code=303)
    lang = get_lang(session)
    with using_lang(lang):
        return page(slug, CLINIC_ENV, email, _thread(session),
                    seo_views.component_view(slug), lang=lang)


@rt("/seo/{slug}/prompt")
def get(session, slug: str):
    email, denied = _require(session, "seo")
    if denied:
        return denied
    if not seo.component(slug):
        return RedirectResponse("/seo", status_code=303)
    lang = get_lang(session)
    with using_lang(lang):
        return page(slug, CLINIC_ENV, email, _thread(session),
                    seo_views.prompt_editor_view(slug), lang=lang)


@rt("/seo/{slug}/prompt")
def post(session, slug: str, prompt: str = ""):
    email, denied = _require(session, "seo")
    if denied:
        return denied
    if not seo.component(slug):
        return RedirectResponse("/seo", status_code=303)
    seo.write_prompt(slug, prompt)
    lang = get_lang(session)
    with using_lang(lang):
        return page(slug, CLINIC_ENV, email, _thread(session),
                    seo_views.prompt_editor_view(slug, saved=True), lang=lang)


@rt("/seo/{slug}/run-confirm")
def get(session, slug: str, site_url: str | None = None):
    email, denied = _require(session, "seo")
    if denied:
        return denied
    lang = get_lang(session)
    with using_lang(lang):
        return page(slug, CLINIC_ENV, email, _thread(session),
                    seo_views.run_confirm_view(slug, site_url or SEO_SITE), lang=lang)


@rt("/seo/{slug}/run")
def post(session, slug: str, site_url: str = SEO_SITE):
    _, denied = _require(session, "seo")
    if denied:
        return denied
    if not seo.component(slug):
        return RedirectResponse("/seo", status_code=303)
    logger.info(f"Running SEO audit {slug} for {site_url}")
    content = seo.fetch_site_context(site_url)
    seo.run_component(slug, site_url, content)
    return RedirectResponse(f"/seo/{slug}", status_code=303)


@rt("/seo/{slug}/csv")
def get(session, slug: str):
    _, denied = _require(session, "seo")
    if denied:
        return denied
    p = seo.latest_csv_path(slug)
    if not p:
        return "no data", 404
    from starlette.responses import FileResponse
    return FileResponse(str(p), media_type="text/csv", filename=p.name)


@rt("/seo/{slug}/xlsx")
def get(session, slug: str):
    _, denied = _require(session, "seo")
    if denied:
        return denied
    header, rows = seo.load_csv(slug)
    if not header:
        return Response("no data", status_code=404, media_type="text/plain")
    from web.exports import build_xlsx, XLSX_MIME
    body = build_xlsx(header, rows, sheet_name=slug[:31])
    return Response(body, media_type=XLSX_MIME,
                    headers={"Content-Disposition": f'attachment; filename="fastclinic_seo_{slug}.xlsx"'})


# --- chat ---
@rt("/chat/new")
def get(session):
    email, denied = _require(session, "chat-full")
    if denied:
        return denied
    session["thread_id"] = f"fastclinic_{uuid.uuid4().hex[:12]}"
    return _localized(session, lambda: Div(
        Div(NotStr("New conversation started. Ask the AI anything or type <code>/help</code>."),
            cls="msg system"),
        id="chat-body", cls="chat-body", hx_swap_oob="outerHTML",
    ))


@rt("/chat/stream")
async def post(session, message: str = "", thread_id: str = ""):
    """SSE streaming chat: slash-commands answer instantly; free-form streams the
    LangGraph agent token-by-token with a tool trace."""
    _, denied = _require(session, "chat-full")
    if denied:
        return Response("unauthorized", status_code=401)
    from web.sse import sse
    msg = (message or "").strip()
    lang = get_lang(session)
    tid = _thread(session)
    owner_id = _auth(session)

    async def gen():
        if not msg:
            yield sse("done", {})
            return
        with using_lang(lang):
            kind, payload = cmd.dispatch(msg)
        if kind == "local":
            from web.chat_history import append_turn
            await asyncio.to_thread(append_turn, owner_id, tid, msg, payload, lang)
            yield sse("token", {"text": payload})
            yield sse("done", {"local": True})
            return
        from graph.clinic_assistant import answer_stream
        prompt = payload if payload is not None else msg
        got = False
        try:
            async for ev, data in answer_stream(
                prompt, thread_id=tid, lang=lang, owner_id=owner_id,
            ):
                if ev == "token":
                    got = True
                    yield sse("token", {"text": data})
                elif ev == "tool_start":
                    yield sse("tool_start", data)
                elif ev == "tool_end":
                    yield sse("tool_end", data)
                elif ev == "error":
                    yield sse("error", {"message": data})
        except Exception as e:  # noqa: BLE001
            logger.exception("chat stream failed")
            yield sse("error", {"message": str(e)})
        if not got:
            yield sse("token", {"text": t("*(no response)*", lang)})
        yield sse("done", {})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@rt("/chat/send")
def post(session, message: str = "", thread_id: str = ""):
    _, denied = _require(session, "chat-full")
    if denied:
        return _localized(session, lambda: Div("Unauthorized", cls="msg system"))
    # The session owns the thread. Never let a forged hidden-field value attach
    # one signed-in user to another user's persisted clinical conversation.
    tid = _thread(session)
    msg = (message or "").strip()
    if not msg:
        return ""

    user_bubble = Div(msg, cls="msg user")
    lang = get_lang(session)
    with using_lang(lang):
        kind, payload = cmd.dispatch(msg)

    if kind == "local":
        from web.chat_history import append_turn
        append_turn(_auth(session), tid, msg, payload, lang)
        bubble_id = f"a-{uuid.uuid4().hex[:8]}"
        return (
            user_bubble,
            Div(
                NotStr(f"<div id='{bubble_id}-md' class='md'></div>"),
                Script(NotStr(
                    f"document.getElementById('{bubble_id}-md').innerHTML = "
                    f"marked.parse({_js_str(payload)});"
                )),
                cls="msg assistant",
            ),
        )

    agent_prompt = payload if payload is not None else msg
    try:
        from graph.clinic_assistant import answer
        content = answer(
            agent_prompt, thread_id=tid, lang=lang, owner_id=_auth(session),
        ) or t("*(no response)*", lang)
    except Exception as e:
        logger.exception("Assistant failed")
        content = f"⚠ assistant error: `{e}`"

    bubble_id = f"a-{uuid.uuid4().hex[:8]}"
    return (
        user_bubble,
        Div(
            NotStr(f"<div id='{bubble_id}-md' class='md'></div>"),
            Script(NotStr(
                f"document.getElementById('{bubble_id}-md').innerHTML = "
                f"marked.parse({_js_str(content)});"
            )),
            cls="msg assistant",
        ),
    )


def _js_str(s: str) -> str:
    import json
    return json.dumps(s)


def _ensure_db():
    """Build fastclinic.sqlite from the newest export in SQLite mode.

    Lets the container come up with data even when the DB isn't committed.
    """
    from web.db import db_exists, DB_PATH, is_postgres
    if db_exists():
        return
    if is_postgres():
        raise RuntimeError(
            "PostgreSQL clinical schema is missing; run "
            "scripts/migrate_clinical_to_postgres.py before startup"
        )
    try:
        from pms.importer import build, _default_export
        # Prefer the shipped synthetic demo export; fall back to any data/*.xlsx.
        synth = os.path.join(os.path.dirname(__file__), "data", "synthetic_fastclinic.xlsx")
        export = synth if os.path.exists(synth) else _default_export()
        logger.info(f"No database found — importing {export} -> {DB_PATH}")
        build(export, DB_PATH)
        logger.info("Database built.")
    except SystemExit as e:
        logger.warning(f"Could not auto-build database: {e}")
    except Exception:
        logger.exception("Auto-build of database failed")


# --- boot ---

register_seo_routes(app)

if __name__ == "__main__":
    _ensure_db()
    logger.info(f"Starting FastClinic Cockpit on :{PORT}")
    serve(host="0.0.0.0", port=PORT, reload=False)
