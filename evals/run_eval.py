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
OPS_DB_PATH = Path(tempfile.gettempdir()) / "fastclinic_eval_ops.sqlite"
AUTH_DB_PATH = Path(tempfile.gettempdir()) / "fastclinic_eval_accounts.sqlite"
OPS_DB_PATH.unlink(missing_ok=True)  # start the activation loop from empty
AUTH_DB_PATH.unlink(missing_ok=True)  # never touch the configured account store
os.environ["FASTCLINIC_DB"] = str(DB_PATH)
os.environ["FASTCLINIC_OPS_DB"] = str(OPS_DB_PATH)
os.environ["FASTSME_AUTH_DB"] = str(AUTH_DB_PATH)
os.environ["FASTCLINIC_DATABASE_BACKEND"] = "sqlite"
os.environ["FASTCLINIC_OPS_BACKEND"] = "sqlite"
os.environ["FASTCLINIC_BOOTSTRAP_AUTH_ENABLED"] = "true"
os.environ["FASTCLINIC_BOOTSTRAP_EMAIL"] = "admin@fastclinic.example"
os.environ["FASTCLINIC_BOOTSTRAP_PASSWORD"] = "FastClinic2026$"
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
    response = client.post(
        "/auth/local/login",
        data={"email": os.environ["FASTCLINIC_BOOTSTRAP_EMAIL"],
              "password": os.environ["FASTCLINIC_BOOTSTRAP_PASSWORD"]},
    )
    if response.status_code != 200:
        raise RuntimeError("Evaluation bootstrap account could not sign in")
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


def run_consent() -> list[dict]:
    """Assert no contact who opted out of marketing can be reached.

    Regression gate for a real defect: `party.marketing_opt_out` was stored by
    the importer and read by nothing, so every campaign list and CSV export
    included opted-out contacts, and the SMS/email routes would send to them.
    """
    from web import activation as act
    from web.consent import is_suppressed_phone, is_suppressed_email
    from web.db import query

    opted = {r["id"] for r in query("SELECT id FROM party WHERE marketing_opt_out = 1")}
    out = []

    # 1. no opted-out contact survives any engine (incl. its CSV export)
    for name, fn in (("reminders", act.due_rows), ("lapsed", act.lapsed_rows),
                     ("followup", act.followup_rows)):
        rows = fn()
        leaked = [r for r in rows if r.get("contact_id") in opted]
        out.append({
            "suite": "consent", "question": f"{name}:no-opted-out-in-list",
            "category": "marketing_consent", "passed": not leaked,
            "detail": "" if not leaked else f"{len(leaked)} opted-out contacts leaked",
            "response_excerpt": f"{len(rows)} rows, {len(leaked)} leaked",
        })

    # 2. the send-time guard blocks an opted-out recipient and spares a consenting one
    blocked = query("SELECT phone, email FROM party WHERE marketing_opt_out = 1 "
                    "AND phone IS NOT NULL AND email IS NOT NULL LIMIT 1")
    allowed = query("SELECT phone, email FROM party WHERE marketing_opt_out = 0 "
                    "AND phone IS NOT NULL AND email IS NOT NULL LIMIT 1")
    if blocked and allowed:
        b, a = blocked[0], allowed[0]
        checks = [
            ("guard-blocks-opted-out-sms", is_suppressed_phone(b["phone"]) is True),
            ("guard-blocks-opted-out-email", is_suppressed_email(b["email"]) is True),
            # national 0-prefixed form must resolve to the same person as E.164
            ("guard-blocks-national-form", is_suppressed_phone("0" + b["phone"][3:]) is True),
            ("guard-allows-consenting-sms", is_suppressed_phone(a["phone"]) is False),
            ("guard-allows-consenting-email", is_suppressed_email(a["email"]) is False),
        ]
        for label, ok in checks:
            out.append({
                "suite": "consent", "question": label,
                "category": "marketing_consent", "passed": ok,
                "detail": "" if ok else "guard gave the wrong answer",
                "response_excerpt": "ok" if ok else "FAILED",
            })
    return out


def run_model() -> list[dict]:
    """Assert the generic subject/party/role invariants (docs/CLINIC_OS_PLAN.md §2).

    The 1:1 patient=contact collapse was a veterinary-lineage bug: a sixth of
    patients are minors who cannot be their own contactable party. These gates
    fail if that regresses — e.g. if the synth generator starts giving children
    their own phones again, or a minor is linked as `self`.
    """
    from web.db import query, scalar, reference_date
    ref = reference_date()
    out = []

    def check(label, passed, detail=""):
        out.append({"suite": "model", "question": label, "category": "generic_core",
                    "passed": bool(passed), "detail": "" if passed else detail,
                    "response_excerpt": detail or "ok"})

    # every subject has exactly one primary contactable party
    orphans = scalar(
        "SELECT COUNT(*) FROM subject s WHERE s.deceased_at IS NULL AND NOT EXISTS "
        "(SELECT 1 FROM subject_party_role r WHERE r.subject_id=s.id AND r.is_primary=1)"
    ) or 0
    check("every-subject-has-primary-party", orphans == 0, f"{orphans} subjects without a primary party")

    # no minor is their own party (role='self')
    bad_self = scalar(
        "SELECT COUNT(*) FROM subject s JOIN subject_party_role r ON r.subject_id=s.id "
        "WHERE r.role='self' AND s.date_of_birth > date(?, '-16 years')", (ref,)
    ) or 0
    check("no-minor-is-self", bad_self == 0, f"{bad_self} minors linked as self")

    # every minor is linked to a guardian
    minors = scalar("SELECT COUNT(*) FROM subject WHERE date_of_birth > date(?, '-16 years')", (ref,)) or 0
    minors_guarded = scalar(
        "SELECT COUNT(DISTINCT s.id) FROM subject s JOIN subject_party_role r ON r.subject_id=s.id "
        "WHERE r.role='guardian' AND s.date_of_birth > date(?, '-16 years')", (ref,)
    ) or 0
    check("every-minor-has-guardian", minors == minors_guarded,
          f"{minors - minors_guarded} of {minors} minors ungoverned")

    # the 1-party:N-subjects path is genuinely exercised (siblings share a guardian)
    shared = scalar(
        "SELECT COUNT(*) FROM (SELECT party_id FROM subject_party_role "
        "GROUP BY party_id HAVING COUNT(*) > 1)"
    ) or 0
    check("one-party-covers-many-subjects", shared > 0,
          "no shared-guardian families — 1:N path never exercised")

    # no minor has a party that is uniquely theirs with a personal phone
    minor_own_phone = scalar(
        "SELECT COUNT(*) FROM subject s JOIN subject_party_role r ON r.subject_id=s.id "
        "JOIN party p ON p.id=r.party_id "
        "WHERE s.date_of_birth > date(?, '-16 years') AND r.role='self' "
        "AND p.phone IS NOT NULL", (ref,)
    ) or 0
    check("no-toddler-with-own-phone", minor_own_phone == 0,
          f"{minor_own_phone} minors have their own phone")

    return out


def run_loop() -> list[dict]:
    """Assert the persisted activation loop (docs/CLINIC_OS_PLAN.md §6, Phase 2).

    Closes the loop the marketing cockpit previously left open: reminders are
    persisted, every send attempt is logged (sent / failed / blocked), duplicate
    enqueues are suppressed, and a blocked send never reaches a provider.
    """
    from web import activation_loop as aloop
    from web.db import query as mq
    out = []

    def check(label, passed, detail=""):
        out.append({"suite": "loop", "question": label, "category": "activation_loop",
                    "passed": bool(passed), "detail": "" if passed else detail,
                    "response_excerpt": detail or "ok"})

    n1 = aloop.enqueue_due_reminders()
    check("enqueue-creates-reminders", n1 > 0, f"enqueued {n1}")
    pend1 = aloop.reminder_counts().get("pending", 0)
    n2 = aloop.enqueue_due_reminders()
    pend2 = aloop.reminder_counts().get("pending", 0)
    check("enqueue-idempotent", n2 == 0 and pend1 == pend2,
          f"second enqueue added {n2}, pending {pend1}->{pend2}")

    # a blocked (opted-out) recipient is logged as 'blocked', never 'sent'
    opt = mq("SELECT phone FROM party WHERE marketing_opt_out=1 AND phone IS NOT NULL LIMIT 1")
    if opt:
        before = aloop.communication_counts().get("blocked", 0)
        from web.consent import check_phone
        blocked = check_phone(opt[0]["phone"])
        if blocked:
            pid, sid = aloop.resolve_by_phone(opt[0]["phone"])
            aloop.log_communication(channel="sms", to_addr=opt[0]["phone"], body="x",
                                    status="blocked", party_id=pid, subject_id=sid,
                                    error="opted_out")
        after = aloop.communication_counts().get("blocked", 0)
        check("blocked-send-is-logged", after == before + 1, f"blocked {before}->{after}")

    # recurring reminder rolls forward on mark_sent (one consumed, one created)
    pend = aloop.pending_reminders(limit=1)
    if pend:
        recurring = [r for r in aloop.pending_reminders(limit=500)
                     if r.get("recurring_interval_days")]
        if recurring:
            rid = recurring[0]["id"]
            p_before = aloop.reminder_counts().get("pending", 0)
            aloop.mark_sent(rid)
            counts = aloop.reminder_counts()
            check("recurring-rolls-forward",
                  counts.get("sent", 0) >= 1 and counts.get("pending", 0) == p_before,
                  f"pending {p_before}->{counts.get('pending')}, sent {counts.get('sent')}")

    # attribution returns a well-formed structure
    attr = aloop.attribution(30)
    check("attribution-well-formed",
          set(attr) == {"sent", "converted", "rate", "within_days"},
          f"keys={sorted(attr)}")
    return out


def run_appointments() -> list[dict]:
    """Assert appointment booking + availability (Phase 3).

    The estate had no booking with real availability. These gates prove slot
    generation, conflict detection (no double-booking), cross-clinician
    independence, cancellation freeing a slot, and the Phase-2 reminder hook.
    """
    from datetime import date, timedelta
    from web import appointments as appt
    from web import activation_loop as aloop
    from web.db import reference_date
    out = []

    def check(label, passed, detail=""):
        out.append({"suite": "appointments", "question": label,
                    "category": "scheduling", "passed": bool(passed),
                    "detail": "" if passed else detail, "response_excerpt": detail or "ok"})

    d = date.fromisoformat(reference_date()[:10])
    while d.weekday() != 0:               # next Monday — guaranteed a working day
        d += timedelta(days=1)
    slots = [s for s in appt.day_schedule(1, d) if s["free"]]
    check("slots-generated", len(slots) > 0, f"{len(slots)} free slots on a working day")
    if not slots:
        return out
    slot = slots[0]["start_at"]

    before = appt.appointment_counts().get("scheduled", 0)
    aid = appt.book(1206, 1, slot, reason="Immunisation")
    after = appt.appointment_counts().get("scheduled", 0)
    check("booking-creates-appointment", after == before + 1 and aid > 0)

    try:
        appt.book(1207, 1, slot)
        check("double-booking-refused", False, "SlotTaken not raised")
    except appt.SlotTaken:
        check("double-booking-refused", True)

    try:
        appt.book(1207, 2, slot)          # different clinician, same time
        check("cross-clinician-allowed", True)
    except appt.SlotTaken:
        check("cross-clinician-allowed", False, "same slot on another clinician was refused")

    appt_reminders = aloop.query(
        "SELECT COUNT(*) AS n FROM reminder WHERE category='appointment'")[0]["n"]
    check("booking-queues-reminder", appt_reminders > 0, "no appointment reminder queued")

    appt.set_status(aid, "cancelled")
    free_now = [s for s in appt.day_schedule(1, d) if s["free"] and s["start_at"] == slot]
    check("cancel-frees-slot", len(free_now) == 1, "cancelled slot did not free up")
    return out


def run_billing() -> list[dict]:
    """Assert invoicing + double-entry ledger (Phase 4, lifted from FastERP).

    Proves a fee invoice posts a balanced journal, payments settle it while
    keeping the ledger balanced, re-raising is idempotent, and — the clinic
    twist — the billed party is separable from the treated subject (a minor's
    invoice bills the guardian party, not the child).
    """
    from web import billing
    from web.db import query as mq
    out = []

    def check(label, passed, detail=""):
        out.append({"suite": "billing", "question": label, "category": "revenue_cycle",
                    "passed": bool(passed), "detail": "" if passed else detail,
                    "response_excerpt": detail or "ok"})

    con = mq("SELECT id, subject_id, revenue_vat FROM consultation "
             "WHERE revenue_vat > 0 ORDER BY id LIMIT 1")
    if not con:
        check("has-billable-consultation", False, "no consultation with revenue")
        return out
    cid = con[0]["id"]

    iid = billing.raise_invoice(cid)
    check("raise-invoice", bool(iid), "invoice not raised")
    check("ledger-balanced-after-invoice", billing.gl_balanced())
    check("raise-idempotent", billing.raise_invoice(cid) is None, "re-raise created a duplicate")

    inv = next((i for i in billing.invoices(500) if i["id"] == iid), None)
    if inv:
        billing.record_payment(iid, round(inv["total"] / 2, 2))
        inv2 = next(i for i in billing.invoices(500) if i["id"] == iid)
        check("partial-payment", inv2["status"] == "Partly Paid" and billing.gl_balanced(),
              f"status={inv2['status']}")
        billing.record_payment(iid, inv2["total"] - inv2["paid"])
        inv3 = next(i for i in billing.invoices(500) if i["id"] == iid)
        check("full-payment-settles", inv3["status"] == "Paid" and billing.gl_balanced(),
              f"status={inv3['status']}")

    # payer ≠ subject: a minor's invoice bills the guardian party
    from web.db import reference_date
    minor = mq("SELECT s.id, s.party_id FROM subject s JOIN subject_party_role r "
               "ON r.subject_id=s.id WHERE r.role='guardian' "
               "AND s.date_of_birth > date(?, '-16 years') LIMIT 1", (reference_date(),))
    if minor:
        payer = billing._payer_party(minor[0]["id"])
        check("minor-billed-to-guardian-party", payer == minor[0]["party_id"] and payer is not None,
              f"payer party {payer}")
    return out


def run_specialties() -> list[dict]:
    """Assert the multi-specialty taxonomy: GP + surgical specialties + dental.

    FastClinic is positioned as a multi-specialty clinic operations platform, not
    GP-only. These gates prove the synthetic data and classifier actually produce
    a broad case mix across departments with clean (no 'other') classification.
    """
    from web.db import query, scalar
    from pms.catalog import specialty_of, categorise
    out = []

    def check(label, passed, detail=""):
        out.append({"suite": "specialties", "question": label,
                    "category": "multi_specialty", "passed": bool(passed),
                    "detail": "" if passed else detail, "response_excerpt": detail or "ok"})

    specs = {r["specialty"] for r in query("SELECT DISTINCT specialty FROM item")}
    for needed in ("general_practice", "dental", "orthopaedics", "ophthalmology"):
        check(f"has-specialty:{needed}", needed in specs, f"missing {needed}; have {sorted(specs)}")
    check("broad-specialty-coverage", len(specs) >= 8, f"only {len(specs)} specialties")

    # surgical and dental work is present and material
    surg = scalar("SELECT COUNT(*) FROM item WHERE category='surgery'") or 0
    dent = scalar("SELECT COUNT(*) FROM item WHERE category='dental'") or 0
    check("has-surgery", surg > 50, f"{surg} surgery lines")
    check("has-dental", dent > 50, f"{dent} dental lines")

    # classification is clean — nothing dumped in 'other'
    other = scalar("SELECT COUNT(*) FROM item WHERE category='other'") or 0
    check("no-unclassified-items", other == 0, f"{other} items fell to 'other'")

    # classifier sanity: a known procedure maps to the right specialty/category
    cases = [
        ("Total knee replacement", "orthopaedics", "surgery"),
        ("Cataract surgery", "ophthalmology", "surgery"),
        ("Dental implant", "dental", "dental"),
        ("Root canal treatment", "dental", "dental"),
        ("GP consultation", "general_practice", "consultation"),
    ]
    for name, want_spec, want_cat in cases:
        gs, gc = specialty_of(name), categorise(name)
        check(f"classify:{name}", gs == want_spec and gc == want_cat,
              f"got specialty={gs} category={gc}, want {want_spec}/{want_cat}")

    # the 'appointment' false-positive regression: must NOT be ENT
    check("no-ent-false-positive",
          specialty_of("Urgent same-day appointment") != "ent",
          "'appointment' wrongly matched ENT")
    return out


def run_fhir() -> list[dict]:
    """Assert Clinic OS Phase 5a/5b: R4 shaping + offline NHS adapter."""
    from web import fhir
    from web.adapters.base import AdapterNotAvailable
    from web.adapters.nhs import live
    from web.adapters.nhs.identifiers import verify_nhs_number
    from web.adapters.registry import get_adapter
    from web.db import query_one, reference_date

    out = []

    def check(label, passed, detail=""):
        out.append({
            "suite": "fhir", "question": label, "category": "interop",
            "passed": bool(passed), "detail": "" if passed else detail,
            "response_excerpt": detail or "ok",
        })

    cap = fhir.capability_statement()
    check("capability-is-r4", cap.get("fhirVersion") == "4.0.1", cap.get("fhirVersion"))

    adult = query_one(
        "SELECT id FROM subject s JOIN subject_party_role r ON r.subject_id=s.id "
        "WHERE r.role='self' AND s.deceased_at IS NULL ORDER BY s.id LIMIT 1"
    )
    if not adult:
        check("has-adult-subject", False, "no adult subject")
        return out
    resources = fhir.export_subject(adult["id"])
    kinds = {row["resourceType"] for row in resources}
    check("adult-has-patient", "Patient" in kinds)
    check("adult-has-no-related-person", "RelatedPerson" not in kinds)
    patient = next(row for row in resources if row["resourceType"] == "Patient")
    check("patient-id-matches-subject", patient["id"] == str(adult["id"]))

    minor = query_one(
        "SELECT s.id FROM subject s JOIN subject_party_role r ON r.subject_id=s.id "
        "WHERE r.role='guardian' AND s.date_of_birth > date(?, '-16 years') "
        "ORDER BY s.id LIMIT 1",
        (reference_date(),),
    )
    if minor:
        mres = fhir.export_subject(minor["id"])
        related = [row for row in mres if row["resourceType"] == "RelatedPerson"]
        people = [row for row in mres if row["resourceType"] == "Person"]
        check("minor-has-related-person", len(related) >= 1, f"related={len(related)}")
        check("minor-has-person-linkage", len(people) >= 1, f"person={len(people)}")
        if related:
            check(
                "related-person-patient-is-1-1",
                related[0]["patient"]["reference"] == f"Patient/{minor['id']}",
            )
    else:
        check("has-minor-subject", False, "no guardian-linked minor")

    outcome = fhir.validate_resource(patient)
    check(
        "exported-patient-validates",
        all(issue.get("severity") not in {"error", "fatal"} for issue in outcome["issue"]),
    )
    mapped = fhir.import_resource(patient)
    check("import-patient-apply-safe", mapped.get("apply_safe") is True)

    known_valid = verify_nhs_number("943 476 5919")
    check("nhs-number-modulus-11-accepts-known-valid", known_valid["valid"] is True)
    check("nhs-number-rejects-short", verify_nhs_number("123")["valid"] is False)

    nhs = get_adapter("GB")
    uk = nhs.export_subject(adult["id"], release="r4")
    uk_patient = next(row for row in uk if row["resourceType"] == "Patient")
    check(
        "uk-core-profile-on-patient",
        any("UKCore-Patient" in p for p in uk_patient.get("meta", {}).get("profile", [])),
    )
    stu3 = nhs.export_subject(adult["id"], release="stu3")
    stu3_patient = next(row for row in stu3 if row["resourceType"] == "Patient")
    check(
        "gpconnect-stu3-profile-on-patient",
        any("CareConnect-GPC-Patient-1" in p for p in stu3_patient.get("meta", {}).get("profile", [])),
    )
    try:
        live.pds_lookup("9434765919")
        check("pds-stays-gated", False, "PDS call did not raise")
    except AdapterNotAvailable:
        check("pds-stays-gated", True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not SYNTH.exists():
        print(f"ERROR: synthetic export not found at {SYNTH}", file=sys.stderr)
        return 2
    db_counts = build(str(SYNTH), str(DB_PATH))

    cases = (run_shortcuts() + run_chat() + run_routes() + run_coverage()
             + run_consent() + run_model() + run_loop() + run_appointments()
             + run_billing() + run_specialties() + run_fhir())

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
