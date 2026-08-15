::: cover

# FastClinic

#### User Guide — Run Your Multi-Specialty Clinic

**Modern clinical care, made personal.**

General practice · surgical specialties · dental · patient activation

Version {{GUIDE_VERSION}} · {{GUIDE_DATE_LONG}} · **fastclinic.dev**

:::

---

## Contents

The PDF page numbers and PowerPoint slide numbers are intentionally identical.

| Component | Pages / slides | What it covers |
|---|---:|---|
| **Get started** | 3–6 | Overview, sign-in, layout, and Copilot |
| **Run the clinic** | 7–14 | Treatments, appointments, patients, clinical, revenue, and billing |
| **Keep patients in the loop** | 15–19 | Recall, lapsed patients, follow-up, and measured outreach |
| **Reach, automate & integrate** | 20–25 | Communications, AI, web presence, API, and data operations |
| **Compliance & interoperability** | 26–30 | Current posture, GDPR path, FHIR/EHDS, and national adapters |
| **Run it every week** | 31–33 | Weekly operating rhythm and quick reference |

---

::: divider

## Get started

Orient the team around one operations cockpit, one consistent layout, and one
assistant grounded in clinic data.

:::

---

## FastClinic at a glance

![Overview](img/01-overview.png)

**FastClinic** is an open-source operations platform for European private
multi-specialty clinics. The Overview is the daily scorecard: active and total
patients, visits, revenue, service mix, and trends—all dated so the team knows
how fresh the picture is.

The platform combines **real availability and conflict-safe appointments**,
patient and contact-party operations, recall, communications, balanced billing,
multi-specialty analytics, and an AI assistant. The public demo contains only
synthetic records; it is designed for safe exploration rather than clinical use.

---

## Sign in & the three-pane layout

![Sign in](img/00-login.png)

Open **https://fastclinic.dev** and choose **Sign In**. Use the account method
configured for your clinic; the public demo may offer local or Google sign-in.

- **Left** — navigation grouped by job: Overview, Operations, Recall &
  Scheduling, Communications, Help, and Admin.
- **Centre** — the active workspace: dashboards, lists, forms, and reports.
- **Right** — the collapsible **AI Copilot**, available without leaving the
  current task.

The public landing page, account flow, compliance page, developer page, app,
chat, and dashboards support the same European language catalogue.

---

## The AI Copilot — just ask

![AI Copilot](img/02-copilot.png)

The Copilot turns plain-language questions into answers grounded in FastClinic's
tools and current conversation. Ask *“Which specialties bring in the most
revenue?”*, *“How many surgical cases did we run?”*, or *“Who is due for recall?”*

- Conversation history is checkpointed per account and thread, with bounded
  retention and context limits.
- The selected request language is propagated into agent tool execution so the
  answer and underlying labels stay aligned.
- Slash commands provide deterministic pulls: `/kpi`, `/due`, `/lapsed`,
  `/followup`, `/revenue`, and `/patient <id>`.

The assistant is scoped to operations and information retrieval; it is not a
diagnostic or treatment-recommendation system.

---

::: divider

## Run the clinic

Plan work, protect availability, understand the patient base, and keep the
financial record balanced across every specialty.

:::

---

## Treatments & Specialties — the case-mix lens

![Treatments & Specialties](img/18-treatments.png)

Every treatment line is classified on two axes: **what was delivered**
(consultation, surgery, dental, diagnostic, procedure, and more) and **which
specialty delivered it**.

Use this view to compare revenue and case volume across general practice,
orthopaedics, ophthalmology, ENT, general surgery, gynaecology, urology,
dermatology, plastics, cardiology, gastroenterology, dental, and diagnostics.
Surgical throughput and top procedures make the operational mix visible without
flattening the clinic into a single revenue total.

---

## Appointments & booking

![Appointments](img/07-appointments.png)

Book into **real clinician availability**. Choose a clinician and date to see
free and occupied slots, then create, confirm, reschedule, complete, or cancel an
appointment.

- Conflict detection prevents the same clinician being double-booked.
- A parallel slot can remain available for another clinician.
- Booking changes retain operational history and can queue reminders.
- The integration API exposes availability and idempotent external reservation
  primitives for booking adapters.

---

## Patients, contacts & representatives

![Patients](img/08-patients.png)

The searchable patient register shows visit count, last-seen date, and lifetime
value. FastClinic deliberately separates the **subject of care** from the
**contactable or billable party**.

That model supports a patient acting for themselves, a guardian representing a
minor, a family contact, an emergency contact, or a separate payer. Consent,
communications, and invoices are attributed to the correct party instead of
assuming the patient is always directly contactable.

---

## Patient profile

![Patient profile](img/09-patient.png)

The profile brings together demographics, representatives, lifetime value,
visit count, consultation history, diagnoses, notes, and recent billable items.

Use it before a call or visit to understand the relationship context as well as
the care history. API mutations follow domain-safe behaviour: clinical subjects
and notes are archived instead of silently erased, and linked parties cannot be
deleted until their relationships are resolved.

---

## Clinical operations

![Clinical](img/10-clinical.png)

The Clinical view summarises common diagnoses and clinician activity across the
practice. It is an operational workload and service-planning lens—not clinical
decision support.

Use it to identify capacity pressure, recurring condition cohorts, and where
follow-up programmes may be useful. Imported diagnoses and performed-care facts
remain traceable to their synthetic consultations.

---

## Revenue

![Revenue](img/11-revenue.png)

Revenue is shown by month, service category, specialty, and top procedure. Pair
it with Treatments & Specialties to understand both the money and the work behind
it.

The analytics endpoints expose the same synthetic aggregates used by the
dashboard, so an authorised integration can reconcile its reports against the
user interface.

---

## Billing & payments

![Billing](img/12-billing.png)

Raise invoices from consultations, record part or full payments, issue refunds,
and void invoices through reversing entries. A **balanced double-entry ledger**
keeps every billed and collected amount accounted for.

Because payer and patient are separate, a guardian or insurer can pay for a
subject of care naturally. API idempotency keys prevent the same payment being
recorded twice, while the audit trail records operational mutations.

---

::: divider

## Keep patients in the loop

Turn due care, lapsed relationships, and recent visits into reviewable,
consent-aware outreach with measurable outcomes.

:::

---

## Recalls Due

![Recalls Due](img/03-reminders.png)

Recalls Due surfaces who is due or overdue for recurring services such as
immunisations, health checks, and repeat-prescription reviews. Rows are ranked by
urgency and include a drafted message.

Intervals can account for age and cohort. Filters and CSV/XLS exports let the
team review the cohort before queuing anything. No campaign is sent merely
because a person appears in a list.

---

## Lapsed Patients

![Lapsed Patients](img/04-lapsed.png)

Lapsed Patients finds people with no visit inside a chosen window and ranks them
by lifetime value. Adjust the period to narrow or widen the cohort.

The view supports a deliberate win-back workflow: verify the relationship and
contact channel, review the drafted message, respect purpose and opt-out rules,
then measure whether outreach resulted in a return visit.

---

## Post-Visit Follow-up

![Post-Visit Follow-up](img/05-followup.png)

Post-Visit Follow-up lists recent visits—including post-procedure reviews—within
a chosen 7, 14, 30, or 60-day window.

Use it for operational check-ins, recovery calls, review requests, or rebooking.
Marketing and necessary clinical follow-up must be treated as distinct purposes;
deployment policy determines the correct lawful basis and channel.

---

## The Recall Loop — queue, send, measure

![Recall Loop](img/06-loop.png)

Queue reviewed cohorts as persistent reminders. Every communication attempt is
logged as sent, failed, or blocked, and marketing opt-outs are enforced at the
point of delivery.

The loop tracks pending work, delivery outcomes, blocked contacts, and the
30-day return rate. This provides an operational record of what the clinic did,
not merely a static export of who appeared eligible.

---

::: divider

## Reach, automate & integrate

Connect approved communication providers, use the assistant responsibly, expose
typed APIs, and keep clinical and operational stores under control.

:::

---

## SMS & Email

![SMS](img/13-sms.png)

Send through configured SMS and email providers after reviewing the recipient,
purpose, and message. FastClinic suppresses opted-out marketing contacts at send
time and retains immutable delivery outcomes.

Provider contracts, data location, processor terms, retention, and transfer
controls remain deployment decisions. In environments without a configured
provider, cohorts can still be exported for an approved clinic workflow.

---

## AI Assistant

![AI Assistant](img/15-ai.png)

The full-page assistant supports deeper operational questions across revenue,
scheduling, patients, and recall. Its agent tools are read-oriented and its
evaluation suite checks grounding, tool routing, supported languages, privacy,
prompt injection, safety, robustness, streaming, and memory.

Before real patient data is introduced, clinics must resolve the model provider,
EU/EEA processing location, contracts, minimisation, retention, human oversight,
and international-transfer position.

---

## Web Presence

![Web presence](img/16-seo.png)

The audit suite checks how the clinic appears in search and AI answer engines,
then writes dated reports for review. It complements patient retention with a
top-of-funnel view of how prospective patients discover the clinic.

Keep published clinical claims, pricing, professional credentials, and privacy
notices under human approval; the audit identifies issues but does not publish
changes automatically.

---

## Developer API

| Surface | Location | Access model |
|---|---|---|
| Human guide | `https://fastclinic.dev/developers` | Public |
| Swagger UI | `/api/docs` | Public documentation |
| OpenAPI | `/api/openapi.json` and `/swagger.json` | Public schema |
| Clinical reads & analytics | `/api/v1/...` | Public synthetic reads |
| Clinical CRUD | Patients, parties, relationships, notes | Bearer token |
| Operations | Appointments, recall, communications, billing, audit | Bearer token |
| Patient mobile | `/api/v1/mobile/*` | MedBackend OAuth 2.0 + PKCE |

The API is typed and versioned. Destructive verbs use domain-safe semantics:
archive, cancel, refund, or reverse rather than bypassing clinical and financial
history. FastBooking uses a separate least-privilege token.

The patient mobile contract includes identity/bootstrap, Assistant and
Classical booking, own appointment cancellation/rescheduling, and owned FHIR R4
JSON/XML records. Patient identity always comes from the verified OAuth token,
not a submitted identifier. See `docs/mobile_app_api.md` for the native-client
flow and security requirements.

---

## Data, import & database backends

![Data & Import](img/17-data.png)

The synthetic clinical model can run on **SQLite** or **PostgreSQL**. Production
PostgreSQL data is isolated in the `fast_clinic` schema; operational state such
as chat, appointments, reminders, billing, and audit records remains separately
configured.

The migration verifies table counts, subject/party relationships, orphan checks,
and the treatment-revenue checksum before commit. The public demo and repository
continue to contain synthetic data only—no PHI.

---

::: divider

## Compliance & interoperability

FastClinic's Europe-first design approach, current limitations, and potential
FHIR/EHDS integration path. See **fastclinic.dev/compliance** for the full public
statement.

:::

---

## Compliance posture — current vs planned

**Available today**

- Synthetic public demo and repository; no PHI.
- Separate subject-of-care and party/representative model.
- Consent-aware communications, mutation audit events, persistent conversation
  history, typed API, and balanced accounting.

**Required before production health-data deployment**

- Enforceable EU/EEA data residency, encryption and key management, fine-grained
  RBAC, MFA/SSO paths, append-only audit evidence, retention and legal holds.
- DPIA and processing records, processor agreements, incident procedures,
  backup/recovery evidence, and national legal review.

FastClinic does **not** currently claim ISO 27001/27701 certification, production
EHR conformity, or automatic legal compliance for a deploying clinic.

---

## GDPR integration approach

FastClinic is designed to give the clinic controller usable controls and the
processor relationship auditable evidence.

| Concern | Product / adapter approach |
|---|---|
| Privacy by design | Minimise data, isolate environments, apply least privilege and secure defaults |
| Lawful purpose | Keep health-care operations distinct from marketing consent and opt-out |
| Patient rights | Locate, explain, export, restrict, rectify, or erase where legally permitted |
| Representatives | Route minors and represented adults through the authorised party relationship |
| Retention | Country-configurable schedules and legal holds; erasure is not absolute for clinical records |
| Incidents | Structured logs and monitoring to support risk assessment and notification workflows |
| AI processing | Resolve provider location, contracts, transfers, minimisation, retention, and oversight first |

Legal basis, national retention duties, controller responsibilities, and whether
a DPO is required remain deployment-specific decisions.

---

## FHIR R4 & EHDS integration approach

FastClinic keeps a **normalised internal core** and places FHIR profiles,
national identifiers, terminology, transport, and consent rules in adapters.

| FastClinic concept | Potential FHIR R4 boundary mapping |
|---|---|
| Subject of care | `Patient` |
| Guardian or contactable party | `RelatedPerson` / `Patient.contact` |
| Appointment and visit | `Appointment` / `Encounter` |
| Diagnosis and performed care | `Condition` / `Procedure` |
| Payer and coverage | `Coverage` / `Organization` |
| Clinician and clinic | `Practitioner` / `PractitionerRole` / `Organization` |
| Consent and audit evidence | `Consent` / `AuditEvent` |

FHIR R4 is the planned interoperability spine; conformant FHIR import/export,
EHDS exchange-format support, and production national connections are roadmap
work—not capabilities claimed by the current synthetic demo.

---

## National adapters & primary references

Potential adapters will materialise country-specific identifiers, profiles,
terminology, professional identity, consent, and transport without contaminating
the generic core.

| Market | Discovery target | Primary reference |
|---|---|---|
| Estonia | TEHIK health information system / upTIS | [TEHIK](https://www.tehik.ee/en/health-information-system) |
| Finland | Kanta FHIR transition and national profiles | [Kanta](https://www.kanta.fi/en/system-developers/fhir-technology-and-kanta) |
| Germany | gematik ePA FHIR implementation guides | [gematik](https://gemspec.gematik.de/ig/fhir/epa/1.3.1/downloads.html) |
| Netherlands | Nictiz profiles and MedMij trust framework | [Nictiz / MedMij](https://www.nictiz.nl/programmas/medmij/) |

Legislation and standards: [GDPR](https://eur-lex.europa.eu/eli/reg/2016/679/oj) ·
[EHDS Regulation](https://eur-lex.europa.eu/eli/reg/2025/327/oj) ·
[FHIR R4](https://hl7.org/fhir/R4/). Adapter conformance must be checked against
the authoritative version in force for each deployment.

---

::: divider

## Run it every week

A short, repeatable operating rhythm turns the dashboards into controlled action
and measurable improvement.

:::

---

## The weekly playbook

1. **See.** Review Overview, Treatments & Specialties, and availability.
2. **Schedule.** Fill appropriate slots, confirm bookings, and resolve conflicts.
3. **Bill.** Raise invoices, record payments, and check the balanced trial balance.
4. **Recall.** Review due, lapsed, and follow-up cohorts before queuing reminders.
5. **Reach.** Confirm the party, purpose, consent state, and approved channel.
6. **Measure.** Track delivery outcomes, return rate, active patients, and revenue.
7. **Improve.** Review audit evidence, exceptions, and integration failures.

> **The daily question:** *How is the clinic running across every specialty—and
> what needs attention now?*

---

## Quick reference

| Need | Go to |
|---|---|
| Clinic scorecard | **Overview** |
| Case mix and procedures | **Treatments & Specialties** |
| Availability and booking | **Appointments** |
| Subject, party, and care history | **Patients** |
| Invoices, payments, and ledger | **Billing** |
| Due, lapsed, and recent-visit cohorts | **Recall & Scheduling** |
| Delivery status and return rate | **Recall Loop** |
| Operational questions | **Copilot / AI Assistant** |
| API schema and examples | **fastclinic.dev/developers** |
| Trust statement and roadmap | **fastclinic.dev/compliance** |

**Current public status:** open-source operations cockpit, synthetic data only.
Production controls, FHIR exchange, certifications, and national-system adapters
must be implemented and verified before real health-data use.
