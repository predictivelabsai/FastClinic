#!/usr/bin/env python3
"""Grant one FastClinic login access to one imported FHIR patient identity."""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.import_fhir_r4 import DDL, SCHEMA_RE, _connect

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def link(email: str, database_url: str, schema: str) -> dict[str, int]:
    email = email.strip().lower()
    with _connect(database_url, schema) as connection:
        with connection.cursor() as cursor:
            cursor.execute(DDL)
            cursor.execute(
                """SELECT DISTINCT patient_identifier_system,patient_identifier_value
                   FROM fhir_document_bundle
                   WHERE patient_identifier_system IS NOT NULL
                     AND patient_identifier_value IS NOT NULL"""
            )
            identities = cursor.fetchall()
            if len(identities) != 1:
                raise RuntimeError(
                    f"Expected exactly one imported patient identity, found {len(identities)}; "
                    "specify identity support before linking"
                )
            system, value = identities[0]
            cursor.execute(
                """INSERT INTO fhir_patient_access(
                     account_email,patient_identifier_system,patient_identifier_value,access_role
                   ) VALUES(%s,%s,%s,'owner')
                   ON CONFLICT(account_email,patient_identifier_system,patient_identifier_value)
                   DO UPDATE SET access_role='owner'""",
                (email, system, value),
            )
    return {"linked_accounts": 1, "patient_identities": 1}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--database-url-env", default="DATABASE_URL_PROD")
    parser.add_argument("--schema", default=os.getenv("FASTCLINIC_DB_SCHEMA", "fast_clinic"))
    args = parser.parse_args()
    if not EMAIL_RE.fullmatch(args.email.strip().lower()):
        parser.error("--email must be valid")
    if not SCHEMA_RE.fullmatch(args.schema):
        parser.error("--schema must be a PostgreSQL identifier")
    database_url = os.getenv(args.database_url_env)
    if not database_url:
        parser.error(f"{args.database_url_env} is not set")
    try:
        result = link(args.email, database_url, args.schema)
    except RuntimeError as exc:
        print(f"FHIR patient link failed: {exc}", file=sys.stderr)
        return 1
    import json
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

