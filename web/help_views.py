"""Help section — Shortcuts reference + web User Guide."""
from __future__ import annotations

import json
import os
from fasthtml.common import Div, H1, H3, P, A, NotStr, Script, Table, Thead, Tbody, Tr, Th, Td

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_MD = os.path.join(ROOT, "docs", "fastclinic_user_guide.md")

# Single source of truth for the slash-command reference.
SHORTCUTS = [
    ("/kpi", "Clinic KPIs — active/total patients, visits, revenue, clients"),
    ("/due [vaccine|health_plan|repeat_prescription]", "Patients due or overdue for a recurring service"),
    ("/lapsed [months]", "Lapsed patients to win back (default 12 months)"),
    ("/followup [days]", "Recent visits to follow up (default 14 days)"),
    ("/revenue", "Revenue broken down by service category"),
    ("/patients [search]", "Find patients by id, name or city"),
    ("/patient ID", "A single patient's profile and visit history"),
    ("/help", "Show the shortcut reference in chat"),
]


def _page_title(title: str, sub: str = "", actions=None):
    return Div(
        Div(H1(title), Div(sub, cls="sub") if sub else None),
        actions,
        cls="page-title",
    )


def shortcuts_view():
    rows = [Tr(Td(NotStr(f"<code>{cmd}</code>")), Td(desc)) for cmd, desc in SHORTCUTS]
    return Div(
        _page_title("Shortcuts", "Slash commands for power users — type them in the AI Copilot"),
        Div(
            P(NotStr(
                "Most people just <strong>chat</strong> with the Copilot in plain language. "
                "These shortcuts are an optional fast path that pull cockpit data instantly. "
                "Type them in the Copilot box (right rail) or on the AI Assistant page. "
                "Both <code>/slash</code> and <code>colon:</code> syntax work.")),
            cls="callout",
        ),
        Div(
            Div(H3("Command reference"), cls="card-header"),
            Table(Thead(Tr(Th("Command"), Th("What it does"))), Tbody(*rows), cls="tbl"),
            cls="card",
        ),
        Div(
            Div(H3("Tips"), cls="card-header"),
            NotStr(
                "<ul style='margin:4px 0; padding-left:20px; line-height:1.7; color:var(--text-dim);'>"
                "<li>Arguments are optional — <code>/lapsed</code> uses sensible defaults, "
                "<code>/lapsed 18</code> overrides them.</li>"
                "<li>Results include a link to open the matching full page.</li>"
                "<li>Not sure? Just ask a question — e.g. <em>\"Who should we win back this month?\"</em></li>"
                "</ul>"),
            cls="card",
        ),
    )


def user_guide_view():
    try:
        md = open(GUIDE_MD, encoding="utf-8").read()
    except OSError:
        md = "# User Guide\n\nGuide source not found."
    # Images + PDF are served by FastHTML's static handler from docs/.
    md = md.replace("](img/", "](/docs/img/")
    actions = A("⬇ Download PDF", href="/docs/fastclinic_user_guide.pdf", cls="btn primary",
                target="_blank")
    return Div(
        _page_title("User Guide", "How to grow & activate your clinic's customers", actions=actions),
        Div(
            NotStr("<div id='guide-md' class='guide-doc'></div>"),
            Script(NotStr(
                f"document.getElementById('guide-md').innerHTML = marked.parse({json.dumps(md)});")),
            cls="card",
        ),
    )
