"""FastClinic Cockpit — human GP / general-practice clinic business cockpit.

FastHTML dashboards + customer-activation engines + AI chat, branded for FastClinic.

Run:
    python web_app.py            # http://localhost:5005

Login: admin@fastclinic.example / FastClinic2026$  (override via env, see .env.sample)
"""
from __future__ import annotations

import os
import secrets
import uuid
import logging

from dotenv import load_dotenv
load_dotenv()

from fasthtml.common import (
    fast_app, serve, Div, H1, P, A, Form, Input, Button,
    Titled, NotStr, RedirectResponse, Script, Style, Link, Title,
)
from starlette.responses import Response, StreamingResponse

from web.layout import page, right_pane_reference, LAYOUT_CSS
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

logger = logging.getLogger("fastclinic")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

# --- config ---
VALID_EMAIL = os.getenv("FASTCLINIC_ADMIN_EMAIL", os.getenv("MMG_ADMIN_EMAIL", "admin@fastclinic.example"))
VALID_PASSWORD = os.getenv("FASTCLINIC_ADMIN_PASSWORD", os.getenv("MMG_ADMIN_PASSWORD", "FastClinic2026$"))
CLINIC_ENV = os.getenv("FASTCLINIC_ENV_LABEL", "FastClinic")
SECRET = os.getenv("FASTCLINIC_SECRET", os.getenv("MMG_COCKPIT_SECRET", secrets.token_hex(32)))
PORT = int(os.getenv("FASTCLINIC_PORT", os.getenv("MMG_COCKPIT_PORT", "5005")))

# FastClinic favicon — clinical blue mark (repo-root favicon.svg / favicon.ico,
# served by FastHTML's static handler).
FAVICON_HREF = "/favicon.svg"

app, rt = fast_app(
    live=False,
    pico=False,
    secret_key=SECRET,
    hdrs=[Style(LAYOUT_CSS)],
)


# --- helpers ---
def _auth(session) -> str | None:
    return session.get("user_email")


def _thread(session) -> str:
    tid = session.get("thread_id")
    if not tid:
        tid = f"fastclinic_{uuid.uuid4().hex[:12]}"
        session["thread_id"] = tid
    return tid


def _guarded(active: str, builder):
    def handler(session):
        email = _auth(session)
        if not email:
            return RedirectResponse("/login", status_code=303)
        return page(active, CLINIC_ENV, email, _thread(session), builder())
    return handler


def _login_card(error: str = "", email: str = ""):
    return (
        Title("FastClinic Cockpit"),
        Link(rel="icon", type="image/svg+xml", href=FAVICON_HREF),
        Style(LAYOUT_CSS),
        Div(
            Div(
                H1(NotStr("<span style='color:#1e6fb8'>FastClinic</span>")),
                P("GP clinic activation cockpit. Sign in to continue."),
                Div(error, cls="error") if error else None,
                Form(
                    Input(type="email", name="email", value=email, placeholder="admin@fastclinic.example", required=True),
                    Input(type="password", name="password", placeholder="Password", required=True),
                    Button("Sign in", cls="btn primary", type="submit"),
                    method="post", action="/login",
                ),
                cls="login-card",
            ),
            cls="login-wrap",
        ),
    )


# --- auth ---
@rt("/login")
def get(session):
    if _auth(session):
        return RedirectResponse("/", status_code=303)
    return _login_card()


@rt("/login")
def post(session, email: str = "", password: str = ""):
    if email.strip() == VALID_EMAIL and password == VALID_PASSWORD:
        session["user_email"] = email.strip()
        return RedirectResponse("/", status_code=303)
    return _login_card(error="Invalid credentials", email=email)


@rt("/logout")
def get(session):
    session.pop("user_email", None)
    session.pop("thread_id", None)
    return RedirectResponse("/login", status_code=303)


# Favicon (favicon.svg + favicon.ico) is served from the app root by FastHTML's
# static handler; the FastClinic mark lives at repo root and web/static/.


# --- overview ---
@rt("/")
def get(session):
    return _guarded("dashboard", dash.overview_view)(session)


# --- clinic ---
@rt("/patients")
def get(session, q: str = ""):
    return _guarded("patients", lambda: dash.patients_view(q))(session)


@rt("/patients/{pid}")
def get(session, pid: int):
    if not _auth(session):
        return RedirectResponse("/login", status_code=303)
    return page("patients", CLINIC_ENV, _auth(session), _thread(session),
                dash.patient_detail_view(pid))


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
    if not _auth(session):
        return ""
    if consultation_id:
        billing.raise_invoice(consultation_id)
    return billing_views.body()


@rt("/billing/{invoice_id}/pay")
def post(session, invoice_id: int, amount: float = 0.0):
    if not _auth(session):
        return ""
    inv = billing.query("SELECT total, paid FROM invoice WHERE id=?", (invoice_id,))
    pay = amount if amount > 0 else (inv[0]["total"] - inv[0]["paid"] if inv else 0)
    if pay > 0:
        billing.record_payment(invoice_id, pay)
    return billing_views.body()


@rt("/activation/loop")
def get(session):
    return _guarded("act-loop", act.loop_view)(session)


@rt("/activation/reminders/enqueue")
def post(session):
    if not _auth(session):
        return ""
    n = aloop.enqueue_due_reminders()
    logger.info("Enqueued %s reminders", n)
    return act._loop_body()


@rt("/appointments")
def get(session, clinician_id: int = 0, day: str = ""):
    return _guarded("appointments",
                    lambda: appt_views.view(clinician_id or None, day or None))(session)


@rt("/appointments/book")
def post(session, subject_id: int = 0, clinician_id: int = 0, start_at: str = "",
         reason: str = "", day: str = ""):
    if not _auth(session):
        return ""
    day = day or (start_at[:10] if start_at else act.reference_date()[:10])
    if subject_id and clinician_id and start_at:
        try:
            appt.book(subject_id, clinician_id, start_at, reason=reason.strip())
        except appt.SlotTaken as e:
            logger.warning("Booking refused: %s", e)
    return appt_views.body(clinician_id or 1, day)


@rt("/appointments/{appt_id}/status")
def post(session, appt_id: int, to: str = "", clinician_id: int = 0, day: str = ""):
    if not _auth(session):
        return ""
    row = appt.get(appt_id)
    if to:
        try:
            appt.set_status(appt_id, to)
        except ValueError:
            pass
    cid = clinician_id or (row["clinician_id"] if row else 1)
    d = day or (row["start_at"][:10] if row and row.get("start_at") else act.reference_date()[:10])
    return appt_views.body(cid, d)


@rt("/activation/{engine}/csv")
def get(session, engine: str, cat: str = "all", months: int = 12, days: int = 14):
    if not _auth(session):
        return RedirectResponse("/login", status_code=303)
    body, fname = act.campaign_csv(engine, cat=cat, months=months, days=days)
    if body is None:
        return Response("Unknown engine", status_code=404, media_type="text/plain")
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@rt("/activation/{engine}/xlsx")
def get(session, engine: str, cat: str = "all", months: int = 12, days: int = 14):
    if not _auth(session):
        return RedirectResponse("/login", status_code=303)
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
    if not _auth(session):
        return ""
    phone, message = phone.strip(), message.strip()
    if not phone or not message:
        return dash.sms_send_result(False, provider or "—", error="Phone number and message are required.")
    if not provider:
        return dash.sms_send_result(False, "—", error="No SMS provider selected.")
    party_id, subject_id = aloop.resolve_by_phone(phone)
    blocked = consent.check_phone(phone)
    if blocked:
        aloop.log_communication(channel="sms", to_addr=phone, body=message,
                                status="blocked", party_id=party_id,
                                subject_id=subject_id, provider=provider,
                                error="opted_out")
        logger.warning("SMS send BLOCKED — recipient opted out: to=%s", phone)
        return dash.sms_send_result(False, provider, error=blocked)
    from util.sms import send
    result = send(phone, message, provider)
    aloop.log_communication(channel="sms", to_addr=phone, body=message,
                            status="sent" if result.ok else "failed",
                            party_id=party_id, subject_id=subject_id,
                            provider=result.provider,
                            provider_message_id=result.message_id or "",
                            error=result.error or "")
    logger.info("SMS send: provider=%s to=%s ok=%s", provider, phone, result.ok)
    return dash.sms_send_result(result.ok, result.provider, result.message_id, result.error)


@rt("/ops/email")
def get(session):
    return _guarded("email", dash.email_broadcaster_view)(session)


@rt("/api/email/send")
def post(session, to: str = "", subject: str = "", body: str = ""):
    if not _auth(session):
        return ""
    to, subject, body = to.strip(), subject.strip(), body.strip()
    if not to or not subject or not body:
        return dash.email_send_result(False, error="Recipient, subject, and message are required.")
    party_id, subject_id = aloop.resolve_by_email(to)
    blocked = consent.check_email(to)
    if blocked:
        aloop.log_communication(channel="email", to_addr=to, body=body,
                                status="blocked", party_id=party_id,
                                subject_id=subject_id, error="opted_out")
        logger.warning("Email send BLOCKED — recipient opted out: to=%s", to)
        return dash.email_send_result(False, error=blocked)
    from util.email import send as send_email
    result = send_email(to, subject, body)
    aloop.log_communication(channel="email", to_addr=to, body=body,
                            status="sent" if result.ok else "failed",
                            party_id=party_id, subject_id=subject_id,
                            provider="postmark",
                            provider_message_id=result.message_id or "",
                            error=result.error or "")
    logger.info("Email send: to=%s ok=%s", to, result.ok)
    return dash.email_send_result(result.ok, result.message_id, result.error)


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


# --- AI assistant ---
@rt("/ai")
def get(session):
    email = _auth(session)
    if not email:
        return RedirectResponse("/login", status_code=303)
    tid = _thread(session)
    return page("chat-full", CLINIC_ENV, email, tid,
                dash.ai_full_view(tid), right_override=right_pane_reference())


@rt("/ai/prompt")
def get(session):
    return _guarded("prompt", dash.prompt_view)(session)


# --- SEO audit (retargeted to fastclinic.example) ---
SEO_SITE = os.getenv("FASTCLINIC_SEO_SITE", "https://fastclinic.example")


@rt("/seo")
def get(session):
    return _guarded("seo", seo_views.index_view)(session)


@rt("/seo/run-all")
def post(session, site_url: str = SEO_SITE):
    if not _auth(session):
        return RedirectResponse("/login", status_code=303)
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
    if not _auth(session):
        return RedirectResponse("/login", status_code=303)
    if not seo.component(slug):
        return RedirectResponse("/seo", status_code=303)
    return page(slug, CLINIC_ENV, _auth(session), _thread(session), seo_views.component_view(slug))


@rt("/seo/{slug}/prompt")
def get(session, slug: str):
    if not _auth(session):
        return RedirectResponse("/login", status_code=303)
    if not seo.component(slug):
        return RedirectResponse("/seo", status_code=303)
    return page(slug, CLINIC_ENV, _auth(session), _thread(session), seo_views.prompt_editor_view(slug))


@rt("/seo/{slug}/prompt")
def post(session, slug: str, prompt: str = ""):
    if not _auth(session):
        return RedirectResponse("/login", status_code=303)
    if not seo.component(slug):
        return RedirectResponse("/seo", status_code=303)
    seo.write_prompt(slug, prompt)
    return page(slug, CLINIC_ENV, _auth(session), _thread(session), seo_views.prompt_editor_view(slug, saved=True))


@rt("/seo/{slug}/run-confirm")
def get(session, slug: str, site_url: str | None = None):
    if not _auth(session):
        return RedirectResponse("/login", status_code=303)
    return page(slug, CLINIC_ENV, _auth(session), _thread(session),
                seo_views.run_confirm_view(slug, site_url or SEO_SITE))


@rt("/seo/{slug}/run")
def post(session, slug: str, site_url: str = SEO_SITE):
    if not _auth(session):
        return RedirectResponse("/login", status_code=303)
    if not seo.component(slug):
        return RedirectResponse("/seo", status_code=303)
    logger.info(f"Running SEO audit {slug} for {site_url}")
    content = seo.fetch_site_context(site_url)
    seo.run_component(slug, site_url, content)
    return RedirectResponse(f"/seo/{slug}", status_code=303)


@rt("/seo/{slug}/csv")
def get(session, slug: str):
    if not _auth(session):
        return RedirectResponse("/login", status_code=303)
    p = seo.latest_csv_path(slug)
    if not p:
        return "no data", 404
    from starlette.responses import FileResponse
    return FileResponse(str(p), media_type="text/csv", filename=p.name)


@rt("/seo/{slug}/xlsx")
def get(session, slug: str):
    if not _auth(session):
        return RedirectResponse("/login", status_code=303)
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
    session["thread_id"] = f"fastclinic_{uuid.uuid4().hex[:12]}"
    return Div(
        Div(NotStr("New conversation started. Ask the AI anything or type <code>/help</code>."),
            cls="msg system"),
        id="chat-body", cls="chat-body", hx_swap_oob="outerHTML",
    )


@rt("/chat/stream")
async def post(session, message: str = "", thread_id: str = ""):
    """SSE streaming chat: slash-commands answer instantly; free-form streams the
    LangGraph agent token-by-token with a tool trace."""
    if not _auth(session):
        return Response("unauthorized", status_code=401)
    from web.sse import sse
    msg = (message or "").strip()

    async def gen():
        if not msg:
            yield sse("done", {})
            return
        kind, payload = cmd.dispatch(msg)
        if kind == "local":
            yield sse("token", {"text": payload})
            yield sse("done", {"local": True})
            return
        from graph.clinic_assistant import answer_stream
        prompt = payload if payload is not None else msg
        got = False
        try:
            async for ev, data in answer_stream(prompt):
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
            yield sse("token", {"text": "*(no response)*"})
        yield sse("done", {})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@rt("/chat/send")
def post(session, message: str = "", thread_id: str = ""):
    if not _auth(session):
        return Div("Unauthorized", cls="msg system")
    tid = thread_id or _thread(session)
    msg = (message or "").strip()
    if not msg:
        return ""

    user_bubble = Div(msg, cls="msg user")
    kind, payload = cmd.dispatch(msg)

    if kind == "local":
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
        content = answer(agent_prompt) or "*(no response)*"
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
    """Build fastclinic.sqlite from the newest data/ export if it's missing.

    Lets the container come up with data even when the DB isn't committed.
    """
    from web.db import db_exists, DB_PATH
    if db_exists():
        return
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
if __name__ == "__main__":
    _ensure_db()
    logger.info(f"Starting FastClinic Cockpit on :{PORT}")
    serve(host="0.0.0.0", port=PORT, reload=False)
