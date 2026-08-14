# FastClinic × MedBackend Integration Plan

**Status:** agreed target, implementation pending  
**Updated:** 14 August 2026

## Decision

MedBackend is the target primary system of record for authentication and FHIR
clinical resources. During integration testing, FastClinic remains authoritative
and mirrors records to MedBackend. Authority moves resource-by-resource only
after MedBackend has the required FastClinic feature parity, reconciliation is
clean, and the cutover has been explicitly approved. FastClinic remains the
clinic-facing operational UI and maintains a local database for responsive
workflows, reporting, reconciliation, and temporary offline operation.

The integration must support three safe runtime modes:

| Mode | Behaviour |
|---|---|
| `disabled` | No MedBackend calls; current synthetic FastClinic behaviour |
| `dry_run` | Render and validate mappings without transmitting records |
| `mirror` | FastClinic is authoritative and mirrors changes to MedBackend for testing |
| `primary` | MedBackend is authoritative for explicitly enabled resource types |

Configuration is controlled by `MEDBACKEND_ENABLED`,
`MEDBACKEND_SYNC_MODE`, and `MEDBACKEND_RECORD_MODE`. The initial environment is
disabled, `mirror`, and dry-run until secrets, callbacks, and contract tests are
complete. Enabling transmission must not silently change record authority.

The existing xAI-backed FastClinic assistant remains unchanged. MedBackend's
OpenAI-compatible endpoint is not the model provider in this phase.

## Confirmed development project

- Project ID: `c82bf761-d720-4eb8-92e7-3719da7342fd`
- GraphQL: `https://dev-backbone.medbackend.com/graphql`
- REST base: `https://dev-backbone.medbackend.com`
- Required header: `X-Project-ID`
- Separate OAuth clients exist for patient and practitioner portals.
- The direct FHIR Server is reported as not yet available; GraphQL is therefore
  the initial clinical transport.

The initial connectivity contract is an HTTP `POST` with a bearer token and the
project header:

```python
import requests

response = requests.post(
    "https://dev-backbone.medbackend.com/graphql",
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Project-ID": "c82bf761-d720-4eb8-92e7-3719da7342fd",
    },
    json={"query": "{ PatientList { id name { family given } } }"},
    timeout=30,
)
response.raise_for_status()
payload = response.json()
if payload.get("errors"):
    raise RuntimeError(payload["errors"])
patients = payload["data"]["PatientList"]
```

The integration client adds token refresh, bounded retries, correlation IDs,
redacted logging, and GraphQL error/schema validation around this request.

Client secrets are never committed. They belong only in the ignored local
`.env` or the deployment secret manager.

## Target boundary

```text
Patient / practitioner browser
        |
        | OAuth authorization code + PKCE
        v
MedBackend authorization service
        |
        | access token
        v
FastClinic UI and integration API
        |
        | GraphQL + X-Project-ID
        v
MedBackend FHIR record (authoritative)
        |
        | signed webhook / scheduled reconciliation
        v
FastClinic PostgreSQL projection + operational workflows
```

Browser clients must not receive or use either OAuth client secret. FastClinic
uses authorization code with PKCE, validates JWT signature, issuer, audience,
expiry, state, and nonce against the appropriate JWKS, and keeps tokens in a
server-side session.

## Resource coverage

| FastClinic concept | FHIR projection | Phase |
|---|---|---|
| subject/patient | `Patient` | 1 |
| guardian/contact/payer | `RelatedPerson`, `Person` | 1 |
| clinician | `Practitioner`, `PractitionerRole` | 1 |
| clinic/department/room | `Organization`, `HealthcareService`, `Location` | 1 |
| consultation | `Encounter` | 2 |
| diagnosis | `Condition` | 2 |
| clinical item/treatment | `Procedure`, `ServiceRequest`, `Observation` as applicable | 2 |
| note/document | `DocumentReference` or `Composition` | 2, after profile decision |
| appointment | `Appointment`, later `Schedule` and `Slot` | 2 |
| reminder/recall | `ImmunizationRecommendation`, `Task`, `CommunicationRequest` | 2 |
| communication attempt | `Communication` | 2 |
| consent | `Consent` | 2 |
| invoice | `Invoice` plus `ChargeItem` references | 3 |
| payment/refund | `PaymentNotice` or agreed financial profile | 3 |
| sync and source evidence | `Provenance`, `AuditEvent` | every phase |

The mapping for financial resources must be proven against MedBackend's actual
schema before implementation. FHIR does not provide a complete general-ledger
model, so FastClinic's balanced `gl_entry` ledger remains a local accounting
record unless an explicit MedBackend extension/profile is agreed.

## Data-store prerequisite — implemented

FastClinic retains two logical persistence boundaries:

- clinical subject, diagnosis, note, item, consultation, and party data can use
  PostgreSQL;
- appointments, reminders, communications, invoices, payments, ledger, chat,
  API audit, external bookings, and local accounts use operational tables.

The operational store is now selectable through `FASTCLINIC_OPS_BACKEND`. The
configured development deployment uses `DATABASE_URL_PROD` and `fast_clinic`;
SQLite remains available for isolated tests. `scripts/migrate_ops_to_postgres.py`
additively copies any legacy operations and account databases and advances
PostgreSQL sequences. Logical separation is preserved without requiring a
separate database engine.

## Synchronization design

Add integration-owned PostgreSQL tables:

- `medbackend_resource_link`: local identity, FHIR type/id, remote version,
  payload hash, last synchronized time.
- `medbackend_outbox`: ordered create/update/archive work, idempotency key,
  attempts, next retry and terminal state.
- `medbackend_inbox`: webhook request ID, raw-body hash, signature result and
  processing state.
- `medbackend_conflict`: local/remote versions, field differences and operator
  resolution.
- `medbackend_checkpoint`: resource-specific bulk-import and reconciliation
  cursors.

In mirror mode FastClinic owns each record, commits locally first, and places the
corresponding MedBackend operation in the transactional outbox. A remote failure
does not roll back clinic work; it creates visible sync debt for retry or operator
resolution. Once a resource type is promoted to primary mode, FastClinic writes
through the adapter, updates its projection only after a successful response,
and uses `meta.versionId` for optimistic concurrency. No last-write-wins
behaviour is allowed for demographics, consent, clinical facts, or money. Remote
deletion is projected as archive/cancel/void, never an automatic destructive
local delete.

## Delivery sequence

### Phase 0 — OAuth and contract proof

1. Register real patient and practitioner callback URIs.
2. Supply both client secrets through the deployment secret manager.
3. Implement authorization code + PKCE, callback validation, refresh/logout, and
   separate patient/practitioner session roles.
4. Run `Me`, schema introspection in development, and capability probes.
5. Pin a schema snapshot and test token expiry, wrong project, wrong audience,
   and revoked access.

Exit: both roles can authenticate and execute their minimum permitted query.

### Phase 1 — patient and workforce bootstrap

1. Build the MedBackend GraphQL client and mapping/validation layer.
2. Add Admin connection status and dry-run mapping reports.
3. Bulk-import Organization, Location, Practitioner, PractitionerRole, Patient,
   RelatedPerson, and Person in dependency order.
4. Match only on governed identifiers; quarantine duplicates and ambiguity.
5. Re-read every created resource and reconcile counts, references, identifiers,
   and payload hashes.

Exit: every FastClinic person and clinician has a verified MedBackend link.

### Phase 2 — complete clinical and operational record

1. Export encounters, conditions, procedures, observations, appointments,
   reminders, consent, documents, and communications.
2. Add transactional outbox writes to all FastClinic mutations.
3. Add signed webhook intake and scheduled reconciliation.
4. Implement an operator conflict/quarantine screen.

Exit: every selected FastClinic domain is mirrored and reconciled. Each resource
type receives a separate feature-parity and cutover decision before MedBackend
becomes authoritative for it.

### Phase 3 — billing and payment

1. Agree the Invoice, ChargeItem, payer/Coverage, payment and refund profiles.
2. Export invoices only after referenced subjects, payers, encounters, and
   charge items exist.
3. Preserve currency, tax, void, refund, idempotency, and provenance semantics.
4. Reconcile totals and payment state; retain the balanced FastClinic ledger.

Exit: MedBackend contains the interoperable financial mirror and reconciliation
reports show no unexplained differences.

### Phase 4 — Estonia / TEHIK stubs

Create `web/adapters/ee_tehik.py` behind the country-adapter protocol, with every
external operation raising `AdapterNotAvailable` until onboarding and official
contracts are confirmed. Pin interfaces for:

- Estonian personal-code validation and governed patient matching;
- practitioner and organization identity mapping;
- document/resource export and import envelopes;
- terminology/profile validation;
- consent, representation, audit, and provenance;
- transport, certificate, test-environment, and conformance hooks.

The stub must not claim upTIS or TEHIK conformance and must not make live calls.
Implementation begins only against the current official implementation guides,
test services, onboarding terms, and certification requirements.

## Operational and safety gates

- TLS only; secrets in a secret manager; redact tokens and clinical bodies from
  ordinary logs.
- Validate JWTs locally and enforce MedBackend role/project claims in addition
  to FastClinic route authorization.
- Transactional outbox, exponential backoff with jitter, bounded retries,
  dead-letter review, correlation IDs, and replay-safe webhook processing.
- Immutable audit records for login, read, export, mutation, conflict,
  reconciliation, and administrator action.
- Automated mapping, contract, RBAC, PKCE, webhook, idempotency, concurrency,
  deletion, financial-balance, outage, recovery, and synthetic end-to-end tests.
- Feature flags per resource type and an immediate integration kill switch.
- No production health data until controller/processor roles, hosting region,
  retention, DPIA, incident response, backup/restore, and data-subject workflows
  are approved.

## Decisions still required

1. Confirm whether the first bulk load includes all existing synthetic records
   or only records created after integration activation. The working assumption
   is a complete synthetic bulk mirror followed by incremental changes.
2. Provide the real FastClinic patient and practitioner callback URLs and add
   them to the MedBackend project.
3. Confirm the OAuth grant details and scopes returned by MedBackend; the client
   secrets alone do not establish whether machine-to-machine synchronization
   uses client credentials, a practitioner service account, or another grant.
4. Choose the first TEHIK exchange use case (patient summary, referral,
   prescription, appointment, or another document/workflow); “Estonian FHIR
   exchange” is too broad to define a conformant adapter contract.
