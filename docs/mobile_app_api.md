# FastClinic mobile app API

FastClinic API 1.5 adds a patient-mobile contract under `/api/v1/mobile`. The
mobile app uses MedBackend OAuth 2.0 Authorization Code with PKCE. It must never
embed `FASTSME_API_TOKEN`, a MedBackend client secret, or any clinic service
credential.

## Authentication

Register each native redirect URI in the MedBackend patient OAuth client. Use a
claimed HTTPS universal/app link where possible; a development custom scheme is
acceptable only for local builds. Request `openid profile patient/*.read` and
send the access token on each request:

```http
Authorization: Bearer <MedBackend patient access token>
```

FastAPI retrieves the signing key from `MEDBACKEND_PATIENT_JWKS_URL`, accepts
only RS256/ES256, validates expiry and audience against
`MEDBACKEND_PATIENT_CLIENT_ID`, and optionally validates
`MEDBACKEND_PATIENT_ISSUER`. The verified email resolves to FastClinic's
PostgreSQL `access_profile`; patient operations fail closed when no `subject_id`
is linked.

Required deployment configuration:

```dotenv
MEDBACKEND_PATIENT_AUTH_URL=...
MEDBACKEND_PATIENT_TOKEN_URL=...
MEDBACKEND_PATIENT_JWKS_URL=...
MEDBACKEND_PATIENT_CLIENT_ID=...
MEDBACKEND_PATIENT_ISSUER=... # recommended when MedBackend publishes it
```

The client secret belongs only in the server-side code exchange when the OAuth
client type requires one. Native apps are public clients and use PKCE.

## Startup and booking flow

1. `GET /api/v1/mobile/me` verifies identity and returns the effective role and
   capabilities.
2. `GET /api/v1/mobile/bootstrap` returns the patient's own appointments,
   treatments, practitioners, locations, rooms, timezone, and supported booking
   modes.
3. Assistant mode posts `{message, pending}` to
   `POST /api/v1/mobile/booking/chat`. Return the opaque `pending` object with
   the next message. The graph can propose or hold a slot, but creates a booking
   only after an explicit patient confirmation.
4. Classical mode reads
   `GET /api/v1/mobile/availability?clinician_id=...&day=YYYY-MM-DD&appointment_type_code=...`
   and posts the selected slot to `POST /api/v1/mobile/appointments`.
5. List, cancel, or reschedule only the authenticated patient's appointments
   with `/api/v1/mobile/appointments` and its action subroutes.

The create payload deliberately has no `subject_id`. FastAPI derives it from
the verified OAuth identity, so changing JSON or URLs cannot book for another
patient. Slot and room conflicts are checked in the same serialized database
transaction.

## Health records

`GET /api/v1/mobile/records` lists only FHIR documents linked to the verified
email. `GET /api/v1/mobile/records/{bundle_id}` returns the FHIR R4 JSON Bundle;
append `/xml` for `application/fhir+xml`. Responses are private and XML carries
`Cache-Control: private, no-store`.

## Client rules

- Treat timestamps as ISO 8601 and render using the bootstrap `timezone`.
- Store refresh/access tokens in Keychain or Android Keystore, never ordinary
  preferences, logs, analytics, crash metadata, or source control.
- Keep the chat `pending` value opaque and replace it with each response.
- On `401`, refresh or restart OAuth. On `403 patient_not_linked`, show a clinic
  support path. On `409 slot_taken`, refresh availability. On `422`, render the
  machine-readable validation details.
- Do not cache clinical payloads unless the mobile threat model, encryption,
  retention, logout wipe, and device-compromise controls have been approved.

The production API has its own hostname but runs in the same monolith container:

- Swagger UI: `https://api.fastclinic.dev/docs`
- ReDoc: `https://api.fastclinic.dev/redoc`
- OpenAPI: `https://api.fastclinic.dev/openapi.json`
- Health: `https://api.fastclinic.dev/v1/health`

The historical `https://fastclinic.dev/api/*` mount remains compatible.
