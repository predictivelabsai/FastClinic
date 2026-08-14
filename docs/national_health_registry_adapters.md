# National health registry adapters

Last reviewed: 2026-08-14

This document describes FastClinic's country-adapter architecture and the
implemented synthetic sandboxes for Lithuania and Estonia. It records what was
built, how it was tested, which parts remain deliberately disabled, and what a
deploying clinic must complete before exchanging real health data.

The implementation is a **development and conformance-preparation foundation**.
It is not evidence of approval by Registrų centras, TEHIK, a health authority,
or a conformity-assessment body. No national test or production endpoint was
called while building it, and no real patient identity is included.

## Executive answer: is national API access licensed?

These are not open public-record APIs and access is not granted through a
generic developer key.

In Lithuania, the healthcare institution must enter into an ESPBI IS
use/integration agreement, register institutional and contact information,
provide employment relationships where applicable, and register a public key.
The professionals using the connection must have the applicable professional
qualification/licence and institutional role.

In Estonia, access is tied to an authorised healthcare provider, its applicable
Health Board activity licence, registered professionals and a legitimate care
context. Technical access also requires the clinic's X-Road subsystem/security
server arrangement and TEHIK-granted rights to each requested service.

No separate universal “FHIR developer licence” or universal API price was
identified in the official material reviewed. This does not imply that access
is free or permissionless. The deploying clinic must confirm current contract
terms, service scope, infrastructure/certificate costs, test requirements and
any charges directly with the national operator. A software vendor may act as
the clinic's supplier or processor, but that does not give the vendor an
independent right to retrieve national patient records.

## Architecture

FastClinic keeps its internal patient, party, encounter, appointment, billing
and audit models normalised. National wire formats are materialised only at the
adapter boundary.

```text
FastClinic normalised core + generic FHIR R4 projection
│
├── GB adapter
│   ├── UK Core R4
│   └── GP Connect STU3 translation
│
├── LT adapter
│   ├── ESPBI E025 / E027 / E027-ATS / E063 sandbox documents
│   ├── IPR appointment projection
│   └── eLab E200 FHIR R5 transaction Bundle
│
└── EE adapter
    ├── TIS HL7 CDA-shaped outpatient document
    ├── TEHIK MPI FHIR R5 preview
    └── X-Road REST request context
```

FHIR version differences are intentional. FastClinic's generic export remains
R4; a national service adapter projects the exact version and profile expected
by that service. The application is not globally upgraded to R5 merely because
Lithuanian eLab or Estonian MPI uses R5.

The registry in `web/adapters/registry.py` exposes `GB`, `LT` and `EE`. Shared
sandbox submission state is implemented in `web/adapters/exchange.py` and the
portable `national_exchange` operations table.

## Shared exchange controls

The Lithuanian and Estonian adapters use the same exchange lifecycle:

1. Generate or accept a synthetic payload.
2. Run local structural validation.
3. Require a stable `Idempotency-Key`.
4. Canonicalise and hash the payload with SHA-256.
5. Persist country, surface, document type, subject reference, professional
   context, correlation ID, status, request, mock response and timestamps.
6. Return the same exchange for an exact retry; reject reuse of the key with a
   different payload.
7. Reconcile the mock receipt into a distinct final state.
8. Write the API action to the existing append-only API audit trail.

The table runs in SQLite locally and PostgreSQL when
`FASTCLINIC_OPS_BACKEND=postgresql`. PostgreSQL uses the configured
`DATABASE_URL_PROD` and `FASTCLINIC_DB_SCHEMA=fast_clinic`. The application
initialises the table additively; it does not replace clinical tables.

Sandbox receipts use `LT-SBX-*` or `EE-SBX-*` correlation IDs and explicitly
say that the payload was not sent to a national system. Listing, submission and
reconciliation operations require `FASTSME_API_TOKEN`.

## Lithuanian adapter

### National surface

Lithuania's national e-health platform is E. sveikata, formally ESPBI IS. The
Ministry of Health governs the system and Registrų centras is the principal
operator and integration counterpart.

The implementation under `web/adapters/lt/` provides:

- privacy-safe Lithuanian personal-code structure and checksum validation;
- synthetic patient, organisation, practitioner, role, encounter, diagnosis,
  note, appointment and laboratory-order fixtures;
- E025 outpatient, E027 referral, E027-ATS referral-response and E063
  vaccination sandbox document projections;
- an IPR appointment projection;
- an eLab FHIR R5 E200 transaction Bundle with Patient, Organization,
  Practitioner, PractitionerRole, Encounter, ServiceRequest, Composition and
  Provenance;
- local document, IPR and eLab shape validators;
- isolated OAuth 1.0 RSA-SHA1 canonicalisation and signing support for the
  published transport pattern;
- a separate clinical-signature boundary; and
- a fail-closed live transport configuration.

The sandbox clinical signature is a SHA-256 integrity proof only. It always
returns `qualified_electronic_signature=false` and `legal_effect=false`.
Production must use an approved qualified-signature workflow and protect private
keys in an HSM or managed key service rather than in the application database.

### Lithuanian sandbox API

```text
GET  /api/v1/adapters/LT/status
POST /api/v1/adapters/LT/verify-identifier
GET  /api/v1/adapters/LT/fixtures/outpatient?surface=espbi&document_type=E025
GET  /api/v1/adapters/LT/fixtures/outpatient?surface=elab
GET  /api/v1/adapters/LT/fixtures/outpatient?surface=ipr
POST /api/v1/adapters/LT/validate
POST /api/v1/adapters/LT/sandbox/submissions
GET  /api/v1/adapters/LT/sandbox/submissions
POST /api/v1/adapters/LT/sandbox/submissions/{id}/reconcile
```

Example:

```bash
curl "http://localhost:5005/api/v1/adapters/LT/fixtures/outpatient?surface=elab"

curl -X POST "http://localhost:5005/api/v1/adapters/LT/sandbox/submissions" \
  -H "Authorization: Bearer $FASTSME_API_TOKEN" \
  -H "Idempotency-Key: lt-e025-local-example-001" \
  -H "Content-Type: application/json" \
  -d '{"surface":"espbi","document_type":"E025"}'
```

### Lithuanian live configuration contract

```text
LT_ESPBI_LIVE_ENABLED=false
LT_ESPBI_BASE_URL=
LT_ESPBI_CONSUMER_KEY=
LT_ESPBI_PRIVATE_KEY_FILE=
LT_ESPBI_ORGANIZATION_JAR=
LT_ESPBI_SPEC_VERSION=
```

Supplying these values does not activate network calls. The live transport
continues to raise `AdapterNotAvailable` until the approved profiles, test
identities, qualified signature provider and acceptance process are implemented.

### Lithuanian production sequence

1. Confirm the healthcare-provider entity, JAR code, sites, practitioners,
   employment relationships, specialties and intended services.
2. Complete Registrų centras integration onboarding and obtain the applicable
   MOK/PUB endpoints, test identities and current specification versions.
3. Start with one private-pay outpatient specialty and E025. Add E027 and IPR
   next; add e-prescription, eLab, imaging and VLK/SVEIDRA only when required.
4. Replace sandbox identifiers and terminology with official test resources and
   versioned ESPBI classifiers.
5. Complete qualified signing, key rotation and revocation.
6. Run official XSD/profile/terminology validation and negative tests.
7. Complete institutional RBAC, professional context, audit, DPIA, retention,
   legal hold, incident response, backup and portal-fallback procedures.
8. Complete national acceptance and a controlled parallel run before go-live.

## Estonian adapter

### National surface

Estonia's central Health Information System is Tervise infosüsteem (TIS). The
Ministry of Social Affairs is the controller and TEHIK develops and manages the
system. Established TIS exchange remains document/message based over X-Road,
while newer services such as the Master Patient Index publish FHIR R5 guides.

The implementation under `web/adapters/ee/` provides:

- privacy-safe Estonian personal-code structure and checksum validation;
- a synthetic patient, provider, practitioner, encounter and diagnosis fixture;
- a namespace-correct HL7 CDA-shaped outpatient epicrisis;
- a FHIR R5 EE MPI verified-patient preview and authorization-request shape;
- X-Road REST request headers, mandatory purpose/issue and TEHIK auth/MPI URL
  composition;
- local CDA and MPI shape validators; and
- a fail-closed live transport configuration.

The CDA template OID is intentionally a FastClinic sandbox OID. It cannot be
mistaken for or submitted as an official TIS document.

### Estonian sandbox API

```text
GET  /api/v1/adapters/EE/status
POST /api/v1/adapters/EE/verify-identifier
GET  /api/v1/adapters/EE/fixtures/outpatient?surface=tis
GET  /api/v1/adapters/EE/fixtures/outpatient?surface=mpi
GET  /api/v1/adapters/EE/xroad-preview
POST /api/v1/adapters/EE/validate
POST /api/v1/adapters/EE/sandbox/submissions
GET  /api/v1/adapters/EE/sandbox/submissions
POST /api/v1/adapters/EE/sandbox/submissions/{id}/reconcile
```

Example:

```bash
curl "http://localhost:5005/api/v1/adapters/EE/xroad-preview"

curl -X POST "http://localhost:5005/api/v1/adapters/EE/sandbox/submissions" \
  -H "Authorization: Bearer $FASTSME_API_TOKEN" \
  -H "Idempotency-Key: ee-tis-local-example-001" \
  -H "Content-Type: application/json" \
  -d '{"surface":"tis"}'
```

### Estonian live configuration contract

```text
EE_TIS_LIVE_ENABLED=false
EE_XROAD_SECURITY_SERVER=
EE_XROAD_INSTANCE=ee-dev
EE_XROAD_CLIENT=
EE_TIS_ORGANIZATION_CODE=
EE_TIS_PROFILE_VERSION=
```

Supplying these variables does not enable live exchange. Production still
requires the clinic's registered X-Road subsystem/security server, certificates,
TEHIK service permissions, approved test users/patients, current formats and
acceptance evidence.

### Estonian production sequence

1. Confirm the provider's Estonian healthcare activity licence, registry code,
   sites, professional registrations, roles and intended services.
2. Register or configure the clinic's X-Road subsystem/security server and
   request ee-dev access to TEHIK auth, MPI and each required TIS service.
3. Obtain official test users and patients; bind every request to the exact
   professional, organisation, role, patient and recorded treatment purpose.
4. Pin the current MPI FHIR guide plus the exact CDA/message templates, OIDs,
   classifiers and validation rules used by the clinic.
5. Begin with MPI identity resolution and one outpatient epicrisis. Add digital
   referral and response workflows next.
6. Run TEHIK validation, negative authorization, X-Road correlation,
   idempotency, retry and reconciliation tests.
7. Complete clinic RBAC, immutable audit, DPIA, retention, incident response,
   backup, monitoring, certificate rotation and portal fallback.
8. Complete TEHIK acceptance and a controlled parallel run before production.

## Security and privacy rules

- National personal codes are external identifiers, never FastClinic primary
  keys. Identifier-check endpoints return only masked values.
- A valid checksum does not prove identity or permission and is never reported
  as a national-system trace.
- National reads and submissions require an institution, authenticated
  professional, professional role, patient context and recorded purpose.
- Test, production and public-demo data must remain isolated.
- Signing keys, X-Road certificates and national credentials must not be stored
  in source control, logs, fixture files or general application tables.
- Payload logs should be minimised in production. Immutable audit metadata and
  signed payload hashes should be retained according to the clinic's policy.
- No clinical submission should silently bypass clinician review/signature.
- Failed, rejected and uncertain submissions must stay visible until reconciled
  or resolved through a documented manual fallback.

## Implemented validation and test coverage

The deterministic tests cover:

- LT and EE adapter registry/status;
- national personal-code checksum, date validation and masking;
- E025/E027/E063, IPR and E200 fixture generation;
- FHIR R5 transaction composition and Provenance;
- CDA namespace, required elements and XML well-formedness;
- MPI profile and X-Road request-context shapes;
- OAuth body hashing, RSA signing and signature verification;
- non-qualified sandbox signature semantics;
- live transport fail-closed behaviour;
- SQLite exchange persistence, country isolation, idempotent replay, conflict
  detection and reconciliation;
- public fixture/validation endpoints and bearer-token protection; and
- complete UI translation catalogue coverage.

At the time of this document update, the full suite passes 94 tests plus 38
localisation subtests. Four unrelated MedBackend tests remain opt-in live checks
and are skipped without their explicit live configuration.

## Limitations and intentionally unfinished work

| Area | Implemented | Still required for production |
|---|---|---|
| LT ESPBI documents | Sandbox E025/E027/E027-ATS/E063 envelopes | Exact current national schemas, official validation and acceptance |
| LT eLab | R5 E200 transaction shape and Provenance | Official test identities, terminology, validator and live endpoint |
| LT IPR | Appointment projection | Full slot, booking, cancellation and reconciliation client |
| LT signing | OAuth RSA boundary and sandbox integrity proof | Approved qualified-signature provider and protected production keys |
| EE TIS | Namespace-correct CDA-shaped XML | Exact TEHIK template OIDs, XSD/business validation and X-Road exchange |
| EE MPI | R5 verified-patient profile preview | ee-dev authorization, official test data and live service client |
| EE X-Road | Headers, purpose and URL composition | Registered subsystem, security server, certificates and service rights |
| Shared exchange | Idempotency, hash, audit and mock reconciliation | National receipt/status parsing, retry policy, dead-letter operations and alerts |
| Optional systems | Documented boundaries | e-prescription, imaging, reimbursement, national booking and inbound event sync |

Local shape validation is not national conformance, legal approval, security
certification or proof of a lawful basis. The final production scope must be
agreed with the clinic, national operator and appropriately qualified counsel.

## Official references

### Lithuania

- [ESPBI integration specifications](https://www.esveikata.lt/espbi-specifikacija)
- [Registrų centras integration onboarding](https://info.registrucentras.lt/content/144417)
- [ESPBI clinical-document catalogue](https://pacientas.esveikata.lt/help/pages/espbi-is-dokumentai-ir-duomenu-rinkiniai.html)
- [eLab FHIR implementation guide](https://specialistas.esveikata.lt/dp/elab/iframe/fhir-ig/guidance.html)
- [IPR specifications](https://www.esveikata.lt/ipr-specifikacija)
- [ESPBI FHIR authorization guide](https://www.esveikata.lt/bylos/failai/Instrukcijos/LTNHR-FHIRauthorization_2020.02.18.pdf)

### Estonia

- [TEHIK Health Information System](https://www.tehik.ee/en/health-information-system)
- [TEHIK Information Centre](https://www.tehik.ee/en/information-centre)
- [TEHIK data-exchange formats](https://teabekeskus.tehik.ee/et/vormingud)
- [Master Patient Index implementation guide](https://github.tehik.ee/ig-ee-mpi/dev.html)
- [EE MPI Patient profile](https://github.tehik.ee/ig-ee-mpi/StructureDefinition-ee-mpi-patient.html)
- [Digital referral requirements](https://www.tehik.ee/en/digital-referral)
- [TEHIK MEDRE](https://www.tehik.ee/en/healthcare-management-information-system-medre)
- [X-Road REST message protocol](https://www.x-tee.ee/docs/live/xroad/pr-rest_x-road_message_protocol_for_rest.html)

Country-specific detail is also available in
`docs/adapters/LITHUANIA_ESPBI.md` and `docs/adapters/ESTONIA_TIS.md`.
