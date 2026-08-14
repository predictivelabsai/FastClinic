# Lithuanian E. sveikata / ESPBI adapter

Status: synthetic sandbox implemented on 2026-08-14. No national test or
production system is connected.

## Purpose and system ownership

Lithuania's national e-health platform is **E. sveikata**, formally ESPBI IS.
The Ministry of Health governs the national e-health system and Registrų centras
is the main operator/integration counterpart. The adapter lets FastClinic keep a
normalised internal model while materialising the country- and service-specific
wire shapes required at the boundary.

Official starting points:

- [Current ESPBI integration specifications](https://www.esveikata.lt/espbi-specifikacija)
- [Registrų centras integration onboarding](https://info.registrucentras.lt/content/144417)
- [ESPBI clinical-document catalogue](https://pacientas.esveikata.lt/help/pages/espbi-is-dokumentai-ir-duomenu-rinkiniai.html)
- [eLab FHIR implementation guide](https://specialistas.esveikata.lt/dp/elab/iframe/fhir-ig/guidance.html)
- [IPR appointment specifications](https://www.esveikata.lt/ipr-specifikacija)
- [ESPBI FHIR authorization guide](https://www.esveikata.lt/bylos/failai/Instrukcijos/LTNHR-FHIRauthorization_2020.02.18.pdf)

The links were reviewed on 2026-08-14. Profile and endpoint versions must be
rechecked during every clinic onboarding.

## What was implemented

`web/adapters/lt/` contains:

- Lithuanian personal-code structure/checksum validation that returns only a
  masked value and never claims an ESPBI trace;
- clearly labelled synthetic patient, practitioner, role, organisation,
  encounter, condition, note, appointment and laboratory-order fixtures;
- E025, E027/E027-ATS and E063 clinical-document sandbox envelopes;
- an IPR appointment projection;
- a FHIR R5 E200 transaction Bundle containing Patient, Organization,
  Practitioner, PractitionerRole, Encounter, ServiceRequest, Composition and
  Provenance resources;
- structural validators that distinguish local checks from an official
  validator result;
- OAuth 1.0 RSA-SHA1 canonicalisation/signing at an isolated transport boundary;
- a separate clinical-signature interface whose sandbox proof is explicitly
  `qualified_electronic_signature=false` and `legal_effect=false`;
- fail-closed live configuration; and
- a persistent, idempotent submission/reconciliation ledger shared with other
  national adapters.

The synthetic fixture intentionally has no plausible Lithuanian personal code,
JAR code, ESPBI resource ID, licence number, or real contact detail. Registrų
centras test identities must replace it in an approved test environment.

## API

Public, synthetic-only inspection:

```text
GET  /api/v1/adapters/LT/status
POST /api/v1/adapters/LT/verify-identifier
GET  /api/v1/adapters/LT/fixtures/outpatient?surface=espbi&document_type=E025
GET  /api/v1/adapters/LT/fixtures/outpatient?surface=elab
GET  /api/v1/adapters/LT/fixtures/outpatient?surface=ipr
POST /api/v1/adapters/LT/validate
```

Token-gated local sandbox operations:

```text
POST /api/v1/adapters/LT/sandbox/submissions
GET  /api/v1/adapters/LT/sandbox/submissions
POST /api/v1/adapters/LT/sandbox/submissions/{id}/reconcile
```

Every submission requires `Authorization: Bearer $FASTSME_API_TOKEN` and a
stable `Idempotency-Key`. The mock returns an `LT-SBX-*` correlation ID and
states that nothing was sent to ESPBI.

## Access and licensing answer

This is **not an open public-records API and not merely a developer API key**.
The official onboarding instructions say a healthcare institution must conclude
an ESPBI use/integration agreement, submit registration and contact details,
provide employment data where applicable, and register a public key. Access is
therefore clinic/institution specific. Clinicians must also have the applicable
professional qualification/licence and institutional role recorded for the
work they perform.

No separate generic “FHIR developer licence” or published universal API fee was
identified in the official onboarding material reviewed. That does **not** mean
access is automatically free or permissionless: contract terms, service scope,
test acceptance and any current charges must be confirmed with Registrų centras
for the particular clinic. A software vendor can implement the adapter as the
clinic's processor/supplier, but cannot use that role to independently retrieve
national patient records.

## Production onboarding and exit criteria

1. Confirm the Lithuanian healthcare-provider entity, JAR code, sites,
   practitioner employment/roles, specialties and services.
2. Conclude the ESPBI integration agreement and obtain the approved MOK/PUB
   endpoints, test identities and currently applicable specification versions.
3. Decide the first clinical scope. The recommended pilot is private-pay
   outpatient care with E025; add E027 and IPR next. Add e-prescribing, eLab,
   imaging and VLK/SVEIDRA only when the clinic requires them.
4. Replace synthetic identifiers and pinned sandbox classifier subset with the
   official test identities and versioned classifier distribution.
5. Integrate an approved key store/HSM and qualified electronic-signature
   provider. Do not store private signing keys in PostgreSQL.
6. Run the official XSD/profile/terminology validators and negative tests, then
   complete Registrų centras acceptance.
7. Complete clinic RBAC, professional context, DPIA, retention/legal hold,
   immutable audit, incident response, backups, monitoring and a manual portal
   fallback.
8. Go live gradually only after every required document type has accepted,
   reconciled test evidence and key-revocation/rollback procedures.

## Known limitations

- The envelope used for E025/E027/E063 is a FastClinic sandbox representation,
  not the complete current ESPBI wire schema.
- The eLab Bundle follows public R5 profile relationships but has not been run
  against the official validator. Public documentation is versioned and can
  change; the sandbox snapshot records `0.3.36-shape-snapshot` only.
- IPR is a mapping preview, not a complete booking/cancellation client.
- OAuth transport signing is implemented, but live network calls are disabled.
  The currently approved algorithm, key size, endpoints and headers must be
  reconfirmed rather than copied from older examples.
- A SHA-256 sandbox integrity proof is not a qualified electronic signature.
- No national records are read and no clinical document is submitted.
- E-prescription, MedVAIS/DICOM, VLK/SVEIDRA and inbound national-event sync are
  not implemented.
- Local structural validation is not regulatory, legal, security, or national
  conformance certification.
