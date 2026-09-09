# FastClinic change log

## 0.8.1 — 2026-09-09

- Geocode every newly scraped clinic address in the same collection task and drain transport-interrupted lookups on the next worker tick, removing the persistent **Address captured** state.
- Add localized Baltic/Romanian address cleanup, clinic/venue-aware matching, a cached Photon fallback and source-adjacent official map-link coordinates while retaining country, settlement, street and house validation.
- Repair the live market-map backlog to 71 mapped branches with no pending or review-only locations.

Validation: 182 tests and 38 subtests passed, with 35 opt-in/live checks skipped.

## 0.8.0 — 2026-09-09

- Expand Competition from four markets to all 30 EEA countries through one data-driven country registry, local-language search packs, contact routes, currencies and country dashboards.
- Add a durable discovery-candidate review queue that retains Exa leads before strict evidence extraction; staff can review, reject, reopen or promote an official URL into the authenticated watchlist.
- Add ordered country campaigns targeting at least 10 verified private clinics per market, with 450 broad discovery queries, bounded ownership checks and visible country-level progress.
- Import the public My Medical Gateway hospital catalogue as unverified seeds, while keeping aggregator profiles separate from official clinic domains until a staff review.
- Add a versioned specialty → treatment-family taxonomy based on the public MMG navigation hierarchy and extended for wellness, diagnostics, oncology, dental, dermatology, bariatric care, rehabilitation, primary care and mental health.
- Queue direct deep scraping as soon as a reviewed candidate is promoted; manual URLs and Exa-discovered pages continue through the same evidence, address and price-history pipeline.
- Make operational schema setup process-local and database-aware so the larger dashboard no longer replays all market DDL on every request.

Validation: 173 tests and 38 subtests passed, with 35 opt-in/live checks skipped. Authenticated Chrome checks covered the 30-country selector, Romania candidate review and promotion, immediate direct-scrape queuing, country dashboard navigation, zero Plotly card overlap and zero console errors.

## 0.7.0 — 2026-09-09

- Add country-specific Competition dashboards for Lithuania, Latvia, Estonia and Romania, with compact country switching and country-scoped charts, evidence and tables.
- Replace aggregate clinic drill-downs with focused clinic pages containing only that provider's addresses, source evidence and observed tariffs plus a back-to-dashboard link.
- Add an independent official-domain address crawler that follows multilingual contact/location links and uses xAI only to structure verbatim address-and-city evidence.
- Rotate bounded address repairs through providers without location rows, preserve evidence URLs, capture long-page footers, retry high-signal individual pages and suppress translated duplicate branches.
- Add **Deep scrape all active** for the authenticated curated watchlist, compact row actions, clearer collection states and responsive/non-overlapping dashboard and assistant charts.
- Add Romanian private-clinic discovery queries and retain direct/manual scraping without Exa discovery.

## 0.6.0 — 2026-09-09

- Replace the form-heavy Competition workspace with a Lithuania wellness dashboard: positioning landscape, collection coverage, capability heatmap, IV/wellness price chart, and compact in-table filters.
- Add a PostgreSQL-backed, authenticated **Market → Watchlist Editor** seeded with 12 named Lithuanian IV/longevity and multi-specialty competitors.
- Support two collection inputs through one evidence pipeline: Exa URL discovery and manually curated official URLs.
- Deep-scrape watched URLs directly without Exa, and deep-fetch Exa-discovered URLs with retained live-crawl content as a bounded fallback.
- Stream deterministic, stored-data Plotly charts alongside Market AI Assistant answers.
- Preserve strict verbatim grounding for every extracted service and price while allowing authenticated watchlist inclusion to identify a provider on its verified official domain.
- Expand Lithuanian wellness discovery queries, staff permissions, documentation, tests, and all 11 non-English locale catalogues.

## 0.5.0 — 2026-09-08

- Add Baltic private-clinic competitive intelligence with regular service prices, filters, clinic drill-downs, source evidence and accumulating weekly history.
- Add an interactive Leaflet/OpenStreetMap market map with evidenced clinic addresses.
- Add Exa personal/shared credentials under Integrations, administrator Market Configuration, and weekly/manual background collection.
- Make the Market AI Assistant aware of the active page and filters, with isolated read-only competitor tools; include the pending application AI/BYOK integration.
- Seed 211 public service observations from four providers across Lithuania, Latvia and Estonia, with five mapped branches.
- Keep Leaflet marker assets in the deployment image and exclude local SQLite/search scratch data.
- Fix the local FastDevops deployment wrapper path.

Validation: 71 tests and 38 subtests passed; three paid Exa checks passed separately. Browser checks covered map zoom/pan, clinic navigation, filtering and a live page-aware AI response. Legacy evaluation: 193/195, with pre-existing version-label and Staff-label expectations.

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
