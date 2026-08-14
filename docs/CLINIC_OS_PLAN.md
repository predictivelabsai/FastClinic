# Clinic OS — gap analysis and build plan

**Status:** proposal, 2026-07-17. Not yet agreed.

**Target (decided 2026-07-17): an open-source human GP clinic.** Veterinary is
not a target. The Provet Cloud REST API is used **as a reference feature model
only** — no Provet adapter will be built.

Compares Provet (reference) against FastClinic today and against reusable modules
in the `Fast*` estate, then sets out a plan to build a **Clinic OS**: a generic,
FHIR R4-shaped core with **pluggable country adapters**, NHS/UK first as the
reference adapter.

Two ideas do the work:

1. **The generic subject/party model (§2).** Not for vet — for **paediatrics**.
   A sixth of FastClinic's patients are minors who cannot be their own
   contactable party, and the current schema says they are.
2. **Generic core, country adapters (§9).** FHIR R4 is international, so it
   belongs in the core. Everything a country layers on top — identifiers,
   profiles, auth, terminology, consent regimes, recall schedules — belongs in an
   adapter. NHS is the reference because it diverges most.

Evidence grades used below:

- **[V]** verified against Provet's own OpenAPI 3.0.3 document
  (`developers.provetcloud.com/restapi/0.1/openapi-schema-01.json`, 554 paths /
  1,112 operations / 136 tags, fetched 2026-07-17), or against this repo's code
  and database.
- **[J]** author's judgement — *not* verified by the research pass. Items 3, 5
  and 6 of the research brief (Provet's sold module set; the FHIR R4 / GP Connect
  / SMART-on-FHIR human contrast; clinic-OS domains beyond a PMS API) returned
  **zero verified claims** and remain open. Everything below touching FHIR or NHS
  integration is [J] and must be checked before it drives a commitment.

---

## 1. The core finding: FastClinic is a veterinary data model with the cardinality pinned to 1

FastClinic's schema is Provet-shaped. This is now evidence, not inference — though
no Provet reference exists anywhere in the repo or git history, so treat it as
convergent lineage rather than a documented port.

Provet's `patient` resource carries `species`, `breed`, `microchip`, `herd_size`,
`not_for_food` — *and also* `insurance`, `insurance_company`, `blood_group`,
`home_department`, `private`, `deceased`, `last_consultation` **[V]**.

FastClinic's `patient` table carries `insurance`, `insurance_company`,
`blood_group`, `home_department_id`, `private`, `deceased_at`,
`last_consultation_id` **[V]** — the same field set with the animal-specific
columns swapped for `nhs_number`. `blood_group` is a genuine veterinary field
(dogs and cats have blood types); it survived the port.

The `item` table still carries `is_dispense_fee_item`, `is_injection_fee_item`,
`no_commissions`, `no_department_rates`, `patient_group_id`,
`parent_linked_item_id` **[V]** — vet-PMS billing concepts.

**The structural difference that matters:**

| | Provet (vet) **[V]** | FastClinic (GP) **[V]** |
|---|---|---|
| `client` | the **owner** — 60 properties, has `patients` array | renamed "the same person's contact record" |
| `patient` | the **animal** — 57 properties | the person |
| cardinality | 1 client : N patients | **1 : 1, pinned** — all 1000 rows |
| encounter | consultation → **N patients, 1 client** | 1 consultation : 1 patient |

`client.patient_count` is `1` for all 1000 rows **[V]** — a vestigial vet column.

### Why the 1:1 collapse is a bug, not a simplification

On FastClinic's own synthetic data **[V]**:

- **176 of 1000 patients are under 16**; 40 are under 5.
- **All 176 have a personal phone number on their own contact record.**

A three-year-old does not have a mobile. The synthetic generator hides the defect
by fabricating a contact record per person; production data would not. The
activation engine would text toddlers about their immunisations.

**Paediatrics is structurally identical to veterinary medicine.** A parent with
three children is an owner with three pets: one contactable, consenting, billable
party; N subjects of care. Provet's 1:N shape is the *correct* shape for the
paediatric cohort already in FastClinic's data. The GP reskin threw away the
cardinality that human primary care actually needs.

---

## 2. The generic model

Two entities and a role. Species-neutral, and correct for GP, paeds, vet,
dentistry, care homes.

```
subject          the body that receives care and accrues care gaps
                 (person | child | animal); holds dob, sex, identifiers,
                 subject_type, and a typed attribute bag for the domain-specific
                 tail (nhs_number | species/breed/microchip)

party            the contactable, consenting, billable entity
                 (name, phone, email, address, per-channel consent)

subject_party_role   N:M   (subject_id, party_id, role, is_primary)
                 role ∈ self | guardian | owner | next_of_kin | payer | carer
```

Degenerate cases fall out:

| Setting | Shape |
|---|---|
| Adult GP | `role=self`, 1:1 — **what FastClinic hardcodes today** |
| Paediatrics | `role=guardian`, 1 party : N subjects |
| Veterinary | `role=owner`, 1 party : N subjects |
| Care home | `role=carer` + `next_of_kin`, N:M |

**The invariant the whole system enforces:**

> Care gaps attach to the **subject**. Messages and consent attach to the
> **party**.

FastClinic's `due_rows()` already joins `patient → client` to fetch a phone
(`web/activation.py:60` **[V]**) — the right shape. The join just needs to stop
being an identity function.

Provet validates the direction: consultation → **N patients, 1 client** **[V,
medium confidence, 2-1 vote]**. A Clinic OS encounter should therefore be
`1 encounter : N subjects : 1 party` — which also models a family appointment or
a care-home round, not just a multi-pet visit.

### FHIR R4 independently arrived at this model — and validates it **[V]**

Researched against the R4 spec 2026-07-17. The model above is not invented; it is
what R4 already does. Three findings pin it down:

**R4 splits subject from party on *referenceability*, not contactability [V].**
`Patient.contact` is an embedded BackboneElement that **cannot be the target of a
Reference**. `RelatedPerson` is a standalone resource whose stated primary purpose
is *attribution*. Use `Patient.contact` to hold a phone number; use
`RelatedPerson` when the party must be *referenced* (as
`Appointment.participant`, `CarePlan.participant`, `Encounter.participant`). The
same human may be both.

`Encounter` enforces the split structurally **[V]**: `Encounter.subject` may
reference only `Patient|Group` — never `RelatedPerson` or `Person` — while
`Encounter.participant.individual` may reference `RelatedPerson`. **A parent
accompanying a child is a participant, never the subject.** That is §2's
invariant, spelled out in the base spec.

**The mapping is exact:**

| This plan | FHIR R4 **[V]** |
|---|---|
| `subject` | `Patient` (`Encounter.subject` may only be Patient\|Group) |
| `subject_party_role` (one row) | **`RelatedPerson`** — `.patient` is `1..1`, the resource's *only* mandatory element |
| `role` | `RelatedPerson.relationship` (`0..*` CodeableConcept) |
| `party` (identity across roles) | `Person` + `Person.link` — **linkage only** |
| `role=payer` | `Coverage.subscriber` / `.policyHolder` (vs `.beneficiary` `1..1` Patient) |

**`RelatedPerson.patient` is `1..1` — a RelatedPerson cannot be shared [V].** A
parent of two children requires **two** RelatedPerson instances; asserting they
are the same human is `Person.link`'s job. And `Person` **SHALL NOT be referenced
by any clinical or administrative resource [V]** — actors are always Patient,
Practitioner or RelatedPerson.

**This dictates the core/adapter seam.** FHIR's wire format is *denormalised*: one
RelatedPerson per (party, subject) pair, with the parent's phone number repeated
on each, and a Person record to say they are one person. Do **not** copy that
shape into the core — it is a serialisation artefact, not a data model. Keep the
core **normalised** (one `party` row, N `subject_party_role` rows) and let the
**FHIR adapter materialise N RelatedPerson + 1 Person on export**. This is the
clearest possible demonstration of why the core/adapter split exists: the core
models the clinic, the adapter speaks the protocol.

**Gotcha to design around [V]:** `RelatedPerson.relationship` is bound at
**PREFERRED** strength only — and R4 names "guardian" as a canonical example
RelatedPerson while **shipping no `guardian` code in that value set**. So role
vocabulary is *necessarily* a country-adapter concern. An untyped RelatedPerson is
conformant; a national profile may tighten the binding without breaking the base
spec. Our `role` enum is ours to own, mapped per-country at the boundary.

**Why R4 makes the adapter architecture viable at all [V]:** base resources are
deliberately thin required spines — `Coverage` mandates only `status`,
`beneficiary`, `payor`; `Encounter` only `status` and `class`. The elements that
actually vary by country (relationship codes, vaccine codes, forecast vocabulary)
are bound at **Preferred or Example** strength. R4 explicitly delegates them to
profiles. The adapter abstraction isn't our idea imposed on FHIR; it is the
extension mechanism FHIR ships.

**Vet, for the record [V]:** `Patient.animal` was **deleted outright in R4** and
animal attributes moved to the `patient-animal` extension (species/breed/
genderStatus), while animals remain within `Patient`'s formal scope. R4 therefore
treats *species* as the variable part (an extension) and the *subject/party split*
as invariant — precisely this plan's thesis, reached independently. Vet is not a
target, but the model does not foreclose it. (Sourcing note: "deleted" and "moved
to the extension" are two documents; the "replaced by" link is an inference.)

### Second axis: the recall catalogue must be cohort-keyed

`pms/catalog.py` today **[V]**:

```python
RECURRING_INTERVALS_DAYS = {"vaccine": 365, "health_plan": 365,
                            "repeat_prescription": 60}
```

Flat, one-size-fits-all, subject-blind. Real recall is keyed on cohort **[J]** —
childhood immunisations at 8/12/16 weeks then 1y and 3y4m; HPV at 12–13; flu
annually at 65+; cervical screening on a 3–5 year cycle for women 25–64; HbA1c
every 6 months for diabetics. Veterinary has the identical shape: puppy course,
annual booster, senior wellness.

Same engine, different parameter table. Generalise to a rules engine keyed on
`(subject_type, age_band, sex, condition)` → interval. That single change is what
makes the product species-neutral, and it is the highest-leverage refactor in the
plan.

---

## 3. Domain gap matrix

Provet operation counts are **[V]**. "Fast\* estate" reflects a full survey of the
18 sibling projects.

| Domain | Provet **[V]** | FastClinic **[V]** | Reusable in estate | Verdict |
|---|---|---|---|---|
| **Reminders / recall** | **13 ops, persisted, multi-channel, recurring, `mark_sent`** | computed on the fly, **never persisted** | — | **Build — the core** |
| **Comms & consent** | `no_sms`/`no_email` + `/client_communication_preferences/` (consent_given, privacy_policy_version, valid_from/to, per-channel rows) | **one boolean, never read** | FastHelpdesk `render_canned()` | **Fix now** |
| Clients & patients | Client 60 props / Patient 57 props; 13 + 77 ops | 1:1 collapsed | — | Remodel (§2) |
| Consultations | 87 ops; complaint, timestamps, status | derived, read-only | — | Build write side |
| **Appointments** | 17 ops (+ `shifttemplate` 18) | **none** | **none** — FastMail `events` is a bare calendar; FastMeet has *no* availability logic | **Build from scratch** |
| Invoicing / payments | Invoices 37 ops + accounting group | `item` revenue only; no invoice header, no AR | **FastERP** `invoices`, `record_payment()`, `post_gl()`, `trial_balance()` | Lift FastERP |
| Inventory / stock | Stock 22 ops | none | FastERP `stock_moves`, `reorder_level` | Lift FastERP |
| Prescriptions | Written prescriptions 19 ops | category label only | — | Build |
| Labs & diagnostics | Laboratory analyses 18 ops | category label only | — | Build |
| Treatment / care plans | Treatment plans 30 + health plans 15/16 | `health_plan` category only | — | Build |
| Referrals | Patient referrals group | category label only | FastESM JSON-schema intake forms; FastHelpdesk SLA timers | Lift |
| Users / staff / permissions | Users 20 ops; role-gated writes | `clinician_id` int, **no table**; single shared admin login in plaintext env var | FastHRM `employees` | Build auth |
| Departments / multi-site | Departments 28 ops; `visible_departments` | `home_department_id` int, no table | — | Build |
| Documents / files | files & attachments | none | FastDrive tree + shares + audit; FastDocs templates/versions | Lift |
| Reporting | `reporting_dimension` slots | Plotly dashboards | FastInsights safe `run_sql`, dashboard composition | Lift |
| Webhooks | **68 triggers**, full CRUD, per-department scoping | none | none | Build if integrating |

### What no sibling provides

1. **Appointment booking with availability / conflict detection.** Absent from
   the entire estate. FastMeet inserts `meetings` rows with no free/busy, no slot
   generation, no conflict check, no working hours, no resources.
2. **Campaign / sequence management.** Nothing anywhere.

These two are the actual scope of "Clinic OS".

### Correction to the estate survey

FastClinic **can** send. `util/sms.py` posts to the live Twilio API and
`util/email.py` to Postmark **[V]** — real HTTP, not stubs. The 15 siblings have
no outbound comms at all. FastClinic is the only project that can reach a real
patient, which is exactly why §4 is urgent. (`util/` is missing from CLAUDE.md's
architecture section — worth adding.)

---

## 4. Phase 0 — consent gate ✅ DONE (2026-07-17)

**Implemented.** `web/consent.py` is now the single source of truth; the three
engines filter at query time and the SMS/email routes gate at send time; the
activation UI states how many contacts are suppressed; `evals/run_eval.py` gained
a `consent` suite (8 cases). Full suite: **119/119 pass** (111 pre-existing + 8
new, no regressions). Measured effect: 209 opted-out patient×service rows (80
distinct patients) were in the reminders pool before the fix; **now zero across
all three engines**.

One judgement call to review: **`followup` is treated as marketing** and
therefore suppressed. A post-visit clinical follow-up may rest on a different
lawful basis and arguably should not be. Suppressing fails closed, which is the
safe default, but if follow-up is reclassified as clinical it must move to a
channel that deliberately bypasses `web/consent.py` — see the scope note at the
top of that module.

The original defect, for the record:

**FastClinic would text patients who opted out of marketing. [V]**

`marketing_opt_out` is generated (`pms/synth.py:141`), imported
(`pms/importer.py:318`), stored on `client` — **and read by nothing**. It appears
in zero queries.

`due_rows()` (`web/activation.py:60`) joins `client` for `c.name`/`c.phone`,
correctly filters `p.deceased_at IS NULL`, and never touches consent. Those rows
flow to `/activation/{engine}/csv` and into the SMS broadcaster, which posts to
real Twilio with no check at the send boundary.

**On current synthetic data: 80 opted-out patients sit in the recurring-service
pool** and would land in the campaign export. The engine excludes dead patients
but not unsubscribed ones.

Fix, smallest first:

1. `SELECT c.marketing_opt_out` + `AND COALESCE(c.marketing_opt_out, 0) = 0` in
   `due_rows()`, `lapsed_rows()`, `followup_rows()`.
2. **Guard at the boundary** in `util/sms.send()` / `util/email.send()` — resolve
   the recipient to a party and refuse on opt-out. A filter in one query is a
   filter someone forgets in the next query; the send path is the chokepoint.
3. Show suppressed counts in the UI ("80 contacts suppressed — opted out"), so
   suppression is visible rather than silent.
4. Add an eval asserting no opted-out contact appears in any campaign export.

Then replace the single boolean with Provet's shape **[V]** — per-channel
(`no_sms`, `no_email`), versioned against a privacy-policy version, time-bounded
(`valid_from`/`valid_to`). That is what a regulator expects to see, and Provet
already models it.

---

## 5. Phase 1 — the generic core ✅ DONE (2026-07-17)

**Implemented.** Data model renamed `patient`→`subject`, `client`→`party`, child
FKs `patient_id`→`subject_id`, link `client_id`→`party_id`; new
`subject_party_role` join derived at import (824 self, 180 guardian). Synth
regenerated so minors share a guardian party — 952 parties for 1000 subjects, 38
sibling families, **zero minors with their own phone**. Catalogue is cohort-keyed
(`recall_interval_days(category, age, gender)`, UK starter set, flat fallback).
User-facing vocabulary kept: routes `/patients`, slash `/patient`, UI "Patient";
the one vet-ism "Client ID" → "Contact ID". Evals: **124/124** (added `model`
suite, 5 invariants). Original design intent below.



Introduce `subject` / `party` / `subject_party_role` (§2), shaped to the verified
R4 mapping. Migrate `patient`→`subject`, `client`→`party`, backfill `role='self'`
for every adult and `role='guardian'` for the 176 minors.

**The synth generator must stop giving children their own phones** — it is
currently manufacturing the very data that hides the defect. Give each minor a
parent `party` with `role='guardian'`, and let siblings share one. That change
alone makes the 1:N path exercised by the eval suite rather than theoretical.

Keep the raw import tables as-is: the importer's 1:1 replica of the export and the
`evals` field-coverage assertion are worth preserving. The generic model is a
layer *above* the replica, not a replacement.

Make `pms/catalog.py` cohort-keyed (§2) — the change that separates the engine
(core) from the schedule (adapter).

**Naming: keep `subject`/`party`/`role` in the core; do not adopt FHIR nouns.**
`Person` in particular is a trap — R4's `Person` is a linkage-only record that
**SHALL NOT be referenced** by any clinical resource, so a core table called
`person` holding the contactable party would invert the spec's meaning. Core
vocabulary is ours; FHIR nouns appear only inside the adapter. The mapping table
in §2 is the contract between them.

Two invariants worth asserting in `evals` as soon as the tables exist, because
both are cheap now and expensive later:

- No `subject` under 16 is its own `party` with `role='self'`.
- Every campaign row resolves to a `party` with a contactable channel and
  consent — extending the Phase 0 consent suite to the new model.

## 6. Phase 2 — close the activation loop ✅ DONE (2026-07-17)

**Implemented** in `web/activation_loop.py` + the "Activation Loop" nav page.
Persisted `reminder` (per-subject, per-channel bodies, recurring with a
Provet-style `mark_sent` that rolls the next occurrence forward) and an immutable
`communication` log recording every send attempt — **sent, failed, or blocked** —
with party/subject resolution and provider message id. Enqueue turns due rows into
reminders idempotently; `attribution(within_days)` joins the log to the read-only
replica to measure return visits. Operational state lives in a **separate
writable ops DB** (`fastclinic_ops.sqlite`) so re-importing the PMS replica never
wipes it. The SMS/email routes now log through here, so the consent block is
recorded, not just refused. Evals: **129/129** (added `loop` suite, 5 checks).
Design intent below.



Today the loop is **open**: FastClinic drafts messages and exports CSV but never
records that a reminder was sent. No `reminder` table, no communication log, no
outcome. It cannot suppress duplicates, attribute a return visit to a nudge, or
measure activation — the one thing the product claims to do.

Provet's Reminder is the reference **[V]**: per-channel bodies
(`email_subject`/`email_text`, `sms_text`, `post_text`), `send_method`,
`send_before`, `planned_sending_date`, `expiry_date`, `status`, recurrence
(`recurring_type`/`recurring_times`/`recurring_interval`), links to patient +
client + `reminder_template`, and a **`mark_sent`** transition.

Build: `reminder` (persisted, per-subject, per-channel, recurring) →
`communication` (what was actually sent, to which party, when, provider message
id) → outcome attribution (did a qualifying visit follow within N days?). Reuse
FastHelpdesk `render_canned(body, ticket)` for merge fields.

This is what turns a marketing cockpit into an activation OS, and it is
independent of the country question.

### Shape it to `ImmunizationRecommendation` — for the vaccine slice only **[V]**

FHIR R4 **does** have a canonical way to say "patient is due for X" — but only for
immunisation, and only structurally:

- **`ImmunizationRecommendation`** is the dedicated resource, scoped explicitly
  cross-discipline / cross-setting / cross-region **[V]**.
- **`forecastStatus` is `1..1` and a *modifier element*** — you cannot instantiate
  one without asserting `due | overdue | immune | contraindicated | complete`
  **[V]**. That is FastClinic's `_status()` function, standardised.
- **`recommendation.dateCriterion`** (`0..*`, `code` `1..1` + `value` `1..1`
  dateTime) carries the timing windows — a direct map onto the engine's
  due/overdue interval maths **[V]**.
- Constraint `imr-1`: `vaccineCode` OR `targetDisease` **[V]**.

**Critical limit [V]: every binding on `.recommendation` is EXAMPLE strength.**
R4 standardises the *structure* of a recall engine and fixes **no vocabulary** —
which is exactly why §2's cohort catalogue is a country-adapter concern.

**And there is no canonical equivalent for the rest.** Cervical/bowel/AAA
screening, health checks and repeat-prescription review have no dedicated "due"
resource; they fall to `CarePlan` / `Task` / `CommunicationRequest`. So the
`reminder` table stays bespoke and country-neutral, with the FHIR adapter
projecting the vaccine slice to `ImmunizationRecommendation` and the rest to
`Task`/`CommunicationRequest`. Do not contort the core to fit a resource that
only covers a third of the problem.

## 7. Phase 3 — appointments ✅ DONE (2026-07-17)

**Implemented** in `web/appointments.py` + `web/appointments_views.py` + the
"Appointments" nav page. Slot generation from a clinician working pattern
(Mon–Fri, 09:00–17:00, 20-min slots, lunch blocked), **conflict detection** that
refuses to double-book a clinician (cross-clinician same-time allowed), RSVP-style
statuses (scheduled/confirmed/cancelled/completed), a day schedule + booking form
+ upcoming list, and a hook that queues a Phase-2 appointment reminder on booking.
Evals: **135/135** (added `appointments` suite, 6 checks). Design intent below.



Build from scratch (nothing to lift). Slot generation from clinician working
patterns, conflict detection, resources/rooms, RSVP-style confirmation states
(FastMeet's `RSVPS` vocabulary is the one reusable scrap), reminder hooks into
Phase 2. FastMail's month grid (`web/views.py:242`) is the UI starting point.

## 8. Phase 4 — money ✅ DONE (2026-07-17)

**Implemented** in `web/billing.py` + `web/billing_views.py` + the "Billing" nav
page. Adapted FastERP's finance code: per-consultation fee invoices, partial +
full payments, and a **double-entry general ledger** (`Accounts Receivable` /
`Cash` / `Fee Income`) that stays balanced through every transaction. The payer is
resolved as a **party with `role=payer`, else the primary party** — so a minor's
invoice bills the guardian party, demonstrating billed-party ≠ treated-subject.
Invoices + ledger live in the ops DB. Evals: **141/141** (added `billing` suite,
6 checks). Design intent below.



Lift FastERP wholesale: `invoices`, `record_payment()`, `post_gl()`,
`trial_balance()`, `ACCOUNTS`. Rename `Sales Revenue` → `Fee Income`. Attach
invoices to encounters; the payer is a **party with `role=payer`** — which is how
insurance and a parent paying for a child's treatment fall out of the same model.

## 9. Phase 5 — interoperability: generic core + country adapters

### Phase 5a — FHIR R4 shaping ✅ DONE (2026-08-14)

**Implemented** in `web/fhir/`. The core stays normalised; this package
materialises vanilla R4 at the boundary. `GET /api/v1/fhir/metadata`,
`GET /api/v1/fhir/{type}/{id}`, `GET /api/v1/fhir/Patient/{id}/$everything`,
`POST /api/v1/fhir/$validate`, and `POST /api/v1/fhir/$import`. Admin preview at
`/admin/fhir`. Evals: `fhir` suite. Design intent below.

### Phase 5b — NHS adapter (mapping) ✅ DONE (2026-08-14); live spine still gated

**Implemented** in `web/adapters/nhs/`, version-split as designed:

- `identifiers.py` — NHS Number modulus 11 (no network)
- `profiles.py` — UK Core R4 profiles + GP Connect STU3 translation
  (including R4 `dateCriterion` → STU3 `recommendation.date`)
- `live.py` — PDS / GP Connect / spine write-back raise `AdapterNotAvailable`
  until `NHS_LIVE_ENABLED` and onboarding credentials exist

`GET /api/v1/adapters/GB/status`, `POST .../verify-identifier`,
`GET .../subjects/{id}?release=r4|stu3`, `POST .../import`,
`GET .../reminders/{id}`. Live PDS/GP Connect remain **unschedulable** until
§10 Q1 is answered by NHS England onboarding. The mapping layer does not
depend on that answer.

**Decided 2026-07-17:** the target is an **open-source human GP clinic**. Provet
is a **reference model only — no Provet adapter will be built.** Everything
Provet contributes to this plan is conceptual: the corrected cardinality (§2),
the Reminder shape (§6), and the consent model (§4). Its OAuth/tenancy/rate-limit
constraints are now irrelevant and have been dropped.

The architecture is instead:

```
              ┌─────────────────────────────┐
              │   FastClinic generic core   │   subject / party / role  (§2)
              │   (FHIR R4 - shaped)        │   encounter, reminder, appointment
              └──────────────┬──────────────┘
                             │  port (interface), not a protocol
       ┌─────────────────────┼─────────────────────┐
       │                     │                     │
  ┌────┴─────┐         ┌─────┴──────┐        ┌─────┴─────┐
  │   NHS    │         │    US      │        │   EU/AU   │
  │ adapter  │         │  adapter   │        │  adapter  │   ← future
  │(reference)│        │            │        │           │
  └──────────┘         └────────────┘        └───────────┘
  GP Connect, IM1,     SMART on FHIR,        EHDS, My Health
  NHS App, PDS,        US Core, USCDI        Record, AU Core
  NHS login
```

**The load-bearing design rule:** FHIR R4 is the *generic* layer — it is an
international standard, so it belongs in the core, not in an adapter. What goes
in an adapter is everything a country adds *on top* of R4: identifier systems
(NHS Number vs MRN), national profiles (UK Core vs US Core), auth (NHS
login / SSP vs SMART on FHIR), terminology bindings (SNOMED CT + dm+d vs RxNorm),
consent regimes, and the recall/screening cohort rules (§2's cohort-keyed
catalogue is **country-specific** — the UK childhood immunisation schedule is not
universal).

NHS is the reference adapter because it is the hardest: it is the one that
diverges most from vanilla R4.

**Sequencing within Phase 5 — the core is not blocked on the adapter.** Shape the
generic core to R4 first; it is useful on its own (a clinic that never touches
the NHS still gets a standards-shaped record). The NHS adapter follows and is
gated on the assurance questions in §10.

### The UK seam: GP Connect and UK Core are on different FHIR versions **[V, medium]**

The single most consequential UK finding, and it contradicts the assumption the
plan started with:

> **GP Connect Access Record: Structured is STU3. UK Core is R4 (4.0.1).**

They are **not version-compatible**. The NHS catalogue's stated rationale for
GP Connect being STU3 — that it is *"aligned with FHIR UK Core, which is built on
FHIR Release 3"* — is **false**: UK Core is built on R4 and always has been
**[V, medium confidence, 2-1 vote; core assertion confirmed via a stronger
primary source than the one cited, while the cited rationale was refuted]**.

Consequences for the NHS adapter, all load-bearing:

1. **The NHS adapter is a translation layer, not a pass-through.** Core (R4) ↔
   GP Connect (STU3) requires real resource mapping. Budget for it.
2. **The NHS adapter is internally version-split.** A single "NHS adapter" must
   speak STU3 to GP Connect *and* R4 to UK Core–profiled surfaces. The country
   adapter's internal seam is by *service*, not by country. Design it as
   `adapters/nhs/gpconnect_stu3/` + `adapters/nhs/ukcore_r4/`, not one blob.
3. **Do not take NHS documentation's stated reasoning at face value.** A published
   rationale on the NHS catalogue was verifiably wrong about NHS's own standard.
   Verify against the profiles themselves (simplifier.net), not the prose.

Still unverified for the NHS surface: the other GP Connect capability packs
(Access Record HTML, Appointment Management, Send Document) and their versions;
SSP/JWT auth specifics; IM1 (Pairing/Bulk/Transactional) and its eligibility;
NHS App and NHS login; PDS/SDS. **Two research passes have now failed to return
verified evidence on these** — see §10 Q1.

Known false-friend: do **not** treat FastHealthData as a head start. Its
FHIR/OMOP support is **metadata tags only** (`standard`, `standard_code`) — no
client, no CDM DDL, no terminology server **[V]**.

---

## 10. Open questions

**Resolved 2026-07-17:** vet is *not* a target; Provet is a reference model only.
The generic subject/party model (§2) survives that decision unchanged — it is
justified by the 176 paediatric patients alone, with no vet ambition needed. The
Provet-adapter questions (reminder-rule configurability, `last_consultation`
filterability, role-permission granularity) are closed as moot.

**Answered 2026-07-17 by the FHIR research pass:**

- *Does R4 model the subject/party split natively?* **Yes, exactly** — and the
  mapping is now in §2. `RelatedPerson.patient` `1..1` is the join row; `Person`
  is linkage-only; `Encounter.subject` may only be `Patient|Group`. The core
  stays normalised and the adapter denormalises.
- *Which FHIR version is GP Connect?* **STU3, while UK Core is R4** — see §9. The
  NHS adapter is a translation layer, and must be internally version-split.
- *Is there a canonical "due for X"?* **Only for immunisation**
  (`ImmunizationRecommendation`, structure only, no vocabulary) — see §6.

Still open:

1. **Can an open-source system actually connect to GP Connect / IM1 / NHS App?**
   ⚠️ **Two research passes have now returned zero verified evidence on this.**
   It remains the binding constraint on Phase 5b, and it is the direct analogue
   of the partner gating that Provet turned out to have. Expect DCB0129/DCB0160
   clinical safety, DTAC, DSPT, possibly GPIT Futures supplier status. **If the
   GP Connect sandbox is approval-gated, the NHS adapter cannot be developed in
   the open at all** — which changes the roadmap's shape, not just its timeline.

   **Do not commission a third broad research pass.** The repeated failure
   suggests this is not answerable from indexed public documentation. Resolve it
   by *direct contact*: NHS England's GP Connect team / `api.service.nhs.uk`
   onboarding, asking one concrete question — *can a non-supplier open-source
   project obtain sandbox credentials, and what does production access require?*
   Until answered, treat 5b as **unschedulable**, not merely unscheduled.

2. **What are the other GP Connect packs, IM1 tiers, and NHS App/PDS surfaces?**
   Also unreturned by both passes. Fold into the same conversation as Q1.

3. **Is `followup` marketing or clinical?** (§4.) Currently suppressed as
   marketing — fails closed, but it is a product/legal call to confirm.

4. **Port collisions in the estate** (ops, unrelated to this plan): 5011
   FastCity/FastERP, 5013 FastHealthData/FastSlides, 5015
   FastESM/FastGrants/FastMeet, 5001 FastCMS/FastLCA/FastLMS. FastClinic (5005)
   and FastDocs (5016) are clear.

---

## Sequencing summary

| Phase | Scope | Why now |
|---|---|---|
| **0** | Consent gate | Live PECR/GDPR exposure; hours of work |
| **1** | subject/party/role + cohort-keyed catalogue | Fixes the 176 paediatric patients; the model FHIR expects |
| **2** | Persisted reminders + comms log + outcomes | Makes the core claim measurable |
| **3** | Appointments + availability | Largest greenfield build; nothing in the estate to lift |
| **4** | Invoices/payments/GL (lift FastERP) | Cheap; mostly a port |
| **5a** | Shape the core to FHIR R4 | ✅ vanilla R4 read surface |
| **5b-map** | NHS adapter mapping (UK Core R4 + GP Connect STU3 + NHS Number) | ✅ offline |
| **5b-live** | Live PDS / GP Connect / IM1 / NHS App | **Gated on §10 Q1 — assurance may block open development** |

Phases 0–5a and the NHS *mapping* layer are unblocked and country-neutral. Only
**5b-live** depends on NHS gatekeeping. If onboarding proves closed to an
open-source project, 0–5b-map still stand and another country's adapter can
go first.

Adapter seam: `web/adapters/base.py` (the `CountryAdapter` port) +
`web/adapters/registry.py` + `web/adapters/nhs/` (implemented mapping; live
calls gated) + `docs/adapters/NHS_GP_CONNECT.md`.

---

## Decision log

- **2026-07-17 — target = open-source human GP clinic.** Vet is not a target;
  Provet is a reference model only, no adapter. (§9)
- **2026-07-17 — full rename, layered.** Data model renames to
  `subject`/`party`/`subject_party_role`; **user-facing vocabulary stays
  "Patient"/"Contact".** Rationale: "patient" is the GP adapter's *rendering* of a
  generic `subject` (as "animal" would be the vet rendering), so routes
  (`/patients`), slash commands (`/patient`), and UI labels keep the clinical word
  — only the model layer goes generic. This also keeps the route/shortcut/chat
  eval suites valid.
- **2026-07-17 — build scope this session: Phases 1–4.** Regenerate synthetic data
  with guardian parties; representative (not comprehensive) UK cohort catalogue.

## Appendix A — Phase 1 implementation plan (the next build)

Goal: introduce the generic `subject` / `party` / `subject_party_role` model as
an **additive layer above** the raw import replica, fix the paediatric data that
hides the 1:1 bug, and make `pms/catalog.py` cohort-keyed — without breaking any
existing query, route, or eval.

### A.1 Schema (new tables, derived at import; raw `patient`/`client` untouched)

```
subject(id, patient_id→patient.id, subject_type, dob, sex, ...)   -- the body
party(id, name, phone, email, marketing_opt_out, ...)             -- the contact
subject_party_role(subject_id, party_id, role, is_primary)        -- N:M join
    role ∈ self | guardian | owner | next_of_kin | payer | carer
```

Built in `pms/importer._build_derived()` alongside the existing `consultation` /
`client` derivations. Idempotent, same as today.

### A.2 Backfill rule (deterministic, from existing data)

- Adult (`dob ≤ ref − 16y`): one `party` = the person; `role='self'`,
  `is_primary=1`.
- Minor (`dob > ref − 16y`, 176 rows): a **guardian `party`**; `role='guardian'`.
  The minor does **not** become their own party.

### A.3 Synth generator (`pms/synth.py`) — stop manufacturing the bug

Today it gives every person, including toddlers, their own phone — which is what
hides the defect. Change: minors get a parent contact; **siblings share one
parent** so the 1-party-N-subject path is real, not theoretical.

### A.4 Consumption — one seam, minimal churn

Add `subject_party()` resolver in `web/` returning the *contactable* party for a
subject. Point `web/consent.py` and the activation engines at it. Existing
`patient`/`client` queries keep working; the resolver is the migration boundary.

### A.5 Cohort-keyed catalogue (`pms/catalog.py`)

Replace the flat `RECURRING_INTERVALS_DAYS` dict with rules keyed on
`(subject_type, age_band, sex, condition) → interval`. Ship a **UK starter set**
(childhood immunisation milestones, adult flu 65+, a cervical-screening cycle),
explicitly marked as the *UK adapter's* schedule — the engine is generic, the
schedule is country data. Keep the old flat intervals working as the default rule
so nothing regresses.

### A.6 Evals (extend the harness, gate the invariants)

New `model` suite asserting: no subject <16 has `role='self'`; every subject has
exactly one primary contactable party; the consent suite still passes against the
resolver; the field-coverage check still passes (raw replica unchanged).

**Out of scope for Phase 1:** persisted reminders (Phase 2), appointments (3),
money (4), any FHIR wire output (5a). This phase changes the data model and the
recall keying only.
