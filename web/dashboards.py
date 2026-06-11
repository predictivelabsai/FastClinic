"""Dashboard views for the FastClinic cockpit — server-rendered FastHTML.

Charts use Plotly (the existing charting layer); everything else is plain
FastHTML components rendered on the server.
"""
from __future__ import annotations

import json
from datetime import date
from fasthtml.common import (
    Div, H1, H3, P, Span, A, Button, Table, Thead, Tbody, Tr, Th, Td, NotStr,
    Select, Option, Label, Form, Input,
)

from web import clinic_queries as q
from web.layout import kpi_card, plot_div
from pms.catalog import gender_label

ACCENT = "#1e6fb8"
ACCENT2 = "#1b2733"
WARN = "#1f9d72"


def _plot_spec(data, layout) -> str:
    return json.dumps({"data": data, "layout": layout})


def _base_layout(title=None, height=280):
    return {
        "margin": {"l": 44, "r": 12, "t": 30 if title else 10, "b": 40},
        "height": height,
        "paper_bgcolor": "white",
        "plot_bgcolor": "white",
        "font": {"family": "ui-sans-serif, system-ui, sans-serif", "size": 12, "color": "#1b2733"},
        "title": {"text": title, "font": {"size": 14}} if title else None,
        # automargin grows the plot margins to fit tick labels — without it the
        # category labels on horizontal bar charts get clipped.
        "xaxis": {"gridcolor": "#dbe6e6", "automargin": True},
        "yaxis": {"gridcolor": "#dbe6e6", "automargin": True},
    }


def _escape(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _eur(v) -> str:
    try:
        return f"€{float(v):,.0f}"
    except (ValueError, TypeError):
        return "—"


def _date(s) -> str:
    return (s or "")[:10] or "—"


def _age(dob) -> str:
    s = (dob or "")[:10]
    try:
        y, m, d = int(s[:4]), int(s[5:7]), int(s[8:10])
        born = date(y, m, d)
        today = date.today()
        years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        return str(years) if years >= 0 else "—"
    except (ValueError, TypeError):
        return "—"


def _page_title(title: str, sub: str = "", actions=None):
    return Div(
        Div(H1(title), Div(sub, cls="sub") if sub else None),
        actions if actions is not None else None,
        cls="page-title",
    )


def _table(headers, rows):
    """rows: list of lists of cell content (str or FT component)."""
    return Table(
        Thead(Tr(*[Th(h) for h in headers])),
        Tbody(*[Tr(*[Td(c) for c in r]) for r in rows]),
        cls="tbl",
    )


# ---------- Overview ----------
def overview_view():
    from web.db import db_exists
    if not db_exists():
        return _no_data_view()
    k = q.overview_kpis()
    cards = Div(
        kpi_card("Active patients (90d)", k["active_90"]),
        kpi_card("Total patients", k["total_patients"], neutral=True),
        kpi_card("Visits (30d)", k["visits_30"]),
        kpi_card("Revenue (90d)", _eur(k["rev_90"])),
        kpi_card("Lifetime revenue", _eur(k["rev_total"]), neutral=True),
        kpi_card("Clients", k["clients"], neutral=True),
        cls="kpi-grid", style="grid-template-columns:repeat(3,1fr);",
    )

    trend = q.monthly_trend()
    months = [r["month"] for r in trend]
    visits_chart = plot_div("ov-visits", _plot_spec(
        [{"type": "bar", "x": months, "y": [r["visits"] for r in trend],
          "marker": {"color": ACCENT}}],
        _base_layout("Visits per month"),
    ))
    rev_chart = plot_div("ov-rev", _plot_spec(
        [{"type": "scatter", "mode": "lines+markers", "x": months,
          "y": [r["revenue"] for r in trend], "line": {"color": WARN, "width": 3}}],
        _base_layout("Revenue per month (€, incl VAT)"),
    ))

    cat = q.revenue_by_category()
    cat_chart = plot_div("ov-cat", _plot_spec(
        [{"type": "bar", "orientation": "h",
          "y": [r["category"] for r in cat][::-1],
          "x": [r["revenue"] for r in cat][::-1],
          "marker": {"color": ACCENT2}}],
        _base_layout(height=300),
    ))

    top = q.top_services(8)
    top_rows = [[s["name"], Span(s["category"], cls=f"status-pill {s['category']}"),
                 s["times"], _eur(s["revenue"])] for s in top]

    return Div(
        _page_title("Clinic Overview", f"Activation cockpit · data through {k['reference_date']}"),
        cards,
        Div(
            Div(Div(H3("Visits"), cls="card-header"), *visits_chart, cls="card"),
            Div(Div(H3("Revenue"), cls="card-header"), *rev_chart, cls="card"),
            cls="grid-2",
        ),
        Div(
            Div(Div(H3("Revenue by category"), cls="card-header"), *cat_chart, cls="card"),
            Div(Div(H3("Top services"), cls="card-header"),
                _table(["Service", "Category", "Times", "Revenue"], top_rows), cls="card"),
            cls="grid-2",
        ),
    )


def _no_data_view():
    return Div(
        _page_title("No data loaded"),
        Div(
            Div(H3("Import a PMS export to begin"), cls="card-header"),
            P("The cockpit database (fastclinic.sqlite) was not found."),
            NotStr("<pre style='background:var(--surface-2);padding:12px;border-radius:6px;'>"
                   "python -m pms.importer</pre>"),
            P("This builds the database from the newest .xlsx export in data/.",
              style="color:var(--text-mute);font-size:13px;"),
            cls="card",
        ),
    )


# ---------- Patients ----------
def patients_view(search: str = ""):
    from web.db import db_exists
    if not db_exists():
        return _no_data_view()
    rows = q.patient_list(search)
    search_form = Form(
        Input(type="text", name="q", value=search, placeholder="Search id / name / city / NHS no…",
              style="padding:8px 12px;border:1px solid var(--border);border-radius:8px;font-size:13px;width:280px;"),
        Button("Search", cls="btn primary", type="submit"),
        method="get", action="/patients",
        style="display:flex;gap:8px;",
    )
    table_rows = []
    for p in rows:
        pid = p["id"]
        status = "—"
        if p["deceased_at"]:
            status = Span("deceased", cls="status-pill cancelled")
        table_rows.append([
            A(f"#{pid}", href=f"/patients/{pid}", style="font-weight:600;"),
            p["official_name"] or "—",
            p["city"] or "—",
            gender_label(p["gender"]),
            _age(p["date_of_birth"]),
            p["nhs_number"] or "—",
            p["visits"] or 0,
            _date(p["last_visit"]),
            _eur(p["lifetime_value"]),
            p["critical_notes"] or status,
        ])
    return Div(
        _page_title("Patients", f"{len(rows)} shown", actions=search_form),
        Div(
            _table(["Patient", "Name", "City", "Sex", "Age", "NHS no.", "Visits", "Last visit", "Lifetime €", "Notes"],
                   table_rows) if table_rows else P("No patients match."),
            cls="card",
        ),
    )


def patient_detail_view(pid: int):
    p = q.patient_detail(pid)
    if not p:
        return Div(_page_title("Patient not found"),
                   Div(P(f"No patient #{pid}."), A("← Back to patients", href="/patients"), cls="card"))
    val = q.patient_value(pid)
    cards = Div(
        kpi_card("Lifetime value", _eur(val.get("lifetime_value"))),
        kpi_card("Visits", val.get("visits") or 0, neutral=True),
        kpi_card("First seen", _date(val.get("first_seen")), neutral=True),
        kpi_card("Last seen", _date(val.get("last_seen"))),
        cls="kpi-grid",
    )

    profile = Div(
        Div(H3("Profile"), cls="card-header"),
        NotStr(
            "<table class='tbl'>"
            f"<tr><th>Patient ID</th><td>#{pid}</td></tr>"
            f"<tr><th>Client ID</th><td>{p['client_id'] or '—'}</td></tr>"
            f"<tr><th>Name</th><td>{_escape(p['official_name'] or '—')}</td></tr>"
            f"<tr><th>Sex</th><td>{gender_label(p['gender'])}</td></tr>"
            f"<tr><th>City</th><td>{_escape(p['city'] or '—')}</td></tr>"
            f"<tr><th>Date of birth</th><td>{_date(p['date_of_birth'])} (age {_age(p['date_of_birth'])})</td></tr>"
            f"<tr><th>NHS number</th><td>{_escape(p['nhs_number'] or '—')}</td></tr>"
            f"<tr><th>Critical notes</th><td>{_escape(p['critical_notes'] or '—')}</td></tr>"
            "</table>"
        ),
        cls="card",
    )

    cons = q.patient_consultations(pid)
    cons_rows = [[_date(c["consult_at"]), c["item_count"], _eur(c["revenue_vat"]),
                  _escape((c["diagnoses"] or "—")[:120])] for c in cons]
    history = Div(
        Div(H3(f"Consultation history ({len(cons)})"), cls="card-header"),
        _table(["Date", "Items", "Revenue", "Diagnoses"], cons_rows) if cons_rows else P("No consultations."),
        cls="card",
    )

    items = q.patient_items(pid, 40)
    item_rows = [[_date(i["item_at"]), Span(i["category"], cls=f"status-pill {i['category']}"),
                  _escape(i["name"]), _eur(i["line_total_vat"])] for i in items]
    spend = Div(
        Div(H3("Recent line items"), cls="card-header"),
        _table(["Date", "Category", "Item", "€"], item_rows) if item_rows else P("No items."),
        cls="card",
    )

    return Div(
        _page_title(f"Patient #{pid}", actions=A("← All patients", href="/patients", cls="btn")),
        cards,
        Div(profile, history, cls="grid-2"),
        spend,
    )


# ---------- Clinical ----------
def clinical_view():
    from web.db import db_exists
    if not db_exists():
        return _no_data_view()
    diag = q.diagnosis_frequency(15)
    diag_chart = plot_div("clin-diag", _plot_spec(
        [{"type": "bar", "orientation": "h",
          "y": [d["name"] for d in diag][::-1],
          "x": [d["n"] for d in diag][::-1],
          "marker": {"color": ACCENT}}],
        _base_layout(height=420),
    ))
    diag_rows = [[d["name"], d["n"], d["patients"]] for d in diag]

    clinicians = q.clinician_activity()
    clinician_rows = [[f"Clinician #{v['clinician_id']}", v["consultations"], v["line_items"], _eur(v["revenue"])]
                      for v in clinicians]

    return Div(
        _page_title("Clinical", "Diagnosis patterns and clinician activity"),
        Div(
            Div(Div(H3("Most frequent diagnoses"), cls="card-header"), *diag_chart, cls="card"),
            Div(Div(H3("Diagnosis table"), cls="card-header"),
                _table(["Diagnosis", "Count", "Patients"], diag_rows), cls="card"),
            cls="grid-2",
        ),
        Div(
            Div(H3("Clinician activity"), cls="card-header"),
            _table(["Clinician", "Consultations", "Line items", "Revenue"], clinician_rows)
            if clinician_rows else P("No clinician data."),
            cls="card",
        ),
    )


# ---------- Revenue ----------
def revenue_view():
    from web.db import db_exists
    if not db_exists():
        return _no_data_view()
    cat = q.revenue_by_category()
    total = sum(r["revenue"] or 0 for r in cat)
    cards = Div(
        kpi_card("Lifetime revenue", _eur(total)),
        kpi_card("Revenue (90d)", _eur(q.overview_kpis()["rev_90"])),
        kpi_card("Categories", len(cat), neutral=True),
        cls="kpi-grid", style="grid-template-columns:repeat(3,1fr);",
    )
    trend = q.monthly_trend(18)
    months = [r["month"] for r in trend]
    rev_chart = plot_div("rev-trend", _plot_spec(
        [{"type": "bar", "x": months, "y": [r["revenue"] for r in trend],
          "marker": {"color": ACCENT}}],
        _base_layout("Monthly revenue (€, incl VAT)"),
    ))
    cat_rows = [[Span(c["category"], cls=f"status-pill {c['category']}"), c["lines"],
                 _eur(c["revenue"]),
                 f"{(100*(c['revenue'] or 0)/total):.0f}%" if total else "—"] for c in cat]
    return Div(
        _page_title("Revenue", "Where clinic revenue comes from"),
        cards,
        Div(Div(H3("Monthly revenue"), cls="card-header"), *rev_chart, cls="card"),
        Div(Div(H3("Revenue by category"), cls="card-header"),
            _table(["Category", "Lines", "Revenue", "Share"], cat_rows), cls="card"),
    )


# ---------- Admin: Data & Import ----------
def data_admin_view():
    from web.db import db_exists, DB_PATH, reference_date
    import os
    exists = db_exists()
    counts = {}
    if exists:
        from web.db import query
        for t in ("patient", "client", "consultation", "diagnosis", "note", "item"):
            counts[t] = query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"]
    count_rows = [[t, n] for t, n in counts.items()]

    exports = []
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    if os.path.isdir(data_dir):
        exports = sorted(f for f in os.listdir(data_dir) if f.endswith(".xlsx"))

    return Div(
        _page_title("Data & Import", "Local SQLite built from PMS exports"),
        Div(
            Div(H3("Database"), cls="card-header"),
            P(NotStr(f"Path: <code>{DB_PATH}</code>")),
            P(f"Status: {'loaded' if exists else 'not found'} · reference date {reference_date() if exists else '—'}"),
            _table(["Table", "Rows"], count_rows) if count_rows else P("No database yet."),
            cls="card",
        ),
        Div(
            Div(H3("Refresh from export"), cls="card-header"),
            P("Drop a new PMS export into data/ and rebuild:"),
            NotStr("<pre style='background:var(--surface-2);padding:12px;border-radius:6px;'>"
                   "python -m pms.importer [export.xlsx]</pre>"),
            P("Detected exports: " + (", ".join(f"{e}" for e in exports) or "none"),
              style="color:var(--text-mute);font-size:13px;"),
            cls="card",
        ),
        Div(
            Div(H3("Patient contacts (needed for outbound campaigns)"), cls="card-header"),
            P("This export contains client IDs but no patient name/phone/email. "
              "Provide a clients export to enable real SMS/email sends; until then "
              "campaign lists key on Client ID."),
            cls="card",
        ),
    )


# ---------- AI assistant (full page) ----------
def ai_full_view(thread_id: str):
    from web.layout import SAMPLE_QUESTIONS
    return Div(
        Div(Div(H1("AI Assistant"),
                Div("Ask about patients, immunisations, revenue — in plain language", cls="sub")),
            Div(
                Button("Copy Chat", id="copy-chat-btn", cls="chat-action-btn",
                       onclick="copyChat()", title="Copy conversation to clipboard"),
                Button("Share", id="share-chat-btn", cls="chat-action-btn",
                       onclick="shareChat()", title="Share conversation link"),
                style="display:flex; gap:6px;",
            ),
            cls="page-title"),
        Div(
            Div(
                Div(
                    NotStr(
                        "Welcome! I'm the FastClinic AI assistant. Just ask in plain language — "
                        "e.g. <em>\"Which patients are overdue for their booster?\"</em> or "
                        "<em>\"How is the clinic performing this month?\"</em><br><br>"
                        "Power users can type <code>/help</code> for slash-command shortcuts."
                    ),
                    cls="msg system",
                ),
                id="chat-body", cls="chat-body",
            ),
            Form(
                Input(type="hidden", name="thread_id", value=thread_id, id="thread-id"),
                Div(
                    Input(type="text", name="message", id="chat-input",
                          placeholder="Ask a question or type /due /lapsed /help …",
                          autocomplete="off"),
                    Button("Send", type="submit", cls="chat-send-btn", id="chat-send-btn"),
                    cls="chat-input-row",
                ),
                onsubmit="return streamChat(event)",
                style="border-top:1px solid var(--border); padding:14px 16px; background:var(--surface);",
            ),
            Div(
                Div(Span("Try asking:", style="font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:.12em; color:var(--text-mute); margin-right:6px;"),
                    *[NotStr(f"<button class='sample-card' style='width:auto;display:inline-flex;' onclick=\"fillChat('{q}'); sendMessage(null);\">{_escape(q)}</button>")
                      for q in SAMPLE_QUESTIONS],
                    Span(NotStr("&middot;"), style="color:var(--text-mute);margin:0 2px;"),
                    NotStr("<button class='shortcut-hint-btn' onclick=\"fillChat('/help'); sendMessage(null);\">⌘ Shortcuts</button>"),
                    style="display:flex; flex-wrap:wrap; gap:6px; align-items:center;"),
                style="padding:8px 16px; background:var(--surface); border-top:1px solid var(--border);",
            ),
            style="display:flex; flex-direction:column; flex:1; overflow:hidden; "
                  "background:var(--surface); border:1px solid var(--border); border-radius:10px; "
                  "min-height:calc(100vh - 120px);",
        ),
    )


def prompt_view():
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "prompts", "system_prompt.md")
    try:
        with open(path) as f:
            content = f.read()
    except Exception as e:
        content = f"Error reading prompt: {e}"
    return Div(
        _page_title("System Prompt", "Read-only view of the AI agent system prompt"),
        Div(
            Div(H3("prompts/system_prompt.md"), cls="card-header"),
            NotStr(f"<pre style='white-space:pre-wrap; font-family:ui-monospace,monospace; "
                   f"font-size:12px; max-height:70vh; overflow:auto; background:var(--surface-2); "
                   f"padding:12px; border-radius:6px;'>{_escape(content)}</pre>"),
            cls="card",
        ),
    )


# ---------- SMS broadcaster ----------
def sms_broadcaster_view():
    from util.sms import available_providers
    from web.db import scalar, db_exists
    providers = available_providers()

    provider_opts = []
    if not providers:
        provider_opts.append(Option("Demo mode — no live provider", value="", disabled=True, selected=True))
    else:
        for p in providers:
            label = {"twilio": "Twilio", "voodoo": "VoodooSMS"}.get(p, p)
            provider_opts.append(Option(label, value=p))

    contactable = 0
    if db_exists():
        contactable = scalar("SELECT COUNT(*) FROM client WHERE phone IS NOT NULL AND phone <> ''") or 0

    demo_banner = None
    if not providers:
        demo_banner = NotStr(
            "<div class='callout'><strong>Demo mode.</strong> Live sending switches on as soon as "
            "an SMS provider (Twilio or VoodooSMS) is connected — that's a later setup step. "
            "You can already build and export targeted campaign lists from the Activation tabs"
            + (f", where <strong>{contactable:,} patients</strong> have a phone number on file." if contactable else ".")
            + "</div>"
        )

    return Div(
        _page_title("SMS Broadcaster", "Turn activation lists into SMS campaigns. "
                    "Build a targeted list in the Activation tabs, then send it here."),
        demo_banner,
        Div(
            Div(H3("Compose message"), cls="card-header"),
            Div(
                Div(Label("Provider"),
                    Select(*provider_opts, name="provider", id="sms-provider", disabled=not providers)),
                Div(Label("Phone Number"),
                    NotStr("<input type='tel' name='phone' id='sms-phone' "
                           "placeholder='+44 7700 900000' required "
                           "pattern='[+]?[0-9\\s]{7,20}' />")),
                Div(Label("Message"),
                    NotStr("<textarea name='message' id='sms-message' "
                           "placeholder='Hello! This is a reminder that your annual health check is "
                           "due. To book, call +44 20 7946 0000 — FastClinic' "
                           "maxlength='1600' oninput='updateCharCount(this)'></textarea>"),
                    Div("0 / 160 chars (1 SMS)", id="sms-chars", cls="sms-char-count")),
                NotStr(
                    "<button class='sms-send' id='sms-btn' "
                    + ("disabled title='Connect a provider to enable live sending' " if not providers else "")
                    + "hx-post='/api/sms/send' hx-target='#sms-result' hx-swap='innerHTML' "
                    "hx-include='#sms-provider,#sms-phone,#sms-message' "
                    "hx-indicator='#sms-spinner' hx-disabled-elt='this'>"
                    "<span id='sms-spinner' class='htmx-indicator spinner'></span>"
                    + ("Connect a provider to send" if not providers else "Send SMS") + "</button>"
                ),
                cls="sms-form",
            ),
            cls="card",
        ),
        Div(id="sms-result"),
        Div(
            Div(H3("Provider Configuration"), cls="card-header"),
            NotStr(
                "<table class='tbl'>"
                "<thead><tr><th>Provider</th><th>Env Vars</th><th>Status</th></tr></thead>"
                "<tbody>"
                "<tr><td>Twilio</td>"
                "<td><code>TWILIO_ACCOUNT_SID</code>, <code>TWILIO_AUTH_TOKEN</code>, <code>TWILIO_FROM_NUMBER</code></td>"
                f"<td><span class='status-pill {'completed' if 'twilio' in providers else 'neutral'}'>{'Configured' if 'twilio' in providers else 'Not configured yet'}</span></td></tr>"
                "<tr><td>VoodooSMS</td>"
                "<td><code>VOODOO_SMS_API_KEY</code>, <code>VOODOO_SMS_FROM</code></td>"
                f"<td><span class='status-pill {'completed' if 'voodoo' in providers else 'neutral'}'>{'Configured' if 'voodoo' in providers else 'Not configured yet'}</span></td></tr>"
                "</tbody></table>"
            ),
            cls="card",
        ),
    )


def sms_send_result(ok: bool, provider: str, message_id: str = "", error: str = ""):
    if ok:
        return Div(
            P(f"SMS sent successfully via {provider}"),
            P(f"Message ID: {message_id}", style="font-size:12px; color:var(--text-dim);") if message_id else None,
            cls="sms-result success",
        )
    return Div(
        P(f"Failed to send via {provider}"),
        P(error, style="font-size:12px;") if error else None,
        cls="sms-result error",
    )


# ---------- Email broadcaster (Postmark) ----------
def email_broadcaster_view():
    from util import email as mail
    cfg = mail.config_summary()
    configured = cfg["configured"]

    config_hint = ""
    if not configured:
        config_hint = (
            "Email not configured. Add Postmark credentials to .env:\n"
            "  POSTMARK_API_TOKEN, POSTMARK_FROM, POSTMARK_FROM_NAME, EMAIL_REPLY_TO"
        )

    from_line = (f"{cfg['from_name']} <{cfg['from']}>" if cfg["from_name"] else cfg["from"]) or "—"

    return Div(
        _page_title("Email Broadcaster", "Send reminder / win-back / follow-up emails via Postmark. "
                    "Build targeted lists in the Activation tabs."),
        Div(
            Div(H3("Send Email"), cls="card-header"),
            NotStr(f"<pre class='sms-result error' style='white-space:pre-wrap; display:block;'>{config_hint}</pre>") if config_hint else None,
            Div(
                Div(Label("From"),
                    NotStr(f"<input type='text' value='{_escape(from_line)}' disabled />")),
                Div(Label("To"),
                    NotStr("<input type='email' name='to' id='email-to' "
                           "placeholder='patient@example.com' required />")),
                Div(Label("Subject"),
                    NotStr("<input type='text' name='subject' id='email-subject' "
                           "placeholder='You are due for a check-up' maxlength='200' required />")),
                Div(Label("Message"),
                    NotStr("<textarea name='body' id='email-body' "
                           "placeholder='Paste a drafted message from the Activation tab, or write your own...'></textarea>")),
                NotStr(
                    "<button class='sms-send' id='email-btn' "
                    f"{'disabled' if not configured else ''} "
                    "hx-post='/api/email/send' hx-target='#email-result' hx-swap='innerHTML' "
                    "hx-include='#email-to,#email-subject,#email-body' "
                    "hx-indicator='#email-spinner' hx-disabled-elt='this'>"
                    "<span id='email-spinner' class='htmx-indicator spinner'></span>Send Email</button>"
                ),
                cls="sms-form",
            ),
            cls="card",
        ),
        Div(id="email-result"),
        Div(
            Div(H3("Provider Configuration"), cls="card-header"),
            NotStr(
                "<table class='tbl'>"
                "<thead><tr><th>Setting</th><th>Value</th></tr></thead><tbody>"
                f"<tr><td>Provider</td><td>Postmark</td></tr>"
                f"<tr><td>From</td><td>{_escape(from_line)}</td></tr>"
                f"<tr><td>Reply-To</td><td>{_escape(cfg['reply_to'] or '—')}</td></tr>"
                f"<tr><td>Message stream</td><td>{_escape(cfg['stream'])}</td></tr>"
                f"<tr><td>API token</td><td><span class='status-pill {'completed' if cfg['token_set'] else 'cancelled'}'>"
                f"{'Configured' if cfg['token_set'] else 'Not set'}</span></td></tr>"
                "</tbody></table>"
            ),
            P("Sending domain fastclinic.example is DKIM + Return-Path verified in Postmark.",
              style="color:var(--text-mute);font-size:12px;"),
            cls="card",
        ),
    )


def email_send_result(ok: bool, message_id: str = "", error: str = ""):
    if ok:
        return Div(
            P("Email sent successfully via Postmark"),
            P(f"Message ID: {message_id}", style="font-size:12px; color:var(--text-dim);") if message_id else None,
            cls="sms-result success",
        )
    return Div(
        P("Failed to send email"),
        P(error, style="font-size:12px;") if error else None,
        cls="sms-result error",
    )
