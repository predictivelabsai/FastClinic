#!/usr/bin/env python3
"""Validate and ingest FHIR R4 document Bundles into PostgreSQL."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.fhir.ingress import FHIRIngressError, read_bundles

SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DDL = """
CREATE TABLE IF NOT EXISTS fhir_import_batch (
  id BIGSERIAL PRIMARY KEY, source_name TEXT NOT NULL, status TEXT NOT NULL,
  document_count INTEGER NOT NULL DEFAULT 0, resource_count INTEGER NOT NULL DEFAULT 0,
  skipped_count INTEGER NOT NULL DEFAULT 0, started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS fhir_document_bundle (
  bundle_id TEXT PRIMARY KEY, canonical_sha256 CHAR(64) NOT NULL UNIQUE,
  fhir_version TEXT NOT NULL, composition_id TEXT, patient_id TEXT, encounter_id TEXT,
  patient_identifier_system TEXT, patient_identifier_value TEXT, document_date TIMESTAMPTZ,
  title TEXT, source_format TEXT NOT NULL, source_name TEXT NOT NULL,
  payload JSONB NOT NULL, imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS fhir_resource (
  bundle_id TEXT NOT NULL REFERENCES fhir_document_bundle(bundle_id) ON DELETE CASCADE,
  resource_type TEXT NOT NULL, resource_id TEXT NOT NULL, full_url TEXT,
  canonical_sha256 CHAR(64) NOT NULL, payload JSONB NOT NULL,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (bundle_id, resource_type, resource_id)
);
CREATE TABLE IF NOT EXISTS fhir_patient_access (
  account_email TEXT NOT NULL, patient_identifier_system TEXT NOT NULL,
  patient_identifier_value TEXT NOT NULL, access_role TEXT NOT NULL DEFAULT 'owner',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (account_email, patient_identifier_system, patient_identifier_value)
);
CREATE INDEX IF NOT EXISTS fhir_patient_access_identifier_idx
  ON fhir_patient_access(patient_identifier_system, patient_identifier_value);
CREATE INDEX IF NOT EXISTS fhir_bundle_patient_identifier_idx
  ON fhir_document_bundle(patient_identifier_system, patient_identifier_value);
CREATE INDEX IF NOT EXISTS fhir_bundle_document_date_idx ON fhir_document_bundle(document_date);
CREATE INDEX IF NOT EXISTS fhir_resource_type_idx ON fhir_resource(resource_type, resource_id);
"""


def _connect(url: str, schema: str):
    import psycopg2
    return psycopg2.connect(url, connect_timeout=10, options=f"-c search_path={schema}")


def ingest(source: Path, database_url: str, schema: str) -> dict[str, int]:
    from psycopg2.extras import Json
    bundles = read_bundles(source)
    inserted = skipped = resources = 0
    with _connect(database_url, schema) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"fastclinic:fhir:{schema}",))
            cursor.execute(DDL)
            cursor.execute(
                "INSERT INTO fhir_import_batch(source_name,status) VALUES(%s,'running') RETURNING id",
                (source.name,),
            )
            batch_id = cursor.fetchone()[0]
            for bundle in bundles:
                cursor.execute(
                    "SELECT canonical_sha256 FROM fhir_document_bundle WHERE bundle_id=%s",
                    (bundle.bundle_id,),
                )
                existing = cursor.fetchone()
                if existing:
                    if existing[0].strip() != bundle.canonical_sha256:
                        raise FHIRIngressError(
                            f"Bundle/{bundle.bundle_id} already exists with different content; no data was changed"
                        )
                    skipped += 1
                    continue
                cursor.execute(
                    """INSERT INTO fhir_document_bundle(
                      bundle_id,canonical_sha256,fhir_version,composition_id,patient_id,encounter_id,
                      patient_identifier_system,patient_identifier_value,document_date,title,
                      source_format,source_name,payload
                    ) VALUES(%s,%s,'4.0.1',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (bundle.bundle_id, bundle.canonical_sha256, bundle.composition_id,
                     bundle.patient_id, bundle.encounter_id, bundle.patient_identifier_system,
                     bundle.patient_identifier_value, bundle.document_date, bundle.title,
                     bundle.source_format, bundle.source_name, Json(bundle.payload)),
                )
                for full_url, resource in bundle.resources:
                    canonical = json.dumps(resource, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    import hashlib
                    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                    cursor.execute(
                        """INSERT INTO fhir_resource(
                          bundle_id,resource_type,resource_id,full_url,canonical_sha256,payload
                        ) VALUES(%s,%s,%s,%s,%s,%s)""",
                        (bundle.bundle_id, resource["resourceType"], str(resource["id"]),
                         full_url, digest, Json(resource)),
                    )
                    resources += 1
                inserted += 1
            cursor.execute(
                """UPDATE fhir_import_batch SET status='completed',document_count=%s,
                resource_count=%s,skipped_count=%s,completed_at=NOW() WHERE id=%s""",
                (inserted, resources, skipped, batch_id),
            )
    return {"validated": len(bundles), "inserted": inserted, "skipped": skipped, "resources_inserted": resources}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", default=Path("data/private-health-records/fhir-r4"))
    parser.add_argument("--database-url-env", default="DATABASE_URL_PROD")
    parser.add_argument("--schema", default=os.getenv("FASTCLINIC_DB_SCHEMA", "fast_clinic"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not SCHEMA_RE.fullmatch(args.schema):
        parser.error("--schema must be a PostgreSQL identifier")
    try:
        bundles = read_bundles(args.source)
        if args.dry_run:
            result = {"validated": len(bundles), "resources": sum(len(b.resources) for b in bundles), "written": 0}
        else:
            database_url = os.getenv(args.database_url_env)
            if not database_url:
                parser.error(f"{args.database_url_env} is not set")
            result = ingest(args.source, database_url, args.schema)
    except (FHIRIngressError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FHIR import failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
