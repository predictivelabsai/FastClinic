"""FHIR R4 JSON-to-XML serialization for imported clinical documents.

The patient portal stores the lossless FHIR JSON representation because it is
convenient to index in PostgreSQL.  This module recreates the normative XML
representation used by the Terviseportaal conversion adapter: FHIR elements
use the FHIR namespace, primitive values use ``value`` attributes, Bundle
entries wrap resources in ``entry.resource``, and Narrative.div remains XHTML.

The serializer deliberately supports the document resources emitted by
``scripts/convert_health_exports_to_fhir.py``.  Unknown fields fail closed
instead of producing XML whose element order cannot be guaranteed against the
FHIR R4 schemas.
"""
from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

from web.fhir.ingress import FHIR_NS

XHTML_NS = "http://www.w3.org/1999/xhtml"
FHIR_XML_MEDIA_TYPE = "application/fhir+xml"

ET.register_namespace("", FHIR_NS)
ET.register_namespace("xhtml", XHTML_NS)


class FHIRXMLSerializationError(ValueError):
    """Raised when a payload cannot be serialized as ordered FHIR R4 XML."""


_RESOURCE_ORDER: dict[str, tuple[str, ...]] = {
    "Bundle": (
        "id", "meta", "implicitRules", "language", "identifier", "type",
        "timestamp", "total", "link", "entry", "signature",
    ),
    "Composition": (
        "id", "meta", "implicitRules", "language", "text", "contained",
        "extension", "modifierExtension", "identifier", "status", "type",
        "category", "subject", "encounter", "date", "author", "title",
        "confidentiality", "attester", "custodian", "relatesTo", "event",
        "section",
    ),
    "Patient": (
        "id", "meta", "implicitRules", "language", "text", "contained",
        "extension", "modifierExtension", "identifier", "active", "name",
        "telecom", "gender", "birthDate", "deceasedBoolean",
        "deceasedDateTime", "address", "maritalStatus",
        "multipleBirthBoolean", "multipleBirthInteger", "photo", "contact",
        "communication", "generalPractitioner", "managingOrganization", "link",
    ),
    "Encounter": (
        "id", "meta", "implicitRules", "language", "text", "contained",
        "extension", "modifierExtension", "identifier", "status",
        "statusHistory", "class", "classHistory", "type", "serviceType",
        "priority", "subject", "episodeOfCare", "basedOn", "participant",
        "appointment", "period", "length", "reasonCode", "reasonReference",
        "diagnosis", "account", "hospitalization", "location",
        "serviceProvider", "partOf",
    ),
    "DocumentReference": (
        "id", "meta", "implicitRules", "language", "text", "contained",
        "extension", "modifierExtension", "masterIdentifier", "identifier",
        "status", "docStatus", "type", "category", "subject", "date",
        "author", "authenticator", "custodian", "relatesTo", "description",
        "securityLabel", "content", "context",
    ),
    "Device": (
        "id", "meta", "implicitRules", "language", "text", "contained",
        "extension", "modifierExtension", "identifier", "definition",
        "udiCarrier", "status", "statusReason", "distinctIdentifier",
        "manufacturer", "manufactureDate", "expirationDate", "lotNumber",
        "serialNumber", "deviceName", "modelNumber", "partNumber", "type",
        "specialization", "version", "property", "patient", "owner",
        "contact", "location", "url", "note", "safety", "parent",
    ),
}

_COMPLEX_ORDER: dict[str, tuple[str, ...]] = {
    "Bundle.identifier": ("use", "type", "system", "value", "period", "assigner"),
    "Bundle.link": ("relation", "url"),
    "Bundle.entry": ("link", "fullUrl", "resource", "search", "request", "response"),
    "Composition.identifier": ("use", "type", "system", "value", "period", "assigner"),
    "Composition.type": ("coding", "text"),
    "Composition.type.coding": ("system", "version", "code", "display", "userSelected"),
    "Composition.category": ("coding", "text"),
    "Composition.category.coding": ("system", "version", "code", "display", "userSelected"),
    "Composition.subject": ("reference", "type", "identifier", "display"),
    "Composition.encounter": ("reference", "type", "identifier", "display"),
    "Composition.author": ("reference", "type", "identifier", "display"),
    "Composition.custodian": ("reference", "type", "identifier", "display"),
    "Composition.section": (
        "title", "code", "author", "focus", "text", "mode", "orderedBy",
        "entry", "emptyReason", "section",
    ),
    "Composition.section.code": ("coding", "text"),
    "Composition.section.code.coding": ("system", "version", "code", "display", "userSelected"),
    "Composition.section.author": ("reference", "type", "identifier", "display"),
    "Composition.section.focus": ("reference", "type", "identifier", "display"),
    "Composition.section.text": ("status", "div"),
    "Composition.section.entry": ("reference", "type", "identifier", "display"),
    "Patient.identifier": ("use", "type", "system", "value", "period", "assigner"),
    "Encounter.identifier": ("use", "type", "system", "value", "period", "assigner"),
    "Encounter.class": ("system", "version", "code", "display", "userSelected"),
    "Encounter.subject": ("reference", "type", "identifier", "display"),
    "Encounter.period": ("start", "end"),
    "DocumentReference.masterIdentifier": ("use", "type", "system", "value", "period", "assigner"),
    "DocumentReference.identifier": ("use", "type", "system", "value", "period", "assigner"),
    "DocumentReference.type": ("coding", "text"),
    "DocumentReference.type.coding": ("system", "version", "code", "display", "userSelected"),
    "DocumentReference.category": ("coding", "text"),
    "DocumentReference.category.coding": ("system", "version", "code", "display", "userSelected"),
    "DocumentReference.subject": ("reference", "type", "identifier", "display"),
    "DocumentReference.author": ("reference", "type", "identifier", "display"),
    "DocumentReference.authenticator": ("reference", "type", "identifier", "display"),
    "DocumentReference.custodian": ("reference", "type", "identifier", "display"),
    "DocumentReference.content": ("attachment", "format"),
    "DocumentReference.content.attachment": (
        "contentType", "language", "data", "url", "size", "hash", "title", "creation",
    ),
    "DocumentReference.content.format": ("system", "version", "code", "display", "userSelected"),
    "Device.identifier": ("use", "type", "system", "value", "period", "assigner"),
    "Device.deviceName": ("name", "type"),
}


def _tag(name: str) -> str:
    return f"{{{FHIR_NS}}}{name}"


def _primitive(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    rendered = str(value)
    if not rendered.strip():
        raise FHIRXMLSerializationError("FHIR primitive values cannot be empty")
    return rendered


def _ordered_fields(payload: dict[str, Any], path: str, resource_type: str | None = None) -> list[str]:
    order = _RESOURCE_ORDER.get(resource_type or "") or _COMPLEX_ORDER.get(path)
    if order is None:
        raise FHIRXMLSerializationError(f"Unsupported FHIR R4 structure: {path}")
    present = [
        key for key in payload
        if key != "resourceType" and not key.startswith("_") and not (resource_type is None and key == "id")
    ]
    unknown = [key for key in present if key not in order]
    if unknown:
        raise FHIRXMLSerializationError(
            f"Unsupported field(s) at {path}: {', '.join(sorted(unknown))}"
        )
    return [key for key in order if key in payload or f"_{key}" in payload]


def _append_xhtml(parent: ET.Element, raw: Any) -> None:
    if not isinstance(raw, str):
        raise FHIRXMLSerializationError("Narrative.div must be serialized XHTML")
    try:
        div = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise FHIRXMLSerializationError("Narrative.div is not well-formed XHTML") from exc
    if div.tag != f"{{{XHTML_NS}}}div":
        raise FHIRXMLSerializationError("Narrative.div must use the XHTML namespace")
    parent.append(div)


def _append_resource(parent: ET.Element, payload: dict[str, Any]) -> None:
    resource_type = str(payload.get("resourceType") or "")
    if resource_type not in _RESOURCE_ORDER:
        raise FHIRXMLSerializationError(f"Unsupported FHIR R4 resource: {resource_type or '(missing)'}")
    element = ET.SubElement(parent, _tag(resource_type))
    _append_fields(element, payload, resource_type, resource_type)


def _append_primitive_metadata(element: ET.Element, metadata: Any, path: str) -> None:
    if metadata is None:
        return
    if not isinstance(metadata, dict):
        raise FHIRXMLSerializationError(f"Primitive metadata at {path} must be an object")
    if metadata.get("id"):
        element.set("id", _primitive(metadata["id"]))
    for extension in metadata.get("extension") or []:
        _append_complex(element, "extension", extension, f"{path}.extension")


def _append_complex(parent: ET.Element, name: str, value: dict[str, Any], path: str) -> None:
    if name in {"resource", "contained", "outcome"} and value.get("resourceType"):
        wrapper = ET.SubElement(parent, _tag(name))
        _append_resource(wrapper, value)
        return
    element = ET.SubElement(parent, _tag(name))
    if value.get("id"):
        element.set("id", _primitive(value["id"]))
    if name == "extension":
        url = value.get("url")
        if not url:
            raise FHIRXMLSerializationError(f"Extension at {path} requires url")
        element.set("url", _primitive(url))
        keys = [key for key in value if key not in {"id", "url", "resourceType"} and not key.startswith("_")]
        ordered = (["extension"] if "extension" in keys else []) + sorted(
            (key for key in keys if key != "extension"), key=lambda key: (not key.startswith("value"), key)
        )
        for key in ordered:
            _append_field(element, key, value[key], value.get(f"_{key}"), f"{path}.{key}")
        return
    _append_fields(element, value, path, None)


def _append_field(parent: ET.Element, name: str, value: Any, metadata: Any, path: str) -> None:
    values = value if isinstance(value, list) else [value]
    metadata_values = metadata if isinstance(metadata, list) else [metadata] * len(values)
    if len(metadata_values) < len(values):
        metadata_values += [None] * (len(values) - len(metadata_values))
    for index, item in enumerate(values):
        item_metadata = metadata_values[index]
        if name == "div":
            _append_xhtml(parent, item)
        elif isinstance(item, dict):
            _append_complex(parent, name, item, path)
        elif item is not None:
            element = ET.SubElement(parent, _tag(name))
            element.set("value", _primitive(item))
            _append_primitive_metadata(element, item_metadata, path)
        elif item_metadata:
            element = ET.SubElement(parent, _tag(name))
            _append_primitive_metadata(element, item_metadata, path)


def _append_fields(parent: ET.Element, payload: dict[str, Any], path: str,
                   resource_type: str | None) -> None:
    for name in _ordered_fields(payload, path, resource_type):
        if name == "id" and resource_type is None:
            continue
        _append_field(parent, name, payload.get(name), payload.get(f"_{name}"), f"{path}.{name}")


def bundle_to_xml(payload: dict[str, Any], *, pretty: bool = True) -> bytes:
    """Serialize a supported FHIR R4 document Bundle as UTF-8 XML."""
    if not isinstance(payload, dict) or payload.get("resourceType") != "Bundle":
        raise FHIRXMLSerializationError("Expected a FHIR Bundle")
    root_holder = ET.Element("holder")
    _append_resource(root_holder, payload)
    root = root_holder[0]
    if pretty:
        ET.indent(root, space="  ")
    rendered = ET.tostring(root, encoding="unicode", short_empty_elements=True)

    # ElementTree can only register one global default namespace.  FHIR uses a
    # FHIR default namespace at the resource root and a nested XHTML default
    # namespace for Narrative.div, so normalize the generated XHTML prefix.
    rendered = rendered.replace(f' xmlns:xhtml="{XHTML_NS}"', "")
    rendered = rendered.replace("<xhtml:div", f'<div xmlns="{XHTML_NS}"')
    rendered = rendered.replace("<xhtml:", "<").replace("</xhtml:", "</")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + rendered + "\n").encode("utf-8")
