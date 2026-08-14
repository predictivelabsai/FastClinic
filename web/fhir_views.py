"""Admin view for the FHIR R4 read surface and the NHS adapter."""
from __future__ import annotations

import json

from fasthtml.common import A, Div, Form, H3, Input, NotStr, P, Pre, Span

from web.dashboards import _page_title, _table
from web.i18n import t


def fhir_admin_view(subject_id: int | None = None, nhs_number: str = "", release: str = "r4"):
    from web import fhir
    from web.adapters.nhs.identifiers import verify_nhs_number
    from web.adapters.nhs.live import missing_live_config
    from web.adapters.registry import get_adapter
    from web.db import db_exists, query_one
    from web.fhir.assemble import as_bundle

    capability = fhir.capability_statement()
    resource_count = len(capability["rest"][0]["resource"])
    adapter = get_adapter("GB")
    status = adapter.status()
    live = missing_live_config()

    sample = (
        query_one(
            "SELECT id, official_name FROM subject WHERE deceased_at IS NULL ORDER BY id LIMIT 1"
        )
        if db_exists()
        else None
    )
    sample_id = int(subject_id or (sample["id"] if sample else 1))

    preview = None
    preview_error = None
    try:
        if release in {"stu3", "gpc", "gpconnect"}:
            preview = as_bundle(adapter.export_subject(sample_id, release="stu3"))
        elif release in {"uk", "ukcore"}:
            preview = as_bundle(adapter.export_subject(sample_id, release="r4"))
        else:
            preview = fhir.bundle_subject(sample_id, include_ops=False)
    except fhir.NotFound as exc:
        preview_error = str(exc)
    except Exception as exc:  # noqa: BLE001 — surface mapping errors in the admin pane
        preview_error = str(exc)

    nhs_result = verify_nhs_number(nhs_number) if nhs_number else None

    return Div(
        _page_title(
            "FHIR R4",
            "Standards-shaped read of the clinic record",
            actions=A(t("Open API docs"), href="/api/docs", cls="btn"),
        ),
        Div(
            Div(H3("CapabilityStatement"), cls="card-header"),
            P(t(
                "Vanilla FHIR R4 projection of the synthetic clinic record. "
                "National identifier systems and profiles are applied by country adapters."
            )),
            _table(
                ["Field", "Value"],
                [
                    ["FHIR version", capability["fhirVersion"]],
                    ["Resources", resource_count],
                    ["Patient $everything", "/api/v1/fhir/Patient/{id}/$everything"],
                    ["Validate", "POST /api/v1/fhir/$validate"],
                ],
            ),
            cls="card",
        ),
        Div(
            Div(H3(t("Export a patient")), cls="card-header"),
            Form(
                Input(
                    type="number", name="subject_id", value=sample_id,
                    placeholder=t("Patient ID"), min=1,
                    style="padding:8px 12px;border:1px solid var(--border);border-radius:8px;width:140px;",
                ),
                Input(type="hidden", name="release", value=release or "r4"),
                Input(type="submit", value=t("Preview"), cls="btn primary"),
                method="get", action="/admin/fhir",
                style="display:flex;gap:8px;align-items:center;",
            ),
            P(
                A("R4", href=f"/admin/fhir?subject_id={sample_id}&release=r4"),
                NotStr(" · "),
                A("UK Core", href=f"/admin/fhir?subject_id={sample_id}&release=ukcore"),
                NotStr(" · "),
                A("GP Connect STU3", href=f"/admin/fhir?subject_id={sample_id}&release=stu3"),
                style="margin-top:10px;",
            ),
            P(preview_error, style="color:var(--danger);") if preview_error else None,
            Pre(
                json.dumps(preview, indent=2, ensure_ascii=False)[:12000],
                style="max-height:480px;overflow:auto;font-size:12px;background:var(--surface-2);padding:12px;border-radius:8px;",
            ) if preview else None,
            cls="card",
        ),
        Div(
            Div(H3(t("NHS adapter")), cls="card-header"),
            P(t("NHS Number check-digit, UK Core R4 mapping, and GP Connect STU3 translation are available offline.")),
            _table(
                ["Surface", "Status"],
                [[name.replace("_", " "), value] for name, value in status["surfaces"].items()],
            ),
            Form(
                Input(
                    type="text", name="nhs_number", value=nhs_number,
                    placeholder="9434765919",
                    style="padding:8px 12px;border:1px solid var(--border);border-radius:8px;width:180px;",
                ),
                Input(type="hidden", name="subject_id", value=sample_id),
                Input(type="hidden", name="release", value=release or "r4"),
                Input(type="submit", value=t("Check"), cls="btn"),
                method="get", action="/admin/fhir",
                style="display:flex;gap:8px;align-items:center;margin-top:12px;",
            ),
            P(
                Span(
                    "valid" if nhs_result["valid"] else "invalid",
                    cls=f"status-pill {'ok' if nhs_result['valid'] else 'cancelled'}",
                ),
                f" {nhs_result.get('formatted') or nhs_number} · {nhs_result.get('reason') or 'modulus-11'}",
            ) if nhs_result else None,
            P(
                t("Live PDS / GP Connect is not connected"),
                f" · PDS missing {', '.join(live['pds']) or '—'}; "
                f"GP Connect missing {', '.join(live['gpconnect']) or '—'}.",
                style="color:var(--text-mute);font-size:13px;margin-top:10px;",
            ),
            cls="card",
        ),
    )
