"""
FastClinic — Accounting Agent (synthetic demo).

A small, self-contained clinic bookkeeping helper for a GP / general-practice
clinic. It generates a deterministic set of SYNTHETIC supplier invoices and
summarises the clinic's monthly expenses: totals by supplier, by category, by
month, plus reclaimable VAT.

IMPORTANT: This is a demo built entirely on SYNTHETIC data. It uses NO real
credentials, NO browser automation, NO vendor-portal logins, and contains NO
personal or company identifiers. All suppliers, invoice numbers and amounts are
made up by the seeded generator below and are safe to commit / share.

Dependencies: Python standard library only.

Usage:
    python scripts/accounting_agent.py                 # generate if missing + summary
    python scripts/accounting_agent.py --regenerate    # rebuild the synthetic set
    python scripts/accounting_agent.py --by category   # break down by category
    python scripts/accounting_agent.py --by supplier    # break down by supplier
    python scripts/accounting_agent.py --by month       # break down by month
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import random
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVOICE_DIR = ROOT / "data" / "invoices_synthetic"

# Deterministic seed so the synthetic set is reproducible across runs/machines.
SEED = 20260101

# Standard-rate VAT applied to taxable supplies in this demo (20%).
VAT_RATE = 0.20

# Plausible GP-clinic suppliers, grouped by expense category. None of these are
# real companies — they are illustrative names for a synthetic ledger.
SUPPLIERS = [
    # (supplier name, category, typical monthly spend band as (low, high) net £)
    ("Meridian Medical Supplies", "medical_consumables", (420, 1850)),
    ("Cobalt Surgical Consumables", "medical_consumables", (300, 1200)),
    ("Greenfield Pharmacy Wholesale", "pharmacy_stock", (900, 3600)),
    ("Riverside Dispensary Distribution", "pharmacy_stock", (650, 2400)),
    ("BrightClean Facilities Services", "cleaning", (180, 520)),
    ("Northgate Utilities", "utilities", (240, 780)),
    ("Lighthouse Locum Staffing Agency", "locum_staffing", (1600, 5200)),
    ("Beacon Clinical Software", "it_software", (120, 460)),
    ("Helix Laboratory Services", "laboratory", (380, 1700)),
    ("Summit Waste & Sharps Disposal", "waste_disposal", (140, 390)),
]

# Human-readable labels for category keys (used in the printed summary).
CATEGORY_LABELS = {
    "medical_consumables": "Medical consumables",
    "pharmacy_stock": "Pharmacy / dispensary stock",
    "cleaning": "Cleaning",
    "utilities": "Utilities",
    "locum_staffing": "Locum staffing",
    "it_software": "IT / software",
    "laboratory": "Laboratory services",
    "waste_disposal": "Clinical waste disposal",
}

# Categories that are zero-rated / exempt for VAT in this demo (no VAT charged,
# nothing to reclaim). Everything else is treated as standard-rated.
VAT_EXEMPT_CATEGORIES = {"locum_staffing"}

MONTHS = list(range(1, 13))  # invoices dated across 2026


@dataclass
class Invoice:
    supplier: str
    invoice_number: str
    date: str  # ISO yyyy-mm-dd
    category: str
    net: float
    vat: float
    gross: float


# ---------------------------------------------------------------------------
# Synthetic invoice generation (deterministic)
# ---------------------------------------------------------------------------

def _money(value: float) -> float:
    """Round to 2 decimal places."""
    return round(value + 1e-9, 2)


def generate_invoices(seed: int = SEED) -> list[Invoice]:
    """Build a deterministic set of synthetic supplier invoices for 2026.

    Each supplier issues roughly one invoice per month; amounts vary within the
    supplier's typical spend band. All values are fabricated.
    """
    rng = random.Random(seed)
    invoices: list[Invoice] = []
    seq = 0

    for month in MONTHS:
        for supplier, category, (low, high) in SUPPLIERS:
            # Not every supplier bills every month — skip some for realism.
            if rng.random() < 0.12:
                continue

            seq += 1
            net = _money(rng.uniform(low, high))

            if category in VAT_EXEMPT_CATEGORIES:
                vat = 0.0
            else:
                vat = _money(net * VAT_RATE)
            gross = _money(net + vat)

            day = rng.randint(1, 28)
            date = dt.date(2026, month, day).isoformat()

            prefix = "".join(w[0] for w in supplier.split()[:3]).upper()
            invoice_number = f"{prefix}-2026-{seq:04d}"

            invoices.append(Invoice(
                supplier=supplier,
                invoice_number=invoice_number,
                date=date,
                category=category,
                net=net,
                vat=vat,
                gross=gross,
            ))

    invoices.sort(key=lambda inv: (inv.date, inv.invoice_number))
    return invoices


def write_invoices(invoices: list[Invoice], directory: Path = INVOICE_DIR) -> Path:
    """Write the synthetic invoices to a CSV file (plus a small README note)."""
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "supplier_invoices.csv"

    fields = ["supplier", "invoice_number", "date", "category", "net", "vat", "gross"]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for inv in invoices:
            writer.writerow(asdict(inv))

    note = directory / "README.txt"
    note.write_text(
        "FastClinic synthetic supplier invoices.\n"
        "Generated by scripts/accounting_agent.py with a fixed seed.\n"
        "All data is fabricated for demo purposes — no real suppliers, "
        "amounts, or credentials.\n"
    )
    return csv_path


def load_invoices(directory: Path = INVOICE_DIR) -> list[Invoice]:
    """Load synthetic invoices from the CSV file."""
    csv_path = directory / "supplier_invoices.csv"
    invoices: list[Invoice] = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            invoices.append(Invoice(
                supplier=row["supplier"],
                invoice_number=row["invoice_number"],
                date=row["date"],
                category=row["category"],
                net=float(row["net"]),
                vat=float(row["vat"]),
                gross=float(row["gross"]),
            ))
    return invoices


def ensure_invoices(regenerate: bool = False) -> list[Invoice]:
    """Generate the synthetic set if missing (or if regenerate=True), then load."""
    csv_path = INVOICE_DIR / "supplier_invoices.csv"
    if regenerate or not csv_path.exists():
        invoices = generate_invoices()
        write_invoices(invoices)
        action = "Regenerated" if regenerate else "Generated"
        print(f"{action} {len(invoices)} synthetic invoices -> {csv_path}")
    return load_invoices()


# ---------------------------------------------------------------------------
# Expense summary
# ---------------------------------------------------------------------------

def summarise(invoices: list[Invoice]) -> dict:
    """Compute totals by supplier, category and month, plus VAT reclaimable."""
    by_supplier: dict[str, dict[str, float]] = {}
    by_category: dict[str, dict[str, float]] = {}
    by_month: dict[str, dict[str, float]] = {}

    total_net = total_vat = total_gross = 0.0

    for inv in invoices:
        month_key = inv.date[:7]  # yyyy-mm
        for bucket, key in (
            (by_supplier, inv.supplier),
            (by_category, inv.category),
            (by_month, month_key),
        ):
            agg = bucket.setdefault(key, {"net": 0.0, "vat": 0.0, "gross": 0.0, "count": 0})
            agg["net"] += inv.net
            agg["vat"] += inv.vat
            agg["gross"] += inv.gross
            agg["count"] += 1

        total_net += inv.net
        total_vat += inv.vat
        total_gross += inv.gross

    return {
        "by_supplier": by_supplier,
        "by_category": by_category,
        "by_month": by_month,
        "totals": {
            "net": _money(total_net),
            "vat": _money(total_vat),
            "gross": _money(total_gross),
            "vat_reclaimable": _money(total_vat),
            "count": len(invoices),
        },
    }


def _fmt(value: float) -> str:
    return f"£{value:,.2f}"


def _print_breakdown(title: str, bucket: dict, label_fn=None) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    width = max((len(label_fn(k) if label_fn else k) for k in bucket), default=10)
    width = max(width, 12)
    print(f"{'':<{width}}  {'count':>5}  {'net':>12}  {'VAT':>12}  {'gross':>12}")
    for key in sorted(bucket, key=lambda k: bucket[k]["gross"], reverse=True):
        agg = bucket[key]
        label = label_fn(key) if label_fn else key
        print(f"{label:<{width}}  {agg['count']:>5}  "
              f"{_fmt(agg['net']):>12}  {_fmt(agg['vat']):>12}  {_fmt(agg['gross']):>12}")


def print_summary(invoices: list[Invoice], by: str | None = None) -> dict:
    """Print a tidy expense summary; `by` optionally focuses one breakdown."""
    summary = summarise(invoices)
    totals = summary["totals"]

    print("=" * 64)
    print("FastClinic — Monthly clinic expense summary (SYNTHETIC demo data)")
    print("=" * 64)
    print(f"Invoices loaded : {totals['count']}")
    print(f"Total net       : {_fmt(totals['net'])}")
    print(f"Total VAT       : {_fmt(totals['vat'])}")
    print(f"Total gross     : {_fmt(totals['gross'])}")
    print(f"VAT reclaimable : {_fmt(totals['vat_reclaimable'])}")

    if by == "category":
        _print_breakdown("By category", summary["by_category"],
                         lambda k: CATEGORY_LABELS.get(k, k))
    elif by == "supplier":
        _print_breakdown("By supplier", summary["by_supplier"])
    elif by == "month":
        _print_breakdown("By month", summary["by_month"])
    else:
        # Default view: show all three breakdowns.
        _print_breakdown("By category", summary["by_category"],
                         lambda k: CATEGORY_LABELS.get(k, k))
        _print_breakdown("By supplier", summary["by_supplier"])
        _print_breakdown("By month", summary["by_month"])

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="FastClinic accounting agent — summarise synthetic clinic "
                    "supplier invoices (demo data, no real credentials).")
    parser.add_argument("--regenerate", action="store_true",
                        help="Rebuild the synthetic invoice set from scratch.")
    parser.add_argument("--by", choices=["category", "supplier", "month"],
                        help="Show a single breakdown (default: show all three).")
    args = parser.parse_args()

    invoices = ensure_invoices(regenerate=args.regenerate)
    print_summary(invoices, by=args.by)


if __name__ == "__main__":
    main()
