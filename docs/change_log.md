# FastClinic change log

## 0.3.0 — 2026-08-14

- Added a Lithuanian E. sveikata adapter sandbox for ESPBI E025/E027/E063
  projections, IPR appointments, and eLab FHIR R5 E200 transaction Bundles.
- Added an Estonian TEHIK/TIS adapter sandbox for CDA-shaped outpatient
  documents, MPI FHIR R5 previews, and X-Road request context.
- Added a PostgreSQL/SQLite-portable, idempotent national exchange ledger with
  mock receipts, reconciliation, payload hashes, actor context, and API audit.
- Added privacy-safe national identifier checks, fail-closed live configuration,
  synthetic fixtures, public validation previews, and token-gated submissions.
- Documented institutional onboarding, access/licensing boundaries, production
  limitations, deployment controls, and the required official validation work.

## 0.2.1 — 2026-08-14

Release checkpoint for the FHIR patient-record integration.

- Added opt-in live MedBackend patient OAuth, JWKS, and GraphQL integration checks.
- Verified MedBackend project configuration and signing-key connectivity without exposing credentials or tokens.
- Documented that patient API access requires an interactive authorization-code grant; no clinical records are mirrored without an authorized patient token.
- Completed translation catalogues for the patient health-record portal.
- Passed the complete automated suite: 57 tests, 38 localization subtests, and four safely skipped opt-in live checks.

## 0.2.0 — 2026-08-14

- Added lossless, replay-safe ingestion of FHIR R4 document Bundles from JSON, XML, and NDJSON into PostgreSQL.
- Imported Terviseportaal clinical documents into private PostgreSQL FHIR tables while keeping source exports and secrets out of Git.
- Added patient ownership mapping and the authenticated **My Health Records** portal.
- Added FHIR R4 resource assembly, validation, import mapping, CapabilityStatement, and patient export surfaces.
- Added PostgreSQL-backed operational storage and migration tooling for accounts, chat, appointments, reminders, billing, payments, and audit state.
- Added the NHS adapter boundary with UK Core R4 and GP Connect STU3 translation support.
- Added the configurable MedBackend integration plan and environment contract; live synchronization remains disabled pending OAuth authorization and final write-schema validation.
