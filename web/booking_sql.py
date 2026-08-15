"""Schema-grounded, read-only text-to-SQL for booking context.

Adapted from FastBI's guarded SQL Lab pattern. Generated SQL is never used for
booking mutations and cannot read patient identity, clinical, authentication,
or billing fields.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from web import activation_loop as ops

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "sql" / "schema.json"

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|"
    r"reindex|copy|grant|revoke|truncate|execute|call)\b", re.IGNORECASE,
)
_SENSITIVE = re.compile(r"\b(subject_id|party_id|password|email|phone|reason)\b", re.IGNORECASE)
_DANGEROUS_FUNCTION = re.compile(
    r"\b(pg_sleep|sleep|readfile|writefile|load_extension|dblink|lo_import|lo_export)\b",
    re.IGNORECASE,
)


class BookingSQLError(ValueError):
    pass


def schema_document() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def schema_prompt() -> str:
    document = schema_document()
    booking = document["fastclinic_booking_context"]
    lines = [
        "FastClinic booking query schema (read-only):",
        json.dumps(booking["tables"], ensure_ascii=False, indent=2),
        "Semantic treatment catalogue from the ingested source schema (context only; do not query these tables):",
    ]
    for name in ("treatment_type", "treatment", "hospital_treatment_type"):
        if name in document.get("tables", {}):
            lines.append(f"{name}: {json.dumps(document['tables'][name], ensure_ascii=False)}")
    return "\n".join(lines)


def _extract_sql(text: str) -> str:
    value = (text or "").strip()
    fenced = re.search(r"```(?:sql)?\s*(.+?)```", value, re.IGNORECASE | re.DOTALL)
    if fenced:
        value = fenced.group(1).strip()
    match = re.search(r"((?:select|with)\b.+)", value, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip().rstrip(";") if match else ""


def validate_sql(sql: str, limit: int = 50) -> str:
    value = (sql or "").strip().rstrip(";")
    if not value or not re.match(r"^(select|with)\b", value, re.IGNORECASE):
        raise BookingSQLError("Only SELECT/WITH queries are allowed")
    if ";" in value or "--" in value or "/*" in value or _FORBIDDEN.search(value):
        raise BookingSQLError("Only one read-only query is allowed")
    if _SENSITIVE.search(value) or _DANGEROUS_FUNCTION.search(value) or re.search(r"(^|[\s,(])(?:\w+\.)?\*([\s,)]|$)", value):
        raise BookingSQLError("Sensitive patient fields are not available to booking SQL")

    allowed = set(schema_document()["fastclinic_booking_context"]["allowed_tables"])
    ctes = set(re.findall(r"(?:with|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s+as\s*\(", value, re.I))
    referenced = set(re.findall(r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)", value, re.I))
    disallowed = referenced - allowed - ctes
    if disallowed:
        raise BookingSQLError(f"Booking SQL referenced unavailable tables: {', '.join(sorted(disallowed))}")
    if not referenced:
        raise BookingSQLError("Booking SQL must query an approved table")
    maximum = max(1, min(limit, 100))
    limit_match = re.search(r"\blimit\s+(\d+)\b", value, re.IGNORECASE)
    if limit_match:
        if int(limit_match.group(1)) > maximum:
            value = (value[:limit_match.start(1)] + str(maximum)
                     + value[limit_match.end(1):])
    elif re.search(r"\blimit\b", value, re.IGNORECASE):
        raise BookingSQLError("LIMIT must be a fixed integer")
    else:
        value += f"\nLIMIT {maximum}"
    return value


def run_sql(sql: str, limit: int = 50) -> list[dict]:
    return ops.query(validate_sql(sql, limit))


def text_to_sql(question: str) -> str:
    from graph.clinic_assistant import make_model

    model = make_model()
    if model is None:
        raise BookingSQLError("No model provider is configured")
    system = (
        "You write one portable PostgreSQL/SQLite read-only query for clinic booking. "
        "Output SQL only, without markdown or a semicolon. Use only the approved tables. "
        "Never select patient identifiers, contact details, free-text reasons, clinical data, "
        "authentication data, or billing data. Prefer appointment_type for treatment matching "
        "and availability rules for practitioner/day questions.\n\n" + schema_prompt()
    )
    response = model.invoke([
        {"role": "system", "content": system},
        {"role": "user", "content": (question or "")[:500]},
    ])
    content = getattr(response, "content", "")
    if isinstance(content, list):
        content = "".join(item.get("text", "") if isinstance(item, dict) else str(item)
                          for item in content)
    sql = _extract_sql(str(content))
    return validate_sql(sql)


def ask(question: str) -> dict[str, Any]:
    sql = text_to_sql(question)
    return {"sql": sql, "rows": run_sql(sql)}
