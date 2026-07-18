"""Server-rendered billing views: invoices, payments, trial balance."""
from __future__ import annotations

from fasthtml.common import (
    Div, H1, H3, P, A, Form, Label, Input, Button, Span,
    Table, Thead, Tbody, Tr, Th, Td,
)

from web.db import db_exists
from web.layout import kpi_card
from web import billing


def _money(v) -> str:
    return f"£{(v or 0):,.2f}"


def _status_pill(s: str):
    tone = {"Paid": "completed", "Partly Paid": "neutral",
            "Unpaid": "warn", "Overdue": "warn"}.get(s, "neutral")
    return Span(s, cls=f"status-pill {tone}")


def _body():
    tot = billing.invoice_totals()
    tb = billing.trial_balance()
    invs = billing.invoices(limit=50)

    cards = Div(
        kpi_card("Invoices", tot["count"]),
        kpi_card("Billed", _money(tot["billed"])),
        kpi_card("Collected", _money(tot["collected"])),
        kpi_card("Outstanding", _money(tot["outstanding"]),
                 warn=bool(tot["outstanding"])),
        cls="kpi-grid", style="grid-template-columns:repeat(4,1fr);",
    )
    raise_form = Form(
        Div(
            Label("Consultation ID",
                  Input(name="consultation_id", type="number", placeholder="e.g. 12", required=True)),
            Button("Raise invoice", cls="btn primary", type="submit"),
            style="display:flex; gap:10px; align-items:end;",
        ),
        **{"hx-post": "/billing/invoice", "hx-target": "#billing-body", "hx-swap": "outerHTML"},
    )
    inv_rows = []
    for i in invs:
        pay_btn = (A("Record payment", href="#", cls="btn",
                     **{"hx-post": f"/billing/{i['id']}/pay",
                        "hx-target": "#billing-body", "hx-swap": "outerHTML"})
                   if i["status"] != "Paid" else Span("—"))
        inv_rows.append([
            i["code"],
            A(f"#{i['subject_id']}", href=f"/patients/{i['subject_id']}"),
            f"cons. {i['consultation_id']}",
            _money(i["total"]), _money(i["paid"]),
            _status_pill(i["status"]), pay_btn,
        ])
    tb_rows = [[r["account"], r["normal"], _money(r["debit"]),
                _money(r["credit"]), _money(r["balance"])] for r in tb]
    balanced = billing.gl_balanced()

    return Div(
        cards,
        Div(Div(H3("Raise a fee invoice"), cls="card-header"), raise_form, cls="card"),
        Div(Div(H3(f"Invoices ({len(invs)})"), cls="card-header"),
            Table(Thead(Tr(*[Th(h) for h in
                    ["Code", "Patient", "For", "Total", "Paid", "Status", ""]])),
                  Tbody(*[Tr(*[Td(c) for c in r]) for r in inv_rows]), cls="tbl")
            if inv_rows else P("No invoices yet — raise one above."), cls="card"),
        Div(Div(H3("Trial balance"), cls="card-header"),
            Table(Thead(Tr(*[Th(h) for h in ["Account", "Normal", "Debit", "Credit", "Balance"]])),
                  Tbody(*[Tr(*[Td(c) for c in r]) for r in tb_rows]), cls="tbl"),
            P(("✓ ledger balanced" if balanced else "⚠ ledger NOT balanced"),
              style=f"color:{'var(--accent-green,#1f9d72)' if balanced else 'crimson'};"
                    "font-size:12px;margin-top:8px;"),
            cls="card"),
        id="billing-body",
    )


def view():
    if not db_exists():
        from web.dashboards import _no_data_view
        return _no_data_view()
    return Div(
        Div(Div(H1("Billing"),
                Div("Fee invoices, payments, and a balanced ledger", cls="sub")),
            cls="page-title"),
        _body(),
    )


def body():
    return _body()
