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
        _insert_gl(conn, lines, ref)
        conn.commit()
    return True


def _insert_gl(conn, lines, ref: str) -> None:
    """Insert a balanced journal on an existing transaction."""
    lines = [(a, round(d, 2), round(c, 2)) for a, d, c in lines if (d or c)]
    if round(sum(d for _, d, _ in lines), 2) != round(sum(c for _, _, c in lines), 2):
        raise ValueError("journal is not balanced")
    for account, debit, credit in lines:
        if account not in ACCOUNTS:
            raise ValueError(f"unknown ledger account {account!r}")
        conn.execute(
            "INSERT INTO gl_entry (entry_date, account, debit, credit, ref) "
            "VALUES (?,?,?,?,?)", (_now()[:10], account, debit, credit, ref))


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
        conn.execute("BEGIN IMMEDIATE")
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
        _insert_gl(
            conn,
            [("Accounts Receivable", total, 0), ("Fee Income", 0, total)],
            ref=code,
        )
        conn.commit()
    return inv_id


def record_payment(
    invoice_id: int,
    amount: float,
    *,
    method: str = "",
    reference: str = "",
    idempotency_key: str | None = None,
) -> bool:
    """Apply a payment (partial or full). Posts Dr Cash / Cr Accounts Receivable."""
    if amount <= 0:
        return False
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if idempotency_key and conn.execute(
            "SELECT 1 FROM payment WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone():
            return True
        row = conn.execute("SELECT * FROM invoice WHERE id=?", (invoice_id,)).fetchone()
        if not row or row["status"] == "Void":
            return False
        inv = dict(row)
        outstanding = round(inv["total"] - inv["paid"], 2)
        if outstanding <= 0 or amount > outstanding + 0.005:
            return False
        pay = round(amount, 2)
        paid = round(inv["paid"] + pay, 2)
        status = "Paid" if paid >= inv["total"] - 0.01 else "Partly Paid"
        conn.execute("UPDATE invoice SET paid=?, status=? WHERE id=?",
                     (paid, status, invoice_id))
        conn.execute(
            """INSERT INTO payment
               (invoice_id, amount, method, reference, status, idempotency_key,
                received_at, created_at)
               VALUES (?,?,?,?, 'received', ?,?,?)""",
            (invoice_id, pay, method, reference, idempotency_key, _now(), _now()),
        )
        _insert_gl(
            conn,
            [("Cash", pay, 0), ("Accounts Receivable", 0, pay)],
            ref=inv["code"],
        )
        conn.commit()
    return True


def payments(limit: int = 100, invoice_id: int | None = None) -> list[dict]:
    if invoice_id is not None:
        return query(
            "SELECT * FROM payment WHERE invoice_id=? ORDER BY id DESC LIMIT ?",
            (invoice_id, limit),
        )
    return query("SELECT * FROM payment ORDER BY id DESC LIMIT ?", (limit,))


def payment(payment_id: int) -> dict | None:
    rows = query("SELECT * FROM payment WHERE id=?", (payment_id,))
    return rows[0] if rows else None


def refund_payment(payment_id: int) -> bool:
    """Reverse a received payment without deleting its audit history."""
    pay = payment(payment_id)
    if not pay or pay["status"] != "received":
        return False
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        pay = conn.execute("SELECT * FROM payment WHERE id=?", (payment_id,)).fetchone()
        if not pay or pay["status"] != "received":
            return False
        inv = conn.execute("SELECT * FROM invoice WHERE id=?", (pay["invoice_id"],)).fetchone()
        if not inv or inv["status"] == "Void":
            return False
        paid = max(0.0, round(inv["paid"] - pay["amount"], 2))
        status = "Unpaid" if paid <= 0 else "Partly Paid"
        conn.execute("UPDATE payment SET status='refunded' WHERE id=?", (payment_id,))
        conn.execute("UPDATE invoice SET paid=?, status=? WHERE id=?", (paid, status, inv["id"]))
        _insert_gl(
            conn,
            [("Accounts Receivable", pay["amount"], 0), ("Cash", 0, pay["amount"])],
            ref=f"{inv['code']}:refund:{payment_id}",
        )
        conn.commit()
    return True


def void_invoice(invoice_id: int) -> bool:
    """Void an invoice using reversing journal entries; never delete ledger history."""
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        inv = conn.execute("SELECT * FROM invoice WHERE id=?", (invoice_id,)).fetchone()
        if not inv or inv["status"] == "Void":
            return False
        if inv["paid"]:
            _insert_gl(
                conn,
                [("Accounts Receivable", inv["paid"], 0), ("Cash", 0, inv["paid"])],
                ref=f"{inv['code']}:void-payment",
            )
            conn.execute(
                "UPDATE payment SET status='voided' WHERE invoice_id=? AND status='received'",
                (invoice_id,),
            )
        _insert_gl(
            conn,
            [("Fee Income", inv["total"], 0), ("Accounts Receivable", 0, inv["total"])],
            ref=f"{inv['code']}:void",
        )
        conn.execute("UPDATE invoice SET paid=0, status='Void' WHERE id=?", (invoice_id,))
        conn.commit()
    return True


def invoice(invoice_id: int) -> dict | None:
    rows = query("SELECT * FROM invoice WHERE id=?", (invoice_id,))
    return rows[0] if rows else None


def update_invoice_due_date(invoice_id: int, due_date: str) -> tuple[dict, dict] | None:
    before = invoice(invoice_id)
    if not before:
        return None
    if before["status"] in {"Paid", "Void"}:
        raise ValueError("Paid or void invoices cannot be rescheduled")
    with _connect() as conn:
        conn.execute("UPDATE invoice SET due_date=? WHERE id=?", (due_date, invoice_id))
        conn.commit()
    return before, invoice(invoice_id) or before


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
              "COALESCE(SUM(paid),0) AS collected FROM invoice WHERE status <> 'Void'")[0]
    return {"count": r["n"], "billed": round(r["billed"], 2),
            "collected": round(r["collected"], 2),
            "outstanding": round(r["billed"] - r["collected"], 2)}
