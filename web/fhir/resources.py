"""Pure FHIR R4 dict builders. No I/O — callers pass already-loaded core rows."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pms.catalog import gender_label

FHIR_VERSION = "4.0.1"
BASE_URL = "https://fastclinic.dev/api/v1/fhir"
CORE_SID = "https://fastclinic.dev/sid"
NATIONAL_ID_SYSTEM = f"{CORE_SID}/national-id"

GENDER_FHIR = {"Male": "male", "Female": "female"}

ITEM_RESOURCE = {
    "vaccine": "Immunization",
    "lab": "Observation",
    "imaging": "Observation",
    "referral": "ServiceRequest",
    "medication": "MedicationRequest",
    "repeat_prescription": "MedicationRequest",
    "surgery": "Procedure",
    "procedure": "Procedure",
    "dental": "Procedure",
    "pre_op": "Procedure",
    "health_plan": "Procedure",
    "follow_up": "Procedure",
    "specialist_consult": "Procedure",
    "consultation": "Procedure",
}

ENCOUNTER_CLASS = {
    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
    "code": "AMB",
    "display": "ambulatory",
}

RESOURCE_TYPES = frozenset({
    "Patient", "RelatedPerson", "Person", "Practitioner", "PractitionerRole",
    "Organization", "Encounter", "Condition", "Procedure", "Observation",
    "ServiceRequest", "Immunization", "MedicationRequest", "DocumentReference",
    "Appointment", "Consent", "ImmunizationRecommendation", "Task",
    "CommunicationRequest", "Communication", "Bundle", "CapabilityStatement",
})


def core_id(*parts: Any) -> str:
    return "-".join(str(p) for p in parts if p is not None and p != "")


def ref(resource_type: str, ident: Any) -> dict:
    return {"reference": f"{resource_type}/{ident}", "type": resource_type}


def coding(system: str, code: str, display: str | None = None) -> dict:
    out = {"system": system, "code": str(code)}
    if display:
        out["display"] = display
    return out


def codeable(system: str, code: str, display: str | None = None, text: str | None = None) -> dict:
    out: dict[str, Any] = {"coding": [coding(system, code, display)]}
    if text or display:
        out["text"] = text or display
    return out


def identifier(system: str, value: Any, *, use: str = "usual", type_code: str | None = None) -> dict:
    out: dict[str, Any] = {"system": system, "value": str(value), "use": use}
    if type_code:
        out["type"] = codeable(
            "http://terminology.hl7.org/CodeSystem/v2-0203", type_code,
        )
    return out


def human_name(official: str | None, *, use: str = "official") -> list[dict]:
    text = (official or "").strip()
    if not text:
        return []
    bits = text.split()
    name: dict[str, Any] = {"use": use, "text": text, "family": bits[-1]}
    if len(bits) > 1:
        name["given"] = bits[:-1]
    return [name]


def telecom(phone: str | None = None, email: str | None = None) -> list[dict]:
    out = []
    if phone:
        out.append({"system": "phone", "value": phone, "use": "home"})
    if email:
        out.append({"system": "email", "value": email, "use": "home"})
    return out


def address(row: dict) -> list[dict]:
    lines = [row.get("street_address"), row.get("street_address_2")]
    lines = [line for line in lines if line]
    city = row.get("city")
    postal = row.get("zip_code")
    country = row.get("country_region")
    state = row.get("state")
    if not any((lines, city, postal, country, state)):
        return []
    out: dict[str, Any] = {"use": "home", "type": "both"}
    if lines:
        out["line"] = lines
    if city:
        out["city"] = city
    if state:
        out["state"] = state
    if postal:
        out["postalCode"] = postal
    if country:
        out["country"] = country
    return [out]


def fhir_gender(code) -> str:
    return GENDER_FHIR.get(gender_label(code), "unknown")


def iso_date(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip().replace("T", " ")
    return text[:10] if len(text) >= 10 else text or None


def iso_datetime(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip().replace(" ", "T")
    if len(text) == 10:
        return f"{text}T00:00:00"
    if len(text) >= 16 and "T" in text:
        return text[:19]
    return text


def _dt(value: str | None) -> datetime | None:
    stamp = iso_datetime(value)
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return None


def clinic_organization() -> dict:
    return {
        "resourceType": "Organization",
        "id": "fastclinic",
        "meta": {"profile": [f"{BASE_URL}/StructureDefinition/fastclinic-organization"]},
        "identifier": [identifier(f"{CORE_SID}/organization", "fastclinic", type_code="XX")],
        "active": True,
        "type": [codeable(
            "http://terminology.hl7.org/CodeSystem/organization-type",
            "prov", "Healthcare Provider",
        )],
        "name": "FastClinic",
    }


def patient_resource(subject: dict) -> dict:
    ident = [identifier(f"{CORE_SID}/subject", subject["id"], type_code="PI")]
    if subject.get("nhs_number"):
        ident.append(identifier(NATIONAL_ID_SYSTEM, subject["nhs_number"], type_code="NH"))
    resource: dict[str, Any] = {
        "resourceType": "Patient",
        "id": str(subject["id"]),
        "identifier": ident,
        "active": not subject.get("archived") and not subject.get("deceased_at"),
        "name": human_name(subject.get("official_name")),
        "gender": fhir_gender(subject.get("gender")),
        "address": address(subject),
    }
    dob = iso_date(subject.get("date_of_birth"))
    if dob:
        resource["birthDate"] = dob
    if subject.get("deceased_at"):
        resource["deceasedDateTime"] = iso_datetime(subject["deceased_at"])
    else:
        resource["deceasedBoolean"] = False
    if subject.get("registered_clinician_id"):
        resource["generalPractitioner"] = [
            ref("Practitioner", subject["registered_clinician_id"])
        ]
    resource["managingOrganization"] = ref("Organization", "fastclinic")
    return _omit_empty(resource)


def related_person_resource(role: dict, party: dict, subject_id: int) -> dict:
    rid = core_id(party["id"], subject_id, role["role"])
    resource = {
        "resourceType": "RelatedPerson",
        "id": rid,
        "identifier": [identifier(f"{CORE_SID}/related-person", rid)],
        "active": True,
        "patient": ref("Patient", subject_id),
        "relationship": [_role_coding(role["role"])],
        "name": human_name(party.get("name")),
        "telecom": telecom(party.get("phone"), party.get("email")),
        "address": address(party),
    }
    return _omit_empty(resource)


def person_resource(party: dict, links: list[dict]) -> dict:
    resource = {
        "resourceType": "Person",
        "id": str(party["id"]),
        "identifier": [identifier(f"{CORE_SID}/party", party["id"])],
        "active": True,
        "name": human_name(party.get("name")),
        "telecom": telecom(party.get("phone"), party.get("email")),
        "address": address(party),
        "link": links,
    }
    return _omit_empty(resource)


def practitioner_resource(clinician_id: int, name: str | None = None) -> dict:
    return {
        "resourceType": "Practitioner",
        "id": str(clinician_id),
        "identifier": [identifier(f"{CORE_SID}/clinician", clinician_id)],
        "active": True,
        "name": human_name(name or f"Clinician {clinician_id}"),
    }


def practitioner_role_resource(clinician_id: int) -> dict:
    return {
        "resourceType": "PractitionerRole",
        "id": str(clinician_id),
        "identifier": [identifier(f"{CORE_SID}/clinician-role", clinician_id)],
        "active": True,
        "practitioner": ref("Practitioner", clinician_id),
        "organization": ref("Organization", "fastclinic"),
        "code": [codeable(
            "http://terminology.hl7.org/CodeSystem/practitioner-role",
            "doctor", "Doctor",
        )],
    }


def encounter_resource(consultation: dict) -> dict:
    status = "finished"
    if consultation.get("is_visit") in (0, "0", False):
        status = "finished"
    resource = {
        "resourceType": "Encounter",
        "id": str(consultation["id"]),
        "identifier": [identifier(f"{CORE_SID}/consultation", consultation["id"])],
        "status": status,
        "class": ENCOUNTER_CLASS,
        "subject": ref("Patient", consultation["subject_id"]),
        "period": {"start": iso_datetime(consultation.get("consult_at"))},
        "serviceProvider": ref("Organization", "fastclinic"),
    }
    if consultation.get("clinician_id"):
        resource["participant"] = [{
            "type": [codeable(
                "http://terminology.hl7.org/CodeSystem/v3-ParticipationType",
                "PPRF", "primary performer",
            )],
            "individual": ref("Practitioner", consultation["clinician_id"]),
        }]
    return _omit_empty(resource)


def condition_resource(diagnosis: dict) -> dict:
    resource = {
        "resourceType": "Condition",
        "id": str(diagnosis["id"]),
        "identifier": [identifier(f"{CORE_SID}/diagnosis", diagnosis["id"])],
        "clinicalStatus": codeable(
            "http://terminology.hl7.org/CodeSystem/condition-clinical",
            "active", "Active",
        ),
        "verificationStatus": codeable(
            "http://terminology.hl7.org/CodeSystem/condition-ver-status",
            "confirmed", "Confirmed",
        ),
        "code": _clinical_code(diagnosis.get("code"), diagnosis.get("name") or diagnosis.get("diagnosis")),
        "subject": ref("Patient", diagnosis["subject_id"]),
        "recordedDate": iso_datetime(diagnosis.get("diagnosis_at")),
    }
    if diagnosis.get("consultation_id"):
        resource["encounter"] = ref("Encounter", diagnosis["consultation_id"])
    if diagnosis.get("clinician_id"):
        resource["recorder"] = ref("Practitioner", diagnosis["clinician_id"])
    if diagnosis.get("description"):
        resource["note"] = [{"text": diagnosis["description"]}]
    return _omit_empty(resource)


def item_resource(item: dict) -> dict:
    """Project a billable line onto the FHIR resource its category implies."""
    category = item.get("category") or "procedure"
    kind = ITEM_RESOURCE.get(category, "Procedure")
    builders = {
        "Procedure": _procedure,
        "Observation": _observation,
        "ServiceRequest": _service_request,
        "Immunization": _immunization,
        "MedicationRequest": _medication_request,
    }
    return builders[kind](item)


def note_resource(note: dict) -> dict:
    text = note.get("text") or ""
    resource = {
        "resourceType": "DocumentReference",
        "id": str(note["id"]),
        "identifier": [identifier(f"{CORE_SID}/note", note["id"])],
        "status": "current" if not note.get("archived_at") else "superseded",
        "docStatus": "preliminary" if note.get("draft") else "final",
        "type": codeable(
            f"{CORE_SID}/note-type",
            note.get("custom_type") or note.get("type") or "clinical-note",
            note.get("custom_type") or "Clinical note",
        ),
        "subject": ref("Patient", note["subject_id"]),
        "date": iso_datetime(note.get("note_at") or note.get("created")),
        "description": (text[:240] + "…") if len(text) > 240 else text,
        "content": [{
            "attachment": {
                "contentType": "text/plain; charset=utf-8",
                "title": note.get("custom_type") or "Clinical note",
                "data": _b64(text),
            }
        }],
    }
    if note.get("consultation_id"):
        resource["context"] = {"encounter": [ref("Encounter", note["consultation_id"])]}
    if note.get("clinician_id"):
        resource["author"] = [ref("Practitioner", note["clinician_id"])]
    return _omit_empty(resource)


def appointment_resource(appointment: dict) -> dict:
    status_map = {
        "scheduled": "booked",
        "confirmed": "booked",
        "cancelled": "cancelled",
        "completed": "fulfilled",
    }
    participants = [
        {"actor": ref("Patient", appointment["subject_id"]), "status": "accepted",
         "required": "required"},
    ]
    if appointment.get("clinician_id"):
        participants.append({
            "actor": ref("Practitioner", appointment["clinician_id"]),
            "status": "accepted",
            "required": "required",
        })
    resource = {
        "resourceType": "Appointment",
        "id": str(appointment["id"]),
        "identifier": [identifier(f"{CORE_SID}/appointment", appointment["id"])],
        "status": status_map.get(appointment.get("status") or "scheduled", "booked"),
        "description": appointment.get("reason") or None,
        "start": iso_datetime(appointment.get("start_at")),
        "end": iso_datetime(appointment.get("end_at")),
        "participant": participants,
    }
    if appointment.get("room"):
        resource["comment"] = f"Room {appointment['room']}"
    return _omit_empty(resource)


def consent_resource(party: dict, subject_id: int) -> dict:
    opted_out = bool(party.get("marketing_opt_out"))
    return _omit_empty({
        "resourceType": "Consent",
        "id": core_id("mkt", party["id"], subject_id),
        "identifier": [identifier(f"{CORE_SID}/marketing-consent", party["id"])],
        "status": "active",
        "scope": codeable(
            "http://terminology.hl7.org/CodeSystem/consentscope",
            "patient-privacy", "Privacy Consent",
        ),
        "category": [codeable(
            "http://loinc.org", "59284-0", "Consent Document",
        )],
        "patient": ref("Patient", subject_id),
        "provision": {
            "type": "deny" if opted_out else "permit",
            "action": [codeable(
                "http://terminology.hl7.org/CodeSystem/consentaction",
                "advertise", "Advertise",
            )],
        },
    })


def reminder_resource(reminder: dict) -> dict:
    """Vaccine slice → ImmunizationRecommendation; everything else → Task."""
    category = reminder.get("category") or ""
    if category == "vaccine":
        return _immunization_recommendation(reminder)
    if category in {"appointment"}:
        return _communication_request(reminder)
    return _task(reminder)


def communication_resource(row: dict) -> dict:
    status_map = {
        "sent": "completed",
        "failed": "not-done",
        "blocked": "not-done",
    }
    resource = {
        "resourceType": "Communication",
        "id": str(row["id"]),
        "identifier": [identifier(f"{CORE_SID}/communication", row["id"])],
        "status": status_map.get(row.get("status") or "sent", "completed"),
        "statusReason": codeable(f"{CORE_SID}/send-status", row.get("status") or "sent")
        if row.get("status") in {"failed", "blocked"} else None,
        "category": [codeable(
            "http://terminology.hl7.org/CodeSystem/communication-category",
            "notification", "Notification",
        )],
        "medium": [codeable(
            "http://terminology.hl7.org/CodeSystem/v3-ParticipationMode",
            "PHONEWRIT" if row.get("channel") == "sms" else "EMAILWRIT",
            row.get("channel") or "email",
        )],
        "subject": ref("Patient", row["subject_id"]) if row.get("subject_id") else None,
        "sent": iso_datetime(row.get("sent_at")),
        "payload": [{"contentString": row.get("body")}] if row.get("body") else None,
    }
    if row.get("reminder_id"):
        resource["basedOn"] = [ref("Task", row["reminder_id"])]
    return _omit_empty(resource)


def capability_statement() -> dict:
    rest_resources = []
    for name, documentation in (
        ("Patient", "Synthetic subject of care"),
        ("RelatedPerson", "Guardian, payer, or other party role"),
        ("Person", "Linkage across RelatedPerson instances"),
        ("Practitioner", "Supervising clinician"),
        ("PractitionerRole", "Clinician role at FastClinic"),
        ("Organization", "The clinic"),
        ("Encounter", "Imported consultation"),
        ("Condition", "Imported diagnosis"),
        ("Procedure", "Performed treatment / surgery / dental"),
        ("Observation", "Lab or imaging line"),
        ("ServiceRequest", "Referral line"),
        ("Immunization", "Vaccine administration line"),
        ("MedicationRequest", "Medication or repeat-prescription line"),
        ("DocumentReference", "Clinical note"),
        ("Appointment", "Booked slot (operational)"),
        ("Consent", "Marketing outreach consent"),
        ("ImmunizationRecommendation", "Vaccine recall"),
        ("Task", "Non-vaccine recall"),
        ("CommunicationRequest", "Appointment reminder"),
        ("Communication", "Sent, failed, or blocked message"),
    ):
        rest_resources.append({
            "type": name,
            "documentation": documentation,
            "interaction": [{"code": "read"}, {"code": "search-type"}],
            "versioning": "no-version",
            "readHistory": False,
            "updateCreate": False,
        })
    return {
        "resourceType": "CapabilityStatement",
        "id": "fastclinic-r4",
        "url": f"{BASE_URL}/metadata",
        "version": FHIR_VERSION,
        "name": "FastClinicR4",
        "title": "FastClinic FHIR R4 Capability Statement",
        "status": "active",
        "experimental": True,
        "date": "2026-08-14",
        "publisher": "FastClinic",
        "description": (
            "Read-only FHIR R4 projection of the FastClinic synthetic clinic "
            "record. National profiles are applied by country adapters."
        ),
        "kind": "instance",
        "software": {"name": "FastClinic", "version": FHIR_VERSION},
        "implementation": {"description": "FastClinic synthetic FHIR R4 read surface",
                           "url": BASE_URL},
        "fhirVersion": FHIR_VERSION,
        "format": ["json"],
        "rest": [{
            "mode": "server",
            "documentation": "Synthetic data only. No live national spine.",
            "security": {
                "cors": True,
                "description": (
                    "Clinical reads of the synthetic record are public. "
                    "Operational resources and writes require a bearer token."
                ),
            },
            "resource": rest_resources,
            "operation": [
                {"name": "everything",
                 "definition": "http://hl7.org/fhir/OperationDefinition/Patient-everything"},
                {"name": "validate",
                 "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
            ],
        }],
    }


def _role_coding(role: str) -> dict:
    """Core-owned role vocabulary — adapters replace this at the boundary."""
    return codeable(f"{CORE_SID}/party-role", role, role.replace("_", " "))


def _clinical_code(code: str | None, text: str | None) -> dict:
    if code:
        system = "http://hl7.org/fhir/sid/icd-10"
        if str(code).upper().startswith(("SNOMED", "SCT")):
            system = "http://snomed.info/sct"
        return codeable(system, code, text, text)
    return {"text": text or "Unspecified"}


def _shared_item(item: dict) -> dict:
    when = iso_datetime(item.get("used") or item.get("item_at"))
    out = {
        "id": str(item["id"]),
        "identifier": [identifier(f"{CORE_SID}/item", item["id"])],
        "subject": ref("Patient", item["subject_id"]),
        "code": _clinical_code(item.get("code"), item.get("name")),
    }
    if item.get("consultation_id"):
        out["encounter"] = ref("Encounter", item["consultation_id"])
    if item.get("clinician_id"):
        out["performer_id"] = item["clinician_id"]
    if when:
        out["when"] = when
    return out


def _procedure(item: dict) -> dict:
    shared = _shared_item(item)
    resource = {
        "resourceType": "Procedure",
        "id": shared["id"],
        "identifier": shared["identifier"],
        "status": "completed",
        "code": shared["code"],
        "subject": shared["subject"],
        "performedDateTime": shared.get("when"),
        "category": codeable(f"{CORE_SID}/item-category", item.get("category") or "procedure"),
    }
    if shared.get("encounter"):
        resource["encounter"] = shared["encounter"]
    if shared.get("performer_id"):
        resource["performer"] = [{"actor": ref("Practitioner", shared["performer_id"])}]
    return _omit_empty(resource)


def _observation(item: dict) -> dict:
    shared = _shared_item(item)
    resource = {
        "resourceType": "Observation",
        "id": shared["id"],
        "identifier": shared["identifier"],
        "status": "final",
        "code": shared["code"],
        "subject": shared["subject"],
        "effectiveDateTime": shared.get("when"),
        "category": [codeable(
            "http://terminology.hl7.org/CodeSystem/observation-category",
            "imaging" if item.get("category") == "imaging" else "laboratory",
        )],
    }
    if shared.get("encounter"):
        resource["encounter"] = shared["encounter"]
    if shared.get("performer_id"):
        resource["performer"] = [ref("Practitioner", shared["performer_id"])]
    return _omit_empty(resource)


def _service_request(item: dict) -> dict:
    shared = _shared_item(item)
    resource = {
        "resourceType": "ServiceRequest",
        "id": shared["id"],
        "identifier": shared["identifier"],
        "status": "completed",
        "intent": "order",
        "code": shared["code"],
        "subject": shared["subject"],
        "authoredOn": shared.get("when"),
        "category": [codeable(f"{CORE_SID}/item-category", "referral", "Referral")],
    }
    if shared.get("encounter"):
        resource["encounter"] = shared["encounter"]
    if shared.get("performer_id"):
        resource["requester"] = ref("Practitioner", shared["performer_id"])
    return _omit_empty(resource)


def _immunization(item: dict) -> dict:
    shared = _shared_item(item)
    resource = {
        "resourceType": "Immunization",
        "id": shared["id"],
        "identifier": shared["identifier"],
        "status": "completed",
        "vaccineCode": shared["code"],
        "patient": shared["subject"],
        "occurrenceDateTime": shared.get("when"),
        "primarySource": True,
    }
    if shared.get("encounter"):
        resource["encounter"] = shared["encounter"]
    if shared.get("performer_id"):
        resource["performer"] = [{"actor": ref("Practitioner", shared["performer_id"])}]
    return _omit_empty(resource)


def _medication_request(item: dict) -> dict:
    shared = _shared_item(item)
    resource = {
        "resourceType": "MedicationRequest",
        "id": shared["id"],
        "identifier": shared["identifier"],
        "status": "completed",
        "intent": "order",
        "medicationCodeableConcept": shared["code"],
        "subject": shared["subject"],
        "authoredOn": shared.get("when"),
    }
    if shared.get("encounter"):
        resource["encounter"] = shared["encounter"]
    if shared.get("performer_id"):
        resource["requester"] = ref("Practitioner", shared["performer_id"])
    return _omit_empty(resource)


def _immunization_recommendation(reminder: dict) -> dict:
    due = iso_date(reminder.get("due_date"))
    status = reminder.get("status") or "pending"
    forecast = {
        "pending": "due",
        "sent": "due",
        "cancelled": "complete",
        "failed": "overdue",
    }.get(status, "due")
    if status == "pending" and due:
        ref_day = due
        # overdue is decided by the caller if they pass status; keep structure valid
        _ = ref_day
    rec: dict[str, Any] = {
        "forecastStatus": codeable(
            "http://terminology.hl7.org/CodeSystem/immunization-recommendation-status",
            forecast, forecast,
        ),
        "vaccineCode": [codeable(f"{CORE_SID}/recall", "vaccine", "Immunisation")],
    }
    if due:
        rec["dateCriterion"] = [{
            "code": codeable(
                "http://loinc.org", "30980-7", "Date vaccine due",
            ),
            "value": f"{due}T00:00:00",
        }]
    return _omit_empty({
        "resourceType": "ImmunizationRecommendation",
        "id": str(reminder["id"]),
        "identifier": [identifier(f"{CORE_SID}/reminder", reminder["id"])],
        "patient": ref("Patient", reminder["subject_id"]),
        "date": iso_datetime(reminder.get("created_at")) or (f"{due}T00:00:00" if due else "1970-01-01T00:00:00"),
        "recommendation": [rec],
    })


def _task(reminder: dict) -> dict:
    status_map = {
        "pending": "requested",
        "sent": "completed",
        "cancelled": "cancelled",
        "failed": "failed",
    }
    return _omit_empty({
        "resourceType": "Task",
        "id": str(reminder["id"]),
        "identifier": [identifier(f"{CORE_SID}/reminder", reminder["id"])],
        "status": status_map.get(reminder.get("status") or "pending", "requested"),
        "intent": "order",
        "code": codeable(
            f"{CORE_SID}/recall",
            reminder.get("category") or "recall",
            (reminder.get("category") or "recall").replace("_", " "),
        ),
        "for": ref("Patient", reminder["subject_id"]),
        "executionPeriod": {"start": iso_date(reminder.get("due_date"))},
        "description": reminder.get("sms_text") or reminder.get("email_text"),
        "authoredOn": iso_datetime(reminder.get("created_at")),
    })


def _communication_request(reminder: dict) -> dict:
    return _omit_empty({
        "resourceType": "CommunicationRequest",
        "id": str(reminder["id"]),
        "identifier": [identifier(f"{CORE_SID}/reminder", reminder["id"])],
        "status": "active" if reminder.get("status") == "pending" else "completed",
        "category": [codeable(
            "http://terminology.hl7.org/CodeSystem/communication-category",
            "notification", "Notification",
        )],
        "subject": ref("Patient", reminder["subject_id"]),
        "payload": (
            [{"contentString": reminder["sms_text"]}]
            if reminder.get("sms_text") else None
        ),
        "occurrenceDateTime": iso_date(reminder.get("due_date")),
        "authoredOn": iso_datetime(reminder.get("created_at")),
    })


def _b64(text: str) -> str:
    import base64
    return base64.b64encode((text or "").encode("utf-8")).decode("ascii")


def _omit_empty(resource: dict) -> dict:
    def keep(value):
        if value is None or value == [] or value == {}:
            return False
        return True
    return {key: value for key, value in resource.items() if keep(value)}
