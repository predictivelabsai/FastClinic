"""Invoicing + double-entry ledger — Phase 4 of the Clinic OS plan.

Adapted from FastERP's finance code (the estate's richest): per-consultation
invoices, partial payments, and a balanced general ledger. Two clinic-specific
changes to the ERP model:

  • Revenue account is **Fee Income**, not Sales Revenue.
  • The payer is a **party with role=payer** (falling back to the subject's
    primary party). This is how insurance, or a parent paying for a child's
    treatment, falls out of the subject/party model (docs/CLINIC_OS_PLAN.md §2/§8)
    — the body treated and the party billed are deliberately separable.

Invoices + ledger live in the writable ops DB (web/activation_loop.py owns it),
not the read-only PMS replica.
"""
from __future__ import annotations

from web.activation_loop import _connect, query, _now
from web.db import query as _main_query

# debit-normal (+1) / credit-normal (-1), as FastERP.
ACCOUNTS = {"Accounts Receivable": 1, "Cash": 1, "Fee Income": -1}


def _payer_party(subject_id: int) -> int | None:
    """The billed party: an explicit role=payer, else the subject's primary party."""
    rows = _main_query(
        "SELECT party_id, role, is_primary FROM subject_party_role WHERE subject_id=?",
        (subject_id,))
    if not rows:
        return None
    payer = next((r for r in rows if r["role"] == "payer"), None)
    if payer:
        return payer["party_id"]
    primary = next((r for r in rows if r["is_primary"]), rows[0])
    return primary["party_id"]


def post_gl(lines, ref: str) -> bool:
    """Post a balanced journal: lines is [(account, debit, credit)]. Skips no-ops."""
    lines = [(a, round(d, 2), round(c, 2)) for a, d, c in lines if (d or c)]
    if not lines:
        return False
    with _connect() as conn:
        for account, debit, credit in lines:
            conn.execute(
                "INSERT INTO gl_entry (entry_date, account, debit, credit, ref) "
                "VALUES (?,?,?,?,?)", (_now()[:10], account, debit, credit, ref))
        conn.commit()
    return True


def raise_invoice(consultation_id: int) -> int | None:
    """Raise a fee invoice for a consultation. Idempotent (one per consultation).

    Total is the consultation's VAT-inclusive revenue. Posts Dr Accounts
    Receivable / Cr Fee Income. Returns the invoice id, or None if the
    consultation is unknown, zero-value, or already invoiced.
    """
    con = _main_query(
        "SELECT id, subject_id, revenue_vat FROM consultation WHERE id=?",
        (consultation_id,))
    if not con or not con[0]["revenue_vat"]:
        return None
    c = con[0]
    with _connect() as conn:
        if conn.execute("SELECT 1 FROM invoice WHERE consultation_id=?",
                        (consultation_id,)).fetchone():
            return None
        party_id = _payer_party(c["subject_id"])
        total = round(c["revenue_vat"], 2)
        n = (conn.execute("SELECT COALESCE(MAX(id), 7000) FROM invoice").fetchone()[0]) + 1
        code = f"INV-{n}"
        cur = conn.execute(
            """INSERT INTO invoice (code, consultation_id, subject_id, party_id,
                   invoice_date, due_date, total, paid, status, created_at)
               VALUES (?,?,?,?, date('now'), date('now','+30 day'), ?, 0, 'Unpaid', ?)""",
            (code, consultation_id, c["subject_id"], party_id, total, _now()))
        inv_id = cur.lastrowid
        conn.commit()
    post_gl([("Accounts Receivable", total, 0), ("Fee Income", 0, total)], ref=code)
    return inv_id


def record_payment(invoice_id: int, amount: float) -> bool:
    """Apply a payment (partial or full). Posts Dr Cash / Cr Accounts Receivable."""
    inv = query("SELECT * FROM invoice WHERE id=?", (invoice_id,))
    if not inv or amount <= 0:
        return False
    inv = inv[0]
    pay = min(inv["total"] - inv["paid"], amount)
    if pay <= 0:
        return False
    paid = round(inv["paid"] + pay, 2)
    status = "Paid" if paid >= inv["total"] - 0.01 else "Partly Paid"
    with _connect() as conn:
        conn.execute("UPDATE invoice SET paid=?, status=? WHERE id=?",
                     (paid, status, invoice_id))
        conn.commit()
    post_gl([("Cash", pay, 0), ("Accounts Receivable", 0, pay)], ref=inv["code"])
    return True


def trial_balance() -> list[dict]:
    out = []
    for account, normal in ACCOUNTS.items():
        r = query("SELECT COALESCE(SUM(debit),0) AS d, COALESCE(SUM(credit),0) AS c "
                  "FROM gl_entry WHERE account=?", (account,))[0]
        out.append({"account": account, "debit": r["d"], "credit": r["c"],
                    "normal": "Dr" if normal > 0 else "Cr",
                    "balance": round((r["d"] - r["c"]) * normal, 2)})
    return out


def gl_balanced() -> bool:
    r = query("SELECT COALESCE(SUM(debit),0) AS d, COALESCE(SUM(credit),0) AS c FROM gl_entry")[0]
    return abs(r["d"] - r["c"]) < 0.01


def invoices(limit: int = 100) -> list[dict]:
    return query("SELECT * FROM invoice ORDER BY id DESC LIMIT ?", (limit,))


def invoice_totals() -> dict:
    r = query("SELECT COUNT(*) AS n, COALESCE(SUM(total),0) AS billed, "
              "COALESCE(SUM(paid),0) AS collected FROM invoice")[0]
    return {"count": r["n"], "billed": round(r["billed"], 2),
            "collected": round(r["collected"], 2),
            "outstanding": round(r["billed"] - r["collected"], 2)}
