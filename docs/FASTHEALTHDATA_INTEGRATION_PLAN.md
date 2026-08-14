# FastClinic × FastHealthData Integration Plan

**Status:** proposed architecture · **Updated:** 14 August 2026

## Decision

Keep the products separate and integrate them through governed contracts:

- **FastClinic** remains the direct-care operational system: subjects and
  representatives, appointments, encounters, diagnoses, procedures, billing,
  communications, and primary-use FHIR adapters.
- **FastHealthData** becomes the secondary-use/research zone: research projects,
  catalog metadata, legal/ethics context, dataset access decisions, disclosure
  review, aggregate analytics, and research output governance.

Do not copy FastHealthData tables into FastClinic or let both products share the
`fast_clinic` schema. A separate trust boundary makes purpose, access, retention,
and audit evidence easier to understand and enforce.

## Capability triage

| FastHealthData capability | Relevance to FastClinic | Recommendation |
|---|---|---|
| Standards-aware dataset and variable catalog | High | Integrate first; register every approved FastClinic research extract and its FHIR/OMOP mappings |
| Access requests and approve/reject decisions | High | Use for secondary-use access; keep clinical RBAC inside FastClinic |
| Append-only governance audit | High | Record catalog, access, intake, disclosure, and output decisions in FastHealthData; retain clinical audit in FastClinic |
| Research project lifecycle | High | Link exports to a project with purpose, legal basis, ethics reference, stage, and owner |
| Pseudonymisation workflow | High | Retain the contract, replace the demo hash with project-scoped HMAC in HSM/KMS before real data |
| k-anonymity signal | Medium | Use as one release-review input, never as an automatic publication decision |
| Aggregate cohort analytics | Medium | Useful after a governed intake; do not expose subject-level records through public analytics |
| FHIR / OMOP / openEHR variable mappings | High | Reuse the metadata vocabulary and add validation/provenance, not merely labels |
| AI assistant | Low initially | Keep assistants product-scoped; do not give one model ungoverned access to both operational and research zones |
| Shared users or shared database | Negative | Avoid; federate identity later with explicit roles and claims |

## Target architecture

```text
FastClinic direct-care zone
  normalised clinical core · consent/representation · clinical audit
                |
                | approved research-export specification
                v
Export coordinator / outbox
  field allow-list · purpose · project · snapshot · provenance · checksum
                |
                v
Pseudonymisation and minimisation gateway
  HSM/KMS HMAC · project-scoped subject key · coarsening · suppression
                |
                +----> separately governed re-identification service
                |      (not available to ordinary researchers)
                v
Encrypted research intake channel
  manifest + validated FHIR/OMOP files in EU/EEA object storage
                |
                v
FastHealthData research zone
  project · dataset versions · variable catalog · access approvals
  disclosure review · aggregate analytics · outputs · governance audit
```

The typed FastHealthData API registers governance metadata. It deliberately does
**not** accept raw subject rows. Bulk research data should move through an
encrypted, checksum-verified intake channel with short-lived credentials and an
immutable manifest.

## Current API contract

FastHealthData now exposes OpenAPI documentation at `/api/docs` and these useful
integration operations:

| Workflow | Endpoint | FastClinic use |
|---|---|---|
| Portfolio and standards discovery | `GET /v1/summary`, `GET /v1/roles` | Capability checks and integration health |
| Research project registration | `POST /v1/projects` | Create the purpose/legal-basis envelope for an export |
| Project lifecycle | `PATCH /v1/projects/{id}/stage` | Move from registration through intake, analysis, outputs, and closure |
| Dataset catalog registration | `POST /v1/datasets` | Register the approved extract without uploading its rows |
| Variable catalog | `POST /v1/datasets/{id}/variables` | Record source field, concept, standard path, type, and PII classification |
| Access request | `POST /v1/access-requests` | Request researcher access with a stated purpose |
| Access decision | `POST /v1/access-requests/{id}/decision` | Data Steward/DPO approval or rejection |
| Governance audit | `GET /v1/audit` | Reconcile cross-system workflow events |
| Disclosure signal | `GET /v1/disclosure/k-anonymity` | Add a bounded synthetic risk signal to release review |
| Pseudonymisation contract | `POST /v1/pseudonymise` | Demonstration only; do not call with real identifiers in production |

Protected operations require a bearer token. The first production integration
should replace the shared token with workload identity or OAuth2 client
credentials carrying tenant, role, and purpose claims.

## First incorporation slice: catalog-only export registration

This is the safest useful first release because no row-level clinical data
leaves FastClinic.

1. A FastClinic administrator selects a synthetic cohort definition and purpose.
2. FastClinic calculates aggregate counts and a field manifest locally.
3. An authorised worker creates or links the FastHealthData research project.
4. The worker registers one dataset and its variables through the API.
5. Each variable records:
   - FastClinic source field and source schema version;
   - FHIR R4 path and/or OMOP concept where available;
   - data type, nullability, sensitivity, and direct/quasi-identifier class;
   - transformation (exact, derived, coarsened, suppressed, or excluded).
6. Both products retain the external IDs, manifest hash, timestamp, and outcome.
7. No actual subject records are transferred in this phase.

### Acceptance criteria

- Replaying the same manifest is idempotent.
- No names, phone numbers, emails, street addresses, free-text notes, or raw
  national identifiers appear in FastHealthData.
- FastClinic and FastHealthData audit events can be correlated by one export ID.
- A Data Steward can see the project, dataset, variables, legal basis, ethics
  reference, sensitivity, provenance, and subject count.
- Closing or cancelling the export does not delete either audit trail.

## Data-minimisation defaults

| FastClinic source | Research-zone default |
|---|---|
| Name, phone, email, street address | Excluded |
| National/insurance identifier | Replaced by a project-scoped pseudonym; source never leaves the gateway |
| Date of birth | Age band or year unless protocol requires more precision |
| Exact location | Region or approved geographic aggregation |
| Exact encounter timestamp | Date/month or protocol-approved precision |
| Diagnoses/procedures | Standard code plus minimum required context |
| Clinical notes and AI conversations | Excluded by default; separate high-risk review if ever proposed |
| Guardian/RelatedPerson details | Excluded unless explicitly necessary and legally approved |
| Rare combinations | Suppressed, generalised, or held for manual disclosure review |

Pseudonyms must be tenant-, project-, and purpose-scoped so two unrelated studies
cannot silently link the same person. Re-identification material belongs in a
separate service under narrower access and independent audit.

## FHIR, OMOP, and EHDS seam

- FastClinic owns primary-use mappings such as `Patient`, `RelatedPerson`,
  `Appointment`, `Encounter`, `Condition`, `Procedure`, `Coverage`,
  `PractitionerRole`, `Consent`, and `AuditEvent`.
- A research-export adapter selects and minimises those resources, replaces
  identifiers, removes unsupported references, validates profiles, and emits an
  immutable provenance manifest.
- FastHealthData catalogs the FHIR paths and optional OMOP target concepts, then
  governs access to the resulting research asset.
- OMOP conversion should be a versioned ETL product with data-quality reports;
  a `standard_code` label alone is not conformance.
- EHDS secondary-use integration is a future adapter to the applicable Health
  Data Access Body processes and implementing specifications. The current demo
  does not claim that connection or conformity.

The public FastClinic `/compliance` page remains the source for current design
intent and limitations.

## Required model additions

### FastClinic

- `research_export` — tenant, project reference, purpose, state, requested and
  approved actors, snapshot time, manifest hash, target, retention status.
- `research_export_field` — source field, output field, standard mapping,
  sensitivity, transformation, inclusion decision, justification.
- `research_export_event` — append-only state and delivery evidence.
- Transactional outbox events so API/network failure cannot produce an
  unrecorded or partially registered export.

These tables store governance metadata, not a duplicate research warehouse.

### FastHealthData

- `dataset_version` — immutable versions, schema hash, source system, extraction
  window, record count, object checksum, validation status.
- `intake_job` — expected manifest, upload location, malware/format/profile
  validation, quarantine, acceptance, and rejection evidence.
- `data_asset` — encrypted object references and retention state; never public
  filesystem paths.
- `disclosure_review` — method, thresholds, reviewer, exceptions, decision, and
  released output hash.
- `output` — approved aggregate/model/publication artifacts and withdrawal state.

## Delivery phases

### Phase 0 — API and contract baseline (implemented)

- Typed FastHealthData API and committed OpenAPI schema.
- Public synthetic catalog/aggregate reads.
- Token-gated project, dataset, variable, access, audit, pseudonymisation, and
  k-anonymity workflows.
- Disposable-database tests for governance invariants.

### Phase 1 — Metadata-only FastClinic adapter

- Add FastClinic export and outbox tables.
- Register projects, datasets, and variable mappings idempotently.
- Add integration status to FastClinic Admin and links to FastHealthData.
- Add contract tests against the committed OpenAPI schema.

### Phase 2 — Production pseudonymisation gateway

- HSM/KMS-backed, project-scoped HMAC and key rotation.
- Separately deployed re-identification service with DPO-controlled access.
- Field-level minimisation policy and free-text exclusion.
- EU/EEA-only encrypted intake storage and short-lived workload credentials.

### Phase 3 — Versioned FHIR/OMOP intake

- FHIR R4 export profiles, validation reports, provenance, and referential checks.
- Optional OMOP ETL with vocabulary versions and data-quality dashboards.
- Dataset versions, intake quarantine, checksum verification, and replay safety.

### Phase 4 — Governed access and disclosure

- Federated identity, project membership, RBAC/ABAC, expiry, and revocation.
- Two-person approval for identifiable or exceptional access.
- Disclosure review combining k-anonymity with small-cell suppression,
  differencing checks, and documented expert review.
- Approved output registry and end-to-end incident/audit reconciliation.

## Security and compliance gates

No production row-level transfer until all are true:

- controller/processor roles, research purpose, Article 6 basis, Article 9
  condition, national law, ethics position, retention, and DPIA are documented;
- EU/EEA residency and subprocessors are contractually and technically enforced;
- strong identity, least privilege, approval separation, revocation, logging,
  monitoring, backup, restore, and incident procedures are tested;
- HSM/KMS pseudonymisation and the separate re-identification boundary pass
  threat modelling and penetration testing;
- FHIR/OMOP validation, data quality, provenance, and deletion/withdrawal
  semantics are covered by automated tests and operator runbooks;
- the synthetic-only statement remains visible until a separately assessed
  production environment is ready.

## Explicit non-goals

- No public or general-purpose endpoint for uploading clinical rows.
- No shared FastClinic/FastHealthData database or cross-schema joins.
- No research access based solely on a FastClinic staff login.
- No export of clinical notes or assistant conversations by default.
- No automatic release because `k >= 5` or because data is pseudonymised.
- No claim that metadata tagged “FHIR”, “OMOP”, or “EHDS” is conformant without
  validation evidence.

## Recommended next implementation

Build **Phase 1: metadata-only FastClinic adapter** next. It delivers visible
value—project linkage, a standards-aware catalog, and a governed audit trail—while
keeping the existing synthetic clinical dataset inside FastClinic. The next
decision gate should be the first target research protocol and country, because
that determines the lawful basis, profile, terminology, minimisation, retention,
and approval requirements for any later row-level transfer.
