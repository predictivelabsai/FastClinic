"""Estonian TIS CDA-shaped sandbox XML projection.

The template OID is deliberately a FastClinic sandbox OID. Production must use
the exact TEHIK-published document template and pass the TIS validation module.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

HL7_NS = "urn:hl7-org:v3"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SANDBOX_TEMPLATE_OID = "1.3.6.1.4.1.55555.372.1"
ET.register_namespace("", HL7_NS)
ET.register_namespace("xsi", XSI_NS)


def outpatient_epicrisis_xml(fixture: dict) -> str:
    patient = fixture["patient"]
    encounter = fixture["encounter"]
    root = ET.Element(_q("ClinicalDocument"), {"classCode": "DOCCLIN", "moodCode": "EVN"})
    ET.SubElement(root, _q("realmCode"), {"code": "EE"})
    ET.SubElement(root, _q("typeId"), {"root": "2.16.840.1.113883.1.3", "extension": "POCD_HD000040"})
    ET.SubElement(root, _q("templateId"), {"root": SANDBOX_TEMPLATE_OID})
    ET.SubElement(root, _q("id"), {"root": "1.3.6.1.4.1.55555.372.2", "extension": encounter["id"]})
    ET.SubElement(root, _q("code"), {"code": "SANDBOX-AMB-EPICRISIS", "displayName": "Synthetic ambulatory epicrisis"})
    ET.SubElement(root, _q("title")).text = "Synthetic ambulatory epicrisis — not for TIS submission"
    ET.SubElement(root, _q("effectiveTime"), {"value": "20260814102500+0300"})
    record_target = ET.SubElement(root, _q("recordTarget"))
    patient_role = ET.SubElement(record_target, _q("patientRole"))
    ET.SubElement(patient_role, _q("id"), {"root": "1.3.6.1.4.1.55555.372.3", "extension": patient["id"]})
    patient_node = ET.SubElement(patient_role, _q("patient"))
    name = ET.SubElement(patient_node, _q("name"))
    ET.SubElement(name, _q("given")).text = patient["name"][0]["given"][0]
    ET.SubElement(name, _q("family")).text = patient["name"][0]["family"]
    author = ET.SubElement(root, _q("author"))
    ET.SubElement(author, _q("time"), {"value": "20260814102500+0300"})
    assigned = ET.SubElement(author, _q("assignedAuthor"))
    ET.SubElement(assigned, _q("id"), {"root": "1.3.6.1.4.1.55555.372.4", "extension": fixture["practitioner"]["id"]})
    custodian = ET.SubElement(root, _q("custodian"))
    assigned_custodian = ET.SubElement(custodian, _q("assignedCustodian"))
    represented = ET.SubElement(assigned_custodian, _q("representedCustodianOrganization"))
    ET.SubElement(represented, _q("id"), {"root": "1.3.6.1.4.1.55555.372.5", "extension": fixture["organization"]["registry_code"]})
    component = ET.SubElement(root, _q("component"))
    body = ET.SubElement(component, _q("structuredBody"))
    section_component = ET.SubElement(body, _q("component"))
    section = ET.SubElement(section_component, _q("section"))
    ET.SubElement(section, _q("title")).text = "Encounter summary"
    ET.SubElement(section, _q("text")).text = fixture["note"]
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def validate_cda_shape(xml_text: str) -> dict:
    errors = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        return {"valid": False, "errors": [f"invalid XML: {exc}"], "official_validator_run": False}
    if root.tag != _q("ClinicalDocument"):
        errors.append("root must be HL7 ClinicalDocument")
    for tag in ("templateId", "id", "code", "recordTarget", "author", "custodian", "component"):
        if root.find(_q(tag)) is None:
            errors.append(f"ClinicalDocument.{tag} is required")
    template = root.find(_q("templateId"))
    if template is not None and template.get("root") != SANDBOX_TEMPLATE_OID:
        errors.append("sandbox document must use the non-production sandbox template OID")
    return {"valid": not errors, "errors": errors, "official_validator_run": False, "schema": "CDA-shaped sandbox"}


def _q(name: str) -> str:
    return f"{{{HL7_NS}}}{name}"
