"""FastClinic cockpit eval runner — regression smoke test.

Builds a fresh SQLite DB from the committed synthetic export, then runs the
ground-truth question/shortcut/route sets against the cockpit's command
dispatcher, activation engines, AI fallback, and HTTP routes. Writes a JSON
report to eval-results/ and exits non-zero on any failure.

    python -m evals.run_eval            # run all suites
    python -m evals.run_eval --quiet    # summary only

No external services required (runs against synthetic data; the AI assistant
uses its no-API-key fallback).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EVALS_DIR = Path(__file__).resolve().parent
GT_DIR = EVALS_DIR / "ground-truth"
RESULTS_DIR = ROOT / "eval-results"
SYNTH = ROOT / "data" / "synthetic_fastclinic.xlsx"

# --- build a deterministic DB from the committed synthetic export, BEFORE
# importing any web module (web.db reads FASTCLINIC_DB at import time) ----------
DB_PATH = Path(tempfile.gettempdir()) / "fastclinic_eval.sqlite"
os.environ["FASTCLINIC_DB"] = str(DB_PATH)
os.environ["FASTCLINIC_ADMIN_EMAIL"] = "admin@fastclinic.example"
os.environ["FASTCLINIC_ADMIN_PASSWORD"] = "FastClinic2026$"
os.environ.setdefault("FASTCLINIC_SECRET", "eval-secret")

from pms.importer import build  # noqa: E402


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_shortcuts() -> list[dict]:
    from web.commands import dispatch
    out = []
    for row in _read_csv(GT_DIR / "fastclinic_eval_shortcuts.csv"):
        q, expect, cat = row["question"], row["expect_contains"], row["category"]
        kind, payload = dispatch(q)
        text = payload or ""
        # every shortcut must resolve locally (not fall through to the agent)
        local_ok = kind == "local"
        contains = expect.lower() in text.lower()
        # an unexpected runtime error in a command is always a failure
        no_err = ("⚠ command error" not in text) or ("error" in expect.lower())
        passed = bool(local_ok and contains and no_err)
        out.append({
            "suite": "shortcuts", "question": q, "category": cat,
            "expect_contains": expect, "kind": kind, "passed": passed,
            "detail": "" if passed else
                      f"kind={kind} contains={contains} no_err={no_err}",
            "response_excerpt": text[:160].replace("\n", " "),
        })
    return out


def run_chat() -> list[dict]:
    from web.commands import dispatch
    from graph import clinic_assistant
    out = []
    for row in _read_csv(GT_DIR / "fastclinic_eval_chat.csv"):
        q, expect_kind, cat = row["question"], row["expect_kind"], row["category"]
        kind, payload = dispatch(q)
        kind_ok = kind == expect_kind
        answer_ok = True
        excerpt = (payload or "")[:160]
        if kind == "agent" and q.strip():
            # the assistant must return a non-empty response (fallback w/o API key)
            ans = clinic_assistant.answer(q)
            answer_ok = bool(ans and ans.strip())
            excerpt = ans[:160].replace("\n", " ")
        passed = bool(kind_ok and answer_ok)
        out.append({
            "suite": "chat", "question": q, "category": cat,
            "expect_kind": expect_kind, "kind": kind, "passed": passed,
            "detail": "" if passed else f"kind_ok={kind_ok} answer_ok={answer_ok}",
            "response_excerpt": excerpt,
        })
    return out


def run_routes() -> list[dict]:
    from starlette.testclient import TestClient
    import web_app
    client = TestClient(web_app.app)
    client.post("/login", data={"email": os.environ["FASTCLINIC_ADMIN_EMAIL"],
                                "password": os.environ["FASTCLINIC_ADMIN_PASSWORD"]})
    out = []
    for row in _read_csv(GT_DIR / "fastclinic_eval_routes.csv"):
        path, expect, expect_not, cat = (
            row["path"], row["expect_contains"], row["expect_not_contains"], row["category"])
        try:
            resp = client.get(path)
            body = resp.text
            status_ok = resp.status_code == 200
            contains = expect.lower() in body.lower()
            not_contains = (not expect_not) or (expect_not.lower() not in body.lower())
            passed = bool(status_ok and contains and not_contains)
            detail = "" if passed else \
                f"status={resp.status_code} contains={contains} not_contains={not_contains}"
        except Exception as e:  # noqa: BLE001
            passed, detail, resp = False, f"exception: {e!r}", None
        out.append({
            "suite": "routes", "path": path, "category": cat,
            "expect_contains": expect, "passed": passed, "detail": detail,
            "status": getattr(resp, "status_code", None),
        })
    return out


def run_coverage() -> list[dict]:
    """Assert the data model ingests 100% of every export's columns (1:1 replica)."""
    from pms.xlsx import sheet_names, read_sheet
    from pms import importer as imp
    maps = {"patient": imp.PATIENT_FIELDS, "Consultationdiagnosis": imp.DIAGNOSIS_FIELDS,
            "Consultationnote": imp.NOTE_FIELDS, "Consultationitem": imp.ITEM_FIELDS}
    sources = [("synthetic", SYNTH)]
    out = []
    for label, path in sources:
        if not path.exists():
            continue
        for i, sheet in enumerate(sheet_names(str(path)), start=1):
            if sheet not in maps:
                continue
            rows = read_sheet(str(path), i)
            real = set(rows[0].keys()) if rows else set()
            keys = {xk for (_m, xk, _t, _c) in maps[sheet]}
            uncovered = sorted(real - keys)
            passed = not uncovered
            out.append({
                "suite": "coverage", "question": f"{label}:{sheet}",
                "category": "field_coverage", "passed": passed,
                "detail": "" if passed else f"uncovered={uncovered}",
                "response_excerpt": f"{len(real)} cols, {len(uncovered)} uncovered",
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not SYNTH.exists():
        print(f"ERROR: synthetic export not found at {SYNTH}", file=sys.stderr)
        return 2
    db_counts = build(str(SYNTH), str(DB_PATH))

    cases = run_shortcuts() + run_chat() + run_routes() + run_coverage()

    passed = sum(c["passed"] for c in cases)
    total = len(cases)
    by_suite: dict[str, dict] = {}
    by_cat: dict[str, dict] = {}
    for c in cases:
        for key, bucket in ((c["suite"], by_suite), (c["category"], by_cat)):
            b = bucket.setdefault(key, {"passed": 0, "total": 0})
            b["total"] += 1
            b["passed"] += int(c["passed"])

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "db_row_counts": db_counts,
        "summary": {
            "total": total, "passed": passed, "failed": total - passed,
            "pass_rate": round(passed / total, 4) if total else 0.0,
            "by_suite": by_suite, "by_category": by_cat,
        },
        "cases": cases,
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"fastclinic_eval_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    (RESULTS_DIR / "latest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"\nFastClinic eval — {passed}/{total} passed ({report['summary']['pass_rate']*100:.1f}%)")
    print("  by suite: " + ", ".join(f"{k} {v['passed']}/{v['total']}"
                                      for k, v in by_suite.items()))
    if not args.quiet:
        fails = [c for c in cases if not c["passed"]]
        if fails:
            print(f"\n  {len(fails)} FAILURES:")
            for c in fails:
                ident = c.get("question") or c.get("path")
                print(f"   ✗ [{c['suite']}] {ident!r} — {c['detail']}")
    print(f"  report: {out_path.relative_to(ROOT)}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
