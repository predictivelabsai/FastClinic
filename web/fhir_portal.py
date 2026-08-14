"""Patient-owned read surface for imported FHIR R4 document Bundles."""
from __future__ import annotations

import json
import re
from html import escape, unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from fasthtml.common import A, Div, H3, H4, NotStr, P, Span

from web import db
from web.dashboards import _page_title, _table
from web.fhir.xml import FHIR_XML_MEDIA_TYPE, bundle_to_xml


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


_ALLOWED_TAGS = {
    "a", "b", "blockquote", "br", "caption", "code", "dd", "div", "dl",
    "dt", "em", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "li",
    "ol", "p", "s", "span", "strong", "sub", "sup", "table", "tbody",
    "td", "tfoot", "th", "thead", "tr", "u", "ul",
}
_DROP_CONTENT = {"base", "form", "iframe", "link", "object", "script", "style"}
_VOID_TAGS = {"br", "hr"}


def _safe_href(value: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    parsed = urlsplit(value)
    if value.startswith("#") or parsed.scheme.lower() in {"http", "https", "mailto"}:
        return value
    return None


def _plain_note_html(value: str) -> str:
    """Turn preformatted episode text into readable, escaped HTML blocks."""
    lines = [line.strip() for line in value.replace("\r\n", "\n").split("\n")]
    output = ['<div class="episode-note">']
    in_list = False
    for line in lines:
        if not line:
            if in_list:
                output.append("</ul>")
                in_list = False
            continue
        bullet = re.match(r"^[-*•]\s+(.+)$", line)
        if bullet:
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append(f"<li>{escape(bullet.group(1))}</li>")
            continue
        if in_list:
            output.append("</ul>")
            in_list = False
        if (line.endswith(":") and len(line) <= 80) or (line.isupper() and len(line) <= 80):
            output.append(f"<h4>{escape(line.rstrip(':'))}</h4>")
            continue
        labelled = re.match(r"^([^:]{1,60}:)\s+(.+)$", line)
        if labelled:
            output.append(
                f"<p><strong>{escape(labelled.group(1))}</strong> {escape(labelled.group(2))}</p>"
            )
            continue
        output.append(f"<p>{escape(line)}</p>")
    if in_list:
        output.append("</ul>")
    output.append("</div>")
    return "".join(output)


class _NarrativeSanitizer(HTMLParser):
    """Allow basic FHIR Narrative XHTML while removing active content."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.open_tags: list[str] = []
        self.skip_depth = 0
        self.pre_depth = 0
        self.pre_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self.skip_depth:
            self.skip_depth += 1
            return
        if tag in _DROP_CONTENT:
            self.skip_depth = 1
            return
        if self.pre_depth:
            self.pre_depth += 1
            if tag in {"br", "div", "li", "p", "tr"}:
                self.pre_text.append("\n")
            return
        if tag == "pre":
            self.pre_depth = 1
            self.pre_text = []
            return
        if tag not in _ALLOWED_TAGS:
            return
        safe_attrs: list[str] = []
        attr_map = {str(name).lower(): value or "" for name, value in attrs}
        if tag == "a":
            href = _safe_href(attr_map.get("href", ""))
            if href:
                safe_attrs.append(f'href="{escape(href, quote=True)}"')
                safe_attrs.append('rel="noopener noreferrer"')
            if attr_map.get("title"):
                safe_attrs.append(f'title="{escape(attr_map["title"], quote=True)}"')
        elif tag in {"td", "th"}:
            for name in ("colspan", "rowspan"):
                raw = attr_map.get(name, "")
                if raw.isdigit() and 0 < int(raw) <= 100:
                    safe_attrs.append(f'{name}="{raw}"')
        rendered_attrs = (" " + " ".join(safe_attrs)) if safe_attrs else ""
        self.output.append(f"<{tag}{rendered_attrs}>")
        if tag not in _VOID_TAGS:
            self.open_tags.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if self.pre_depth:
            self.pre_depth -= 1
            if self.pre_depth == 0:
                self.output.append(_plain_note_html("".join(self.pre_text)))
                self.pre_text = []
            elif tag in {"div", "li", "p", "tr"}:
                self.pre_text.append("\n")
            return
        if tag in _ALLOWED_TAGS and tag not in _VOID_TAGS and self.open_tags:
            if self.open_tags[-1] == tag:
                self.output.append(f"</{tag}>")
                self.open_tags.pop()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.pre_depth:
            self.pre_text.append(data)
        else:
            self.output.append(escape(data))

    def html(self) -> str:
        if self.pre_depth:
            self.output.append(_plain_note_html("".join(self.pre_text)))
            self.pre_depth = 0
        while self.open_tags:
            self.output.append(f"</{self.open_tags.pop()}>")
        return "".join(self.output)


def _sanitize_narrative(value: str) -> str:
    sanitizer = _NarrativeSanitizer()
    sanitizer.feed(value or "")
    sanitizer.close()
    return sanitizer.html()


def _narrative_sections(payload: dict[str, Any]) -> list[tuple[str, str]]:
    entries = payload.get("entry") or []
    composition = next(
        (entry.get("resource") for entry in entries
         if (entry.get("resource") or {}).get("resourceType") == "Composition"),
        {},
    )
    sections = composition.get("section") or []
    if isinstance(sections, dict):
        sections = [sections]
    rendered: list[tuple[str, str]] = []
    for index, section in enumerate(sections, 1):
        raw = ((section.get("text") or {}).get("div") or "")
        if raw.strip():
            rendered.append((section.get("title") or f"Clinical narrative {index}", _sanitize_narrative(raw)))
    return rendered


def xml_for_email(email: str, bundle_id: str) -> bytes | None:
    """Return standards-shaped FHIR XML only when the account owns the record."""
    record = record_for_email(email, bundle_id)
    if not record:
        return None
    payload = record["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return bundle_to_xml(payload)


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
    sections = _narrative_sections(payload)
    filename = re.sub(r"[^A-Za-z0-9._-]", "-", bundle_id) + ".fhir.xml"
    actions = Div(
        A("Back to my records", href="/my-records", cls="btn"),
        A("Download FHIR XML", href=f"/my-records/{bundle_id}/download",
          download=filename, cls="btn primary"),
        cls="record-actions",
    )
    return Div(
        _page_title(record.get("title") or "Clinical document", str(record.get("document_date") or "")[:10],
                    actions=actions),
        *(
            Div(
                Div(H3(title), cls="card-header"),
                Div(NotStr(html), cls="clinical-narrative"),
                cls="card",
            )
            for title, html in sections
        ),
        *(() if sections else (Div(H4("Clinical narrative"), P("No narrative was supplied."), cls="card"),)),
    )
