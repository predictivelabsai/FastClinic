"""Load FastClinic rows and assemble FHIR R4 resources / bundles."""
from __future__ import annotations

from typing import Any

from web import db
from web.fhir.resources import (
    BASE_URL,
    appointment_resource,
    clinic_organization,
    communication_resource,
    condition_resource,
    consent_resource,
    encounter_resource,
    item_resource,
    note_resource,
    patient_resource,
    person_resource,
    practitioner_resource,
    practitioner_role_resource,
    related_person_resource,
    reminder_resource,
)

_OPS_TYPES = {
    "Appointment", "Communication", "ImmunizationRecommendation",
    "Task", "CommunicationRequest",
}


def assemble_subject(subject_id: int, *, include_ops: bool = False) -> list[dict]:
    subject = db.query_one("SELECT * FROM subject WHERE id=?", (subject_id,))
    if not subject:
        return []
    resources: list[dict] = [clinic_organization(), patient_resource(subject)]
    resources.extend(_people(subject))
    resources.extend(_practitioners_for(subject))
    for consultation in db.query(
        "SELECT * FROM consultation WHERE subject_id=? ORDER BY consult_at",
        (subject_id,),
    ):
        resources.append(encounter_resource(consultation))
    for diagnosis in db.query(
        "SELECT * FROM diagnosis WHERE subject_id=? ORDER BY diagnosis_at",
        (subject_id,),
    ):
        resources.append(condition_resource(diagnosis))
    for item in db.query(
        "SELECT * FROM item WHERE subject_id=? ORDER BY item_at",
        (subject_id,),
    ):
        resources.append(item_resource(item))
    for note in db.query(
        "SELECT * FROM note WHERE subject_id=? AND archived_at IS NULL ORDER BY note_at",
        (subject_id,),
    ):
        resources.append(note_resource(note))
    resources.extend(_consents(subject))
    if include_ops:
        resources.extend(_ops(subject_id))
    return resources


def assemble_one(resource_type: str, resource_id: str, *, include_ops: bool = False) -> dict | None:
    if resource_type in _OPS_TYPES and not include_ops:
        return None
    if resource_type == "Organization" and resource_id == "fastclinic":
        return clinic_organization()
    if resource_type == "Patient":
        row = _row("subject", resource_id)
        return patient_resource(row) if row else None
    if resource_type == "Encounter":
        row = _row("consultation", resource_id)
        return encounter_resource(row) if row else None
    if resource_type == "Condition":
        row = _row("diagnosis", resource_id)
        return condition_resource(row) if row else None
    if resource_type == "DocumentReference":
        row = _row("note", resource_id)
        return note_resource(row) if row else None
    if resource_type in {"Procedure", "Observation", "ServiceRequest",
                         "Immunization", "MedicationRequest"}:
        row = _row("item", resource_id)
        if not row:
            return None
        resource = item_resource(row)
        return resource if resource["resourceType"] == resource_type else None
    if resource_type == "Practitioner":
        return _practitioner(resource_id)
    if resource_type == "PractitionerRole":
        pract = _practitioner(resource_id)
        return practitioner_role_resource(int(resource_id)) if pract else None
    if resource_type == "RelatedPerson":
        return _one_related(resource_id)
    if resource_type == "Person":
        party = _row("party", resource_id)
        if not party:
            return None
        return person_resource(party, _person_links(int(resource_id)))
    if resource_type == "Consent":
        return _one_consent(resource_id)
    if resource_type == "Appointment":
        from web import appointments
        try:
            row = appointments.get(int(resource_id))
        except (TypeError, ValueError):
            return None
        return appointment_resource(row) if row else None
    if resource_type in {"ImmunizationRecommendation", "Task", "CommunicationRequest"}:
        from web import activation_loop
        try:
            row = activation_loop.get_reminder(int(resource_id))
        except (TypeError, ValueError):
            return None
        if not row:
            return None
        resource = reminder_resource(row)
        return resource if resource["resourceType"] == resource_type else None
    if resource_type == "Communication":
        from web import activation_loop
        rows = activation_loop.query(
            "SELECT * FROM communication WHERE id=?", (resource_id,),
        )
        return communication_resource(rows[0]) if rows else None
    return None


def as_bundle(resources: list[dict], *, bundle_type: str = "searchset") -> dict:
    entries = []
    for resource in resources:
        ident = resource.get("id")
        kind = resource.get("resourceType")
        full = f"{BASE_URL}/{kind}/{ident}" if ident else None
        entry: dict[str, Any] = {"resource": resource}
        if full:
            entry["fullUrl"] = full
        if bundle_type == "searchset":
            entry["search"] = {"mode": "match"}
        entries.append(entry)
    return {
        "resourceType": "Bundle",
        "type": bundle_type,
        "total": len(entries),
        "entry": entries,
    }


def _row(table: str, ident: str) -> dict | None:
    try:
        item_id = int(ident)
    except (TypeError, ValueError):
        return None
    return db.query_one(f'SELECT * FROM "{table}" WHERE id=?', (item_id,))


def _people(subject: dict) -> list[dict]:
    roles = db.query(
        "SELECT * FROM subject_party_role WHERE subject_id=? ORDER BY is_primary DESC, role",
        (subject["id"],),
    )
    resources: list[dict] = []
    parties_seen: dict[int, list[dict]] = {}
    for role in roles:
        party = db.query_one("SELECT * FROM party WHERE id=?", (role["party_id"],))
        if not party:
            continue
        if role["role"] != "self":
            related = related_person_resource(role, party, subject["id"])
            resources.append(related)
            parties_seen.setdefault(party["id"], []).append({
                "target": {"reference": f"RelatedPerson/{related['id']}"},
                "assurance": "level3",
            })
        else:
            parties_seen.setdefault(party["id"], []).append({
                "target": {"reference": f"Patient/{subject['id']}"},
                "assurance": "level4",
            })
    # Person is emitted only when a party is more than the patient's own self-link
    # (guardian of one or more subjects, payer, shared across siblings, …).
    for party_id, links in parties_seen.items():
        related_links = [link for link in links if link["target"]["reference"].startswith("RelatedPerson/")]
        if not related_links:
            continue
        party = db.query_one("SELECT * FROM party WHERE id=?", (party_id,))
        if party:
            # Include every link this party has so siblings share one Person.
            all_links = _person_links(party_id)
            resources.append(person_resource(party, all_links))
    return resources


def _person_links(party_id: int) -> list[dict]:
    rows = db.query(
        "SELECT * FROM subject_party_role WHERE party_id=? ORDER BY subject_id, role",
        (party_id,),
    )
    links = []
    for role in rows:
        if role["role"] == "self":
            links.append({
                "target": {"reference": f"Patient/{role['subject_id']}"},
                "assurance": "level4",
            })
        else:
            rid = f"{party_id}-{role['subject_id']}-{role['role']}"
            links.append({
                "target": {"reference": f"RelatedPerson/{rid}"},
                "assurance": "level3",
            })
    return links


def _practitioners_for(subject: dict) -> list[dict]:
    ids = set()
    if subject.get("registered_clinician_id"):
        ids.add(int(subject["registered_clinician_id"]))
    for row in db.query(
        "SELECT DISTINCT clinician_id FROM consultation "
        "WHERE subject_id=? AND clinician_id IS NOT NULL",
        (subject["id"],),
    ):
        ids.add(int(row["clinician_id"]))
    resources = []
    for clinician_id in sorted(ids):
        resources.append(practitioner_resource(clinician_id))
        resources.append(practitioner_role_resource(clinician_id))
    return resources


def _practitioner(resource_id: str) -> dict | None:
    try:
        clinician_id = int(resource_id)
    except (TypeError, ValueError):
        return None
    exists = db.query_one(
        "SELECT 1 AS ok FROM consultation WHERE clinician_id=? LIMIT 1",
        (clinician_id,),
    ) or db.query_one(
        "SELECT 1 AS ok FROM subject WHERE registered_clinician_id=? LIMIT 1",
        (clinician_id,),
    )
    if not exists:
        return None
    return practitioner_resource(clinician_id)


def _consents(subject: dict) -> list[dict]:
    rows = db.query(
        """SELECT p.* FROM party p
           JOIN subject_party_role r ON r.party_id=p.id
           WHERE r.subject_id=? AND r.is_primary=1""",
        (subject["id"],),
    )
    return [consent_resource(row, subject["id"]) for row in rows]


def _one_related(resource_id: str) -> dict | None:
    parts = str(resource_id).split("-")
    if len(parts) < 3:
        return None
    try:
        party_id, subject_id, role = int(parts[0]), int(parts[1]), "-".join(parts[2:])
    except ValueError:
        return None
    rel = db.query_one(
        "SELECT * FROM subject_party_role WHERE party_id=? AND subject_id=? AND role=?",
        (party_id, subject_id, role),
    )
    party = db.query_one("SELECT * FROM party WHERE id=?", (party_id,))
    if not rel or not party or rel["role"] == "self":
        return None
    return related_person_resource(rel, party, subject_id)


def _one_consent(resource_id: str) -> dict | None:
    parts = str(resource_id).split("-")
    if len(parts) != 3 or parts[0] != "mkt":
        return None
    try:
        party_id, subject_id = int(parts[1]), int(parts[2])
    except ValueError:
        return None
    party = db.query_one("SELECT * FROM party WHERE id=?", (party_id,))
    if not party:
        return None
    return consent_resource(party, subject_id)


def _ops(subject_id: int) -> list[dict]:
    from web import activation_loop
    resources = []
    for row in activation_loop.query(
        "SELECT * FROM appointment WHERE subject_id=? ORDER BY start_at",
        (subject_id,),
    ):
        resources.append(appointment_resource(row))
    for row in activation_loop.query(
        "SELECT * FROM reminder WHERE subject_id=? ORDER BY due_date",
        (subject_id,),
    ):
        resources.append(reminder_resource(row))
    for row in activation_loop.query(
        "SELECT * FROM communication WHERE subject_id=? ORDER BY sent_at",
        (subject_id,),
    ):
        resources.append(communication_resource(row))
    return resources
