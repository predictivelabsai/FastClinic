"""Patient-owned read surface for imported FHIR R4 document Bundles."""
from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

from fasthtml.common import A, Div, H3, P, Pre, Span

from web import db
from web.dashboards import _page_title, _table


def _email(value: str) -> str:
    return (value or "").strip().lower()


def records_for_email(email: str) -> list[dict]:
    return db.query(
        """SELECT b.bundle_id,b.document_date,b.title,b.source_format
           FROM fhir_document_bundle b
           JOIN fhir_patient_access a
             ON a.patient_identifier_system=b.patient_identifier_system
            AND a.patient_identifier_value=b.patient_identifier_value
          WHERE a.account_email=?
          ORDER BY b.document_date DESC NULLS LAST,b.imported_at DESC""",
        (_email(email),),
    )


def record_for_email(email: str, bundle_id: str) -> dict | None:
    return db.query_one(
        """SELECT b.bundle_id,b.document_date,b.title,b.source_format,b.payload
           FROM fhir_document_bundle b
           JOIN fhir_patient_access a
             ON a.patient_identifier_system=b.patient_identifier_system
            AND a.patient_identifier_value=b.patient_identifier_value
          WHERE a.account_email=? AND b.bundle_id=?""",
        (_email(email), bundle_id),
    )


def _narrative(payload: dict[str, Any]) -> str:
    entries = payload.get("entry") or []
    composition = next(
        (entry.get("resource") for entry in entries
         if (entry.get("resource") or {}).get("resourceType") == "Composition"),
        {},
    )
    sections = composition.get("section") or []
    if isinstance(sections, dict):
        sections = [sections]
    values = []
    for section in sections:
        div = ((section.get("text") or {}).get("div") or "")
        plain = re.sub(r"<[^>]+>", "", div)
        if plain.strip():
            values.append(unescape(plain).strip())
    return "\n\n".join(values)


def records_view(email: str):
    records = records_for_email(email)
    rows = [
        [str(row.get("document_date") or "")[:10], row.get("title") or "Clinical document",
         row.get("source_format", "").upper(), A("Open", href=f"/my-records/{row['bundle_id']}")]
        for row in records
    ]
    return Div(
        _page_title("My health records", "FHIR R4 documents imported from Terviseportaal"),
        Div(
            Div(H3("Imported clinical documents"), Span(f"{len(rows)} records", cls="status-pill ok"), cls="card-header"),
            _table(["Date", "Document", "Format", ""], rows) if rows else P("No health records are linked to this account."),
            cls="card",
        ),
    )


def record_view(email: str, bundle_id: str):
    record = record_for_email(email, bundle_id)
    if not record:
        return None
    payload = record["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    narrative = _narrative(payload)
    return Div(
        _page_title(record.get("title") or "Clinical document", str(record.get("document_date") or "")[:10],
                    actions=A("Back to my records", href="/my-records", cls="btn")),
        Div(Div(H3("Clinical narrative"), cls="card-header"),
            Pre(narrative or "No narrative was supplied.", style="white-space:pre-wrap;max-height:65vh;overflow:auto;"), cls="card"),
    )

