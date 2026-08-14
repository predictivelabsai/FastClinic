# Estonian TEHIK / TIS adapter

Status: synthetic sandbox implemented on 2026-08-14. No X-Road, ee-dev, test or
production service is connected.

## Purpose and system ownership

Estonia's central Health Information System is **Tervise infosüsteem (TIS)**.
The Ministry of Social Affairs is the controller and TEHIK develops and manages
the system. Healthcare providers exchange national health information through
controlled services rather than through an anonymous public API.

Official starting points:

- [TEHIK Health Information System](https://www.tehik.ee/en/health-information-system)
- [TEHIK Information Centre and standards direction](https://www.tehik.ee/en/information-centre)
- [TEHIK data formats](https://teabekeskus.tehik.ee/et/vormingud)
- [Master Patient Index implementation guide](https://github.tehik.ee/ig-ee-mpi/dev.html)
- [EE MPI Patient profile](https://github.tehik.ee/ig-ee-mpi/StructureDefinition-ee-mpi-patient.html)
- [Digital referral requirements](https://www.tehik.ee/en/digital-referral)
- [X-Road REST protocol](https://www.x-tee.ee/docs/live/xroad/pr-rest_x-road_message_protocol_for_rest.html)

The links were reviewed on 2026-08-14. TEHIK's upTIS migration means service and
format versions must be pinned per interface during onboarding.

## What was implemented

`web/adapters/ee/` contains:

- privacy-safe Estonian personal-code structure/checksum validation;
- a clearly labelled synthetic outpatient fixture with no valid national
  personal code, provider registry code or professional identifier;
- an HL7 CDA-shaped outpatient epicrisis XML document using the correct CDA
  namespace but an intentionally non-production FastClinic template OID;
- an EE MPI FHIR R5 verified-patient profile preview and authorization-request
  shape, labelled against the public `1.5.0-trial-use` guide;
- X-Road REST headers (`X-Road-Client`, user, request ID, protocol version and
  mandatory purpose/issue) and TEHIK auth/MPI URL composition;
- local CDA/FHIR shape checks that never claim official validation;
- fail-closed live configuration; and
- the shared idempotent exchange/reconciliation ledger.

## API

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

Submission/list/reconciliation routes require `FASTSME_API_TOKEN` and submission
requires `Idempotency-Key`. Mock receipts cannot be mistaken for TEHIK receipts.

## Access and licensing answer

TIS access requires an authorised **Estonian healthcare provider** and an
authenticated professional with an appropriate role and treatment purpose. A
provider must hold the applicable Health Board activity licence; professional
registrations and activity licences are maintained through MEDRE. Integration
also requires X-Road membership/security-server infrastructure (or an approved
provider arrangement), the clinic's registered subsystem, and TEHIK-granted
access to the specific TIS services.

There is no open licence allowing a software vendor to browse national records.
The vendor can operate as the clinic's contracted system supplier/processor, but
the clinic remains the authorised healthcare-service context. Costs and contract
terms for X-Road infrastructure, certification, implementation and any TEHIK
service arrangements must be confirmed for the deployment; the public technical
guides are not evidence that access is free or automatically granted.

## Production onboarding and exit criteria

1. Verify the clinic's Estonian healthcare activity licence, registry code,
   sites, practitioner registrations, roles and intended services.
2. Register/configure the clinic's X-Road subsystem and security server; request
   ee-dev access to TEHIK auth, MPI and each required TIS service.
3. Obtain official test persons/users and map staff authentication to the exact
   professional and treatment context. Every read needs a recorded purpose.
4. Pin the current MPI FHIR IG and the exact CDA/message templates, OIDs,
   classifiers and validation rules for the selected documents.
5. Begin with MPI identity resolution and one outpatient epicrisis. Add digital
   referrals and responses next; add national booking, prescriptions, imaging or
   reimbursement surfaces only when required.
6. Run TEHIK's local/central validation tooling, negative authorization tests,
   X-Road message/audit correlation, retry/idempotency and reconciliation tests.
7. Complete RBAC, immutable access/submission logs, DPIA, retention, incident
   response, backups, monitoring, certificate rotation and portal fallback.
8. Complete TEHIK acceptance and a controlled parallel run before production.

## Known limitations

- The CDA XML is deliberately not a valid production TIS document: its template
  OID, identifiers and codes are sandbox-only and it has not passed a TEHIK XSD
  or business-rule validator.
- MPI uses a public trial-use R5 profile preview, not an ee-dev transaction.
- The X-Road output is request context only. There is no security-server client,
  mTLS/certificate operation, TEHIK authorization token or network call.
- Digital referral, e-prescription, national booking, imaging, reimbursement,
  inbound events and patient-consent/declaration services are not implemented.
- The generic FastClinic R4 export remains independent from service-specific
  Estonian CDA and R5 shapes.
- Local shape tests are not national conformance, legal or security approval.
