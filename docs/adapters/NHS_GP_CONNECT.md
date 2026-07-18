# NHS / GP Connect adapter — design stub (NOT BUILT)

**Status:** documented seam only. No implementation. `web/adapters/nhs_gpconnect.py`
raises `AdapterNotAvailable` on every call by design. Do not wire it into the app.

This records *what* the NHS adapter would be and *why it is not being built now*,
so the decision is legible and the work has a defined shape if the gate clears.

See `docs/CLINIC_OS_PLAN.md` §9 (interoperability architecture) and §10 Q1 (the
assurance gate) for the surrounding plan.

---

## Why a stub and not code

Building the NHS surface is blocked on one question that **two deep-research
passes could not answer from public documentation**:

> Can a non-supplier, open-source project obtain GP Connect sandbox credentials,
> and what does production access actually require?

The repeated failure is itself the signal: this is not answerable from indexed
public docs. It should be resolved by **direct contact** with NHS England API
onboarding, not a third research pass. Until answered, the adapter is
**unschedulable** — not merely unscheduled.

Expected gates (unverified specifics — confirm during onboarding):
DCB0129 / DCB0160 clinical-safety, DTAC, DSPT (Data Security & Protection
Toolkit), and possibly GPIT Futures / Digital Care Services supplier status.

**Nothing else in the roadmap depends on this.** Phases 0–5a (consent, generic
core, activation loop, appointments, money, FHIR R4 shaping) are all
country-neutral and proceed without it.

---

## The seam it plugs into

`web/adapters/base.py` defines `CountryAdapter` — a country-neutral port. The NHS
module is one implementation of it; a US (SMART on FHIR / US Core) or AU (AU Core)
adapter would be siblings. The core calls the port; it never imports a national
module directly.

Port methods (see `base.py` for signatures): `verify_identifier`,
`export_subject`, `import_record`, `push_reminder`.

---

## Verified constraints to honour when built

Grades: **[V]** = confirmed against a primary source (HL7 R4 spec / NHS).

### 1. GP Connect and UK Core are on different FHIR versions **[V, medium]**

> **GP Connect "Access Record: Structured" is STU3. UK Core is R4 (4.0.1).**

They are **not** version-compatible. Two consequences:

- The adapter is a **translation layer**, not a pass-through: core-R4 ↔
  GP-Connect-STU3 needs real resource mapping.
- The adapter is **internally version-split by service**. Structure it as two
  sub-packages, not one:
  - `adapters/nhs/gpconnect_stu3/` — GP Connect capability packs (STU3)
  - `adapters/nhs/ukcore_r4/` — UK Core-profiled surfaces, PDS (R4)

The NHS catalogue's stated rationale for STU3 (*"aligned with UK Core, which is
built on FHIR R3"*) is **factually wrong** — UK Core is R4 and always has been.
**Verify against the profiles on simplifier.net, not NHS narrative prose.**

### 2. Relationship codes are the adapter's job **[V]**

`RelatedPerson.relationship` is bound at **PREFERRED** strength only, and base R4
**ships no `guardian` code**. So the core `role` enum
(`self|guardian|owner|next_of_kin|payer|carer`) is authoritative and is mapped to
national codes *here, at the boundary*. National codes must never leak into the
core.

### 3. Core is normalised; FHIR is denormalised — the adapter converts **[V]**

`RelatedPerson.patient` is `1..1`, so a parent of two children becomes **two**
RelatedPerson instances plus a `Person` link record. That denormalisation is a
wire-format artefact. The core keeps one `party` + N `subject_party_role` rows;
`export_subject` fans them out, `import_record` re-normalises. `Person` is
**linkage-only** and SHALL NOT be referenced by clinical resources.

### 4. Recall has a canonical form only for vaccines **[V]**

`ImmunizationRecommendation` is the dedicated "due for X" resource
(`forecastStatus` `1..1`, a modifier element = the engine's due/overdue status),
but **structure only — every binding is EXAMPLE strength**. Screening,
health-check and repeat-prescription recalls have no dedicated resource and map to
`Task` / `CommunicationRequest`.

---

## Unverified — resolve during onboarding

Neither research pass returned verified evidence on these; do not assume:

- Other GP Connect capability packs (Access Record HTML, Appointment Management,
  Send Document) and their FHIR versions.
- Auth: Spine Security Proxy (SSP), JWT specifics.
- IM1 (Interface Mechanism): Pairing vs Bulk vs Transactional, eligibility, and
  how it differs from GP Connect.
- NHS App / NHS login integration and its IM1 dependency.
- PDS / SDS environments (sandbox / integration / production) and auth patterns
  (application-restricted, healthcare-worker, patient-access via NHS login).

## First action if this is picked up

Email NHS England API onboarding (`api.service.nhs.uk`) / the GP Connect team with
the single concrete question in "Why a stub", and confirm which surfaces have a
publicly accessible sandbox before any code is written.
