# FastClinic change log

## 0.4.0 — 2026-08-15

- Added five role-specific workspaces with canonical Administrator,
  Practitioner, Receptionist, Billing, and Patient roles.
- Added an audited, session-only **Viewing as** selector for administrators;
  previewing a role never changes the administrator's stored PostgreSQL role.
- Added capability definitions and patient/practitioner record-scope checks in
  addition to navigation and route permissions.
- Added accessible collapse/expand controls to primary cards and navigation
  groups, with role/page-specific presentation state and print-safe behavior.
- Made conversational booking the patient portal default: a patient-safe
  LangGraph workflow interprets requests, reads live availability, proposes a
  slot, and requires explicit confirmation before creating an appointment.
- Added a three-pane booking workspace with chat in the centre, live calendar
  context on the right, and a Classical calendar alternative.
- Grounded booking text-to-SQL in `sql/schema.json` using the FastBI read-only
  pattern, with approved scheduling tables, bounded results, and sensitive-field,
  DML/DDL, multi-statement, wildcard, and dangerous-function rejection.
- Added practitioner availability rules and exceptions, locations, rooms,
  booking policy, temporary holds, participants, notification queue records,
  appointment status history, and record-scoped patient cancellation backed by
  PostgreSQL/SQLite-portable operational tables.
- Added conflict-safe room booking, timezone-normalized UTC timestamps, and
  practitioner day/week/agenda schedule modes.
- Added same-origin protection for browser mutations while preserving the
  separately authenticated service API boundary.
- Added FastAPI 1.5 patient-mobile endpoints for MedBackend OAuth/PKCE identity,
  app bootstrap, live availability, conversational and Classical booking, own
  appointment lifecycle, and owned FHIR R4 JSON/XML records.
- Added `docs/mobile_app_api.md` with native token storage, error handling,
  security, booking state, and deployment guidance.
- Added same-container host routing for `api.fastclinic.dev`, exposing Swagger
  at `/docs`, ReDoc, OpenAPI, and `/v1/health`; Docker now health-checks the API
  hostname path directly.
- Expanded RBAC, booking-agent, availability, record-scope, role-preview, and
  migration tests and refreshed all supported locale catalogues.

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
