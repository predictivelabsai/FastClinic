# FastClinic RBAC and role-specific workspace plan

FastClinic uses five persistent roles: `admin`, `practitioner`, `receptionist`,
`billing`, and `patient`. The legacy value `doctor` is accepted only as a
migration alias for `practitioner`.

Navigation visibility is a presentation concern, not an authorization control.
Every server-rendered route, HTMX mutation, API operation, download, and export
must enforce both an action capability and a record scope.

## Role workspaces

| Role | Primary workspace | Default record scope |
| --- | --- | --- |
| Admin | Clinic overview, configuration, and clinic-wide calendar | Entire clinic |
| Practitioner | Personal agenda, assigned patients, charts, orders, and messages | Assigned/care-team patients |
| Receptionist | Clinic calendar, registration, intake, and administrative communication | Scheduling and demographics only |
| Billing | Invoices, payments, coverage, and revenue | Financial data and minimum necessary demographics |
| Patient | Booking and personal portal | Own records only |

Practitioners are operationally close to administrators during the first
release, but never receive role management, system configuration, audit
administration, unrestricted billing, or bulk export by default.

## Admin role preview

Administrators receive a top-bar **Viewing as** selector for all five roles.
Role preview does not mutate the administrator's stored role:

- `actual_role` remains `admin`.
- `effective_role` is held in the signed server session.
- Authorization and navigation use `effective_role` while preview is active.
- A visible banner and an **Exit role preview** action prevent ambiguity.
- Starting and ending a preview produces an access-audit event.
- Patient preview uses the administrator's linked demo patient record; it is
  not general-purpose patient impersonation.
- Destructive or sensitive actions may be disabled in preview mode.

## Capability model

Capabilities use an `area.action.scope` vocabulary. Initial examples include:

```text
appointments.read.own
appointments.read.assigned
appointments.read.all
appointments.create.own
appointments.create.any
appointments.reschedule.own
appointments.reschedule.any
appointments.cancel.own
appointments.cancel.any
appointments.change_status
availability.read
availability.manage.own
availability.manage.all
patients.read.own
patients.read.assigned
patients.read.demographics
patients.read.all
charts.read.own
charts.read.assigned
charts.write.assigned
billing.read.own
billing.read.all
billing.write
roles.manage
audit.read
settings.manage
```

Each protected operation checks authentication, capability, and record scope.
Patient identity is derived from the authenticated account and is never trusted
from a submitted patient identifier.

## Initial permission matrix

| Function | Admin | Practitioner | Receptionist | Billing | Patient |
| --- | --- | --- | --- | --- | --- |
| Clinic dashboard | Full | Clinical summary | Scheduling summary | Financial summary | None |
| Clinic calendar | Full | Own/assigned | Full scheduling | Optional read-only | None |
| Appointment operations | Full | Own/assigned | Full scheduling | None | Own booking/reschedule/cancel |
| Availability | Full | Manage own | Read | None | Read bookable slots |
| Demographics | Full | Assigned | Full | Minimum necessary | Own |
| Clinical charts | Full | Assigned read/write | None | None | Own released records |
| Orders and encounters | Full | Assigned | None | None | Own released results |
| Messages | Full | Assigned threads | Administrative threads | Billing threads | Own |
| Billing | Full | Limited status | Limited status | Full | Own invoices |
| Users, roles, audit, settings | Full | None | None | None | None |
| Export | Full and audited | Assigned clinical data | None | Financial data | Own records |

## Booking and calendar domain

The prototype's global working hours and fixed clinician are replaced with:

- practitioner and specialty records;
- appointment types and durations;
- recurring availability rules and dated exceptions;
- clinic locations and rooms;
- booking policies, short-lived slot holds, and status history;
- participant and notification records; and
- conflict-safe PostgreSQL transactions for practitioners and rooms.

Times are stored in UTC and rendered in `Europe/Tallinn` by default. Patient
booking selects a service, optional practitioner, available slot, reason,
contact details, and reminder preference. Patients can reschedule or cancel
within policy. Practitioners receive day/week/agenda views and can confirm,
check in, start, complete, cancel, or mark no-show. Admins and receptionists
receive a multi-practitioner clinic calendar.

## Collapsible sections

Large page cards and main navigation groups use one accessible collapsible
component:

- upward chevron while expanded and downward chevron while collapsed;
- keyboard-operable header with `aria-expanded` and `aria-controls`;
- expansion state remembered by role, page, and section in `localStorage`;
- no clinical or patient content stored in browser state;
- HTMX-safe initialization and always-expanded print layout; and
- reduced-motion support.

Patient booking and the next appointment start expanded. Invoices, records,
coverage, and intake start collapsed. Critical warnings are never collapsed.

## Delivery sequence

1. Normalize role naming and add central capability/scope policies.
2. Add audited admin role preview and secure every route/action/API surface.
3. Add role-specific navigation, dashboards, and collapsible sections.
4. Add the PostgreSQL-ready availability and booking model.
5. Build patient, practitioner, receptionist, and admin calendars.
6. Test IDOR resistance, concurrent booking, CSRF, audit coverage, timezones,
   notifications, PostgreSQL migrations, and every role-preview workspace.

## Acceptance criteria

- An admin can preview all five roles without changing the stored role.
- A patient lands on booking and cannot access another patient's data by
  altering a URL, query string, or form field.
- Practitioners see only permitted schedules and patient records.
- Receptionists schedule without reading clinical notes.
- Billing users process financial records without clinical access.
- Concurrent requests cannot double-book a practitioner or room.
- Main sections collapse accessibly and remember only presentation state.
- Tests verify denied backend access rather than only hidden navigation.
- PostgreSQL is canonical for roles, availability, appointments, and audits.
