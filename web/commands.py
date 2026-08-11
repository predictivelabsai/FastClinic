"""Chat command dispatcher — slash commands that short-circuit the LLM with fast DB answers."""
from __future__ import annotations

from typing import Callable

from web import clinic_queries as q
from web import activation as act
from web.i18n import format_currency, t
from pms.catalog import gender_label, category_label


def _table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return t("*(no rows)*")
    head = "| " + " | ".join(t(header) for header in headers) + " |\n"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |\n"
    body = "\n".join("| " + " | ".join(str(c) for c in r) + " |" for r in rows)
    return head + sep + body


def _eur(v) -> str:
    try:
        return format_currency(float(v), "EUR")
    except (ValueError, TypeError):
        return "—"


def cmd_kpi(args: str) -> str:
    k = q.overview_kpis()
    return (
        f"### {t('Clinic KPIs')}\n\n"
        f"- **{t('Active patients (90d)')}**: {k['active_90']:,}\n"
        f"- **{t('Total patients')}**: {k['total_patients']:,}\n"
        f"- **{t('Visits (30d)')}**: {k['visits_30']:,}\n"
        f"- **{t('Revenue (90d)')}**: {_eur(k['rev_90'])}\n"
        f"- **{t('Lifetime revenue')}**: {_eur(k['rev_total'])}\n"
        f"- **{t('Clients')}**: {k['clients']:,}\n\n"
        f"_{t('Data through {date}.', date=k['reference_date'])}_"
    )


def cmd_due(args: str) -> str:
    cat = args.strip().lower() or "all"
    if cat not in ("all", "vaccine", "health_plan", "repeat_prescription"):
        cat = "all"
    rows = act.due_rows(cat)
    if not rows:
        return f"### {t('Immunisations & Care Plans Due')}\n\n{t('Nothing due — all caught up. 🎉')}"
    table = _table(
        ["Patient", "Service", "Due", "Status", "Overdue"],
        [[f"#{r['patient_id']}", t(r["service"]), r["due_date"],
          t(r["status"]), f"{r['days_overdue']}d" if r["days_overdue"] > 0 else "—"]
         for r in rows[:20]],
    )
    return f"### {t('Immunisations & Care Plans Due')} ({len(rows)})\n\n{table}\n\n[{t('Open Activation →')}](/activation/reminders)"


def cmd_lapsed(args: str) -> str:
    try:
        months = int(args.strip()) if args.strip() else 12
    except ValueError:
        months = 12
    rows = act.lapsed_rows(months)
    if not rows:
        return f"### {t('Lapsed Patients')} (>{months}mo)\n\n{t('None at this threshold. 🎉')}"
    val = sum(r["lifetime_value"] or 0 for r in rows)
    table = _table(
        ["Patient", "Last visit", "Lapsed", "Lifetime €"],
        [[f"#{r['patient_id']}", (r["last_visit"] or "")[:10],
          f"{r['months_since']}mo", _eur(r["lifetime_value"])] for r in rows[:20]],
    )
    return (f"### {t('Lapsed Patients')} (>{months}mo) — {len(rows)}, {_eur(val)} {t('at risk')}\n\n{table}\n\n"
            f"[{t('Open Activation →')}](/activation/lapsed?months={months})")


def cmd_followup(args: str) -> str:
    try:
        days = int(args.strip()) if args.strip() else 14
    except ValueError:
        days = 14
    rows = act.followup_rows(days)
    if not rows:
        return f"### {t('Post-Visit Follow-up')} ({days}d)\n\n{t('No visits in this window.')}"
    table = _table(
        ["Patient", "Visit", "Done", "Revenue"],
        [[f"#{r['patient_id']}", (r["consult_at"] or "")[:10],
          (r["categories"] or "—"), _eur(r["revenue_vat"])] for r in rows[:20]],
    )
    return f"### {t('Post-Visit Follow-up')} ({days}d) — {len(rows)}\n\n{table}\n\n[{t('Open Activation →')}](/activation/followup?days={days})"


def cmd_revenue(args: str) -> str:
    cat = q.revenue_by_category()
    if not cat:
        return f"### {t('Revenue')}\n\n{t('*(no data)*')}"
    table = _table(["Category", "Lines", "Revenue"],
                   [[t(category_label(c["category"])), c["lines"], _eur(c["revenue"])] for c in cat])
    return f"### {t('Revenue by Category')}\n\n" + table


def cmd_patients(args: str) -> str:
    rows = q.patient_list(args.strip(), limit=20)
    if not rows:
        return f"### {t('Patients')}\n\n{t('*(none match)*')}"
    table = _table(
        ["ID", "Name", "Sex", "City", "Visits", "Last visit", "Lifetime €"],
        [[f"#{r['id']}", r["official_name"] or "—", t(gender_label(r["gender"])),
          r["city"] or "—", r["visits"] or 0, (r["last_visit"] or "")[:10],
          _eur(r["lifetime_value"])]
         for r in rows],
    )
    return f"### {t('Patients')} ({len(rows)})\n\n{table}"


def cmd_patient(args: str) -> str:
    pid = args.strip()
    if not pid.isdigit():
        return t("Usage: `/patient ID` (e.g. `/patient 117753`)")
    pid = int(pid)
    p = q.patient_detail(pid)
    if not p:
        return t("No patient #{id}.", id=pid)
    v = q.patient_value(pid)
    cons = q.patient_consultations(pid)
    out = (
        f"### {t('Patient')} #{pid}\n\n"
        f"- **{t('Name')}**: {p['official_name'] or '—'}\n"
        f"- **{t('Sex')}**: {t(gender_label(p['gender']))}\n"
        f"- **{t('DOB')}**: {(p['date_of_birth'] or '—')[:10]}\n"
        f"- **{t('City')}**: {p['city'] or '—'}\n"
        f"- **{t('NHS number')}**: {p['nhs_number'] or '—'}\n"
        f"- **{t('Critical notes')}**: {p['critical_notes'] or '—'}\n"
        f"- **{t('Lifetime value')}**: {_eur(v.get('lifetime_value'))} {t('over')} {v.get('visits') or 0} {t('visits')}\n\n"
    )
    if cons:
        out += _table(["Date", "Items", "Revenue", "Diagnoses"],
                      [[(c["consult_at"] or "")[:10], c["item_count"], _eur(c["revenue_vat"]),
                        (c["diagnoses"] or "—")[:60]] for c in cons[:10]])
    out += f"\n\n[{t('Open patient →')}](/patients/{pid})"
    return out


def cmd_help(args: str) -> str:
    rows = [
        ["`/kpi`", t("Clinic KPIs snapshot")],
        ["`/due [vaccine|health_plan|repeat_prescription]`", t("Patients due / overdue")],
        ["`/lapsed [months]`", t("Lapsed patients to win back (default 12)")],
        ["`/followup [days]`", t("Recent visits to follow up (default 14)")],
        ["`/revenue`", t("Revenue by category")],
        ["`/patients [search]`", t("Find patients")],
        ["`/patient ID`", t("Patient summary")],
        ["`/help`", t("Show this reference")],
    ]
    return (f"### {t('FastClinic Cockpit Commands')}\n\n" +
            _table(["Command", "What it does"], rows) + "\n\n" +
            t("Anything else is answered by the FastClinic AI assistant — just ask in plain "
              "language. Full reference: **Help → Shortcuts**; how-to walkthrough: "
              "**Help → User Guide**."))


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
            return ("local", t("⚠ command error: `{error}`", error=e))
    return ("local", t("Unknown command `/{command}`. Type `/help` for options.", command=cmd))
