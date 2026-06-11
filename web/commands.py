"""Chat command dispatcher — slash commands that short-circuit the LLM with fast DB answers."""
from __future__ import annotations

from typing import Callable

from web import clinic_queries as q
from web import activation as act
from pms.catalog import gender_label, category_label


def _table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "*(no rows)*"
    head = "| " + " | ".join(headers) + " |\n"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |\n"
    body = "\n".join("| " + " | ".join(str(c) for c in r) + " |" for r in rows)
    return head + sep + body


def _eur(v) -> str:
    try:
        return f"€{float(v):,.0f}"
    except (ValueError, TypeError):
        return "—"


def cmd_kpi(args: str) -> str:
    k = q.overview_kpis()
    return (
        "### Clinic KPIs\n\n"
        f"- **Active patients (90d)**: {k['active_90']:,}\n"
        f"- **Total patients**: {k['total_patients']:,}\n"
        f"- **Visits (30d)**: {k['visits_30']:,}\n"
        f"- **Revenue (90d)**: {_eur(k['rev_90'])}\n"
        f"- **Lifetime revenue**: {_eur(k['rev_total'])}\n"
        f"- **Clients**: {k['clients']:,}\n\n"
        f"_Data through {k['reference_date']}._"
    )


def cmd_due(args: str) -> str:
    cat = args.strip().lower() or "all"
    if cat not in ("all", "vaccine", "health_plan", "repeat_prescription"):
        cat = "all"
    rows = act.due_rows(cat)
    if not rows:
        return "### Immunisations & Care Plans Due\n\nNothing due — all caught up. 🎉"
    table = _table(
        ["Patient", "Service", "Due", "Status", "Overdue"],
        [[f"#{r['patient_id']}", r["service"], r["due_date"],
          r["status"], f"{r['days_overdue']}d" if r["days_overdue"] > 0 else "—"]
         for r in rows[:20]],
    )
    return f"### Immunisations & Care Plans Due ({len(rows)})\n\n{table}\n\n[Open Activation →](/activation/reminders)"


def cmd_lapsed(args: str) -> str:
    try:
        months = int(args.strip()) if args.strip() else 12
    except ValueError:
        months = 12
    rows = act.lapsed_rows(months)
    if not rows:
        return f"### Lapsed Patients (>{months}mo)\n\nNone at this threshold. 🎉"
    val = sum(r["lifetime_value"] or 0 for r in rows)
    table = _table(
        ["Patient", "Last visit", "Lapsed", "Lifetime €"],
        [[f"#{r['patient_id']}", (r["last_visit"] or "")[:10],
          f"{r['months_since']}mo", _eur(r["lifetime_value"])] for r in rows[:20]],
    )
    return (f"### Lapsed Patients (>{months}mo) — {len(rows)}, {_eur(val)} at risk\n\n{table}\n\n"
            f"[Open Activation →](/activation/lapsed?months={months})")


def cmd_followup(args: str) -> str:
    try:
        days = int(args.strip()) if args.strip() else 14
    except ValueError:
        days = 14
    rows = act.followup_rows(days)
    if not rows:
        return f"### Post-Visit Follow-up ({days}d)\n\nNo visits in this window."
    table = _table(
        ["Patient", "Visit", "Done", "Revenue"],
        [[f"#{r['patient_id']}", (r["consult_at"] or "")[:10],
          (r["categories"] or "—"), _eur(r["revenue_vat"])] for r in rows[:20]],
    )
    return f"### Post-Visit Follow-up ({days}d) — {len(rows)}\n\n{table}\n\n[Open Activation →](/activation/followup?days={days})"


def cmd_revenue(args: str) -> str:
    cat = q.revenue_by_category()
    if not cat:
        return "### Revenue\n\n*(no data)*"
    table = _table(["Category", "Lines", "Revenue"],
                   [[category_label(c["category"]), c["lines"], _eur(c["revenue"])] for c in cat])
    return "### Revenue by Category\n\n" + table


def cmd_patients(args: str) -> str:
    rows = q.patient_list(args.strip(), limit=20)
    if not rows:
        return "### Patients\n\n*(none match)*"
    table = _table(
        ["ID", "Name", "Sex", "City", "Visits", "Last visit", "Lifetime €"],
        [[f"#{r['id']}", r["official_name"] or "—", gender_label(r["gender"]),
          r["city"] or "—", r["visits"] or 0, (r["last_visit"] or "")[:10],
          _eur(r["lifetime_value"])]
         for r in rows],
    )
    return f"### Patients ({len(rows)})\n\n{table}"


def cmd_patient(args: str) -> str:
    pid = args.strip()
    if not pid.isdigit():
        return "Usage: `/patient ID` (e.g. `/patient 117753`)"
    pid = int(pid)
    p = q.patient_detail(pid)
    if not p:
        return f"No patient #{pid}."
    v = q.patient_value(pid)
    cons = q.patient_consultations(pid)
    out = (
        f"### Patient #{pid}\n\n"
        f"- **Name**: {p['official_name'] or '—'}\n"
        f"- **Sex**: {gender_label(p['gender'])}\n"
        f"- **DOB**: {(p['date_of_birth'] or '—')[:10]}\n"
        f"- **City**: {p['city'] or '—'}\n"
        f"- **NHS number**: {p['nhs_number'] or '—'}\n"
        f"- **Critical notes**: {p['critical_notes'] or '—'}\n"
        f"- **Lifetime value**: {_eur(v.get('lifetime_value'))} over {v.get('visits') or 0} visits\n\n"
    )
    if cons:
        out += _table(["Date", "Items", "Revenue", "Diagnoses"],
                      [[(c["consult_at"] or "")[:10], c["item_count"], _eur(c["revenue_vat"]),
                        (c["diagnoses"] or "—")[:60]] for c in cons[:10]])
    out += f"\n\n[Open patient →](/patients/{pid})"
    return out


def cmd_help(args: str) -> str:
    return (
        "### FastClinic Cockpit Commands\n\n"
        "| Command | What it does |\n| --- | --- |\n"
        "| `/kpi` | Clinic KPIs snapshot |\n"
        "| `/due [vaccine\\|health_plan\\|repeat_prescription]` | Patients due / overdue |\n"
        "| `/lapsed [months]` | Lapsed patients to win back (default 12) |\n"
        "| `/followup [days]` | Recent visits to follow up (default 14) |\n"
        "| `/revenue` | Revenue by category |\n"
        "| `/patients [search]` | Find patients |\n"
        "| `/patient ID` | Patient summary |\n"
        "| `/help` | Show this reference |\n\n"
        "Anything else is answered by the FastClinic AI assistant — just ask in plain "
        "language. Full reference: **Help → Shortcuts**; how-to walkthrough: "
        "**Help → User Guide**."
    )


LOCAL_COMMANDS: dict[str, Callable[[str], str]] = {
    "kpi": cmd_kpi, "kpis": cmd_kpi,
    "due": cmd_due, "reminders": cmd_due,
    "lapsed": cmd_lapsed,
    "followup": cmd_followup, "follow-up": cmd_followup,
    "revenue": cmd_revenue,
    "patients": cmd_patients,
    "patient": cmd_patient,
    "help": cmd_help, "?": cmd_help,
}


# Natural-language phrases that should surface the shortcut list directly in chat,
# without spending an LLM call.
_HELP_PHRASES = {
    "help", "shortcuts", "commands", "what shortcuts", "what commands",
    "what shortcuts do you have", "what commands do you have",
    "what shortcuts are there", "what are the shortcuts", "what are the commands",
    "list shortcuts", "list commands", "show shortcuts", "show commands",
    "show me the shortcuts", "shortcut list", "command list",
}


def dispatch(message: str) -> tuple[str, str | None]:
    """
    Returns (kind, payload):
    - ("local", markdown)  — render directly
    - ("agent", prompt|None) — send to AI agent (None = use original message)

    Supports /slash and colon: syntax (e.g. /due or due:).
    """
    msg = message.strip()
    if not msg:
        return ("agent", None)

    # Help-intent in plain language → show the shortcut list in chat.
    if msg.lower().rstrip("?.! ") in _HELP_PHRASES:
        return ("local", cmd_help(""))

    cmd, args = "", ""
    if msg.startswith("/"):
        parts = msg[1:].split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
    elif ":" in msg:
        colon = msg.index(":")
        prefix = msg[:colon].strip().lower()
        if prefix in LOCAL_COMMANDS:
            cmd = prefix
            args = msg[colon + 1:].strip()

    if not cmd:
        return ("agent", None)
    if cmd in LOCAL_COMMANDS:
        try:
            return ("local", LOCAL_COMMANDS[cmd](args))
        except Exception as e:
            return ("local", f"⚠ command error: `{e}`")
    return ("local", f"Unknown command `/{cmd}`. Type `/help` for options.")
