"""Lossless, replay-safe FHIR R4 document ingestion helpers."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

FHIR_NS = "http://hl7.org/fhir"
FHIR_VERSION = "4.0.1"


class FHIRIngressError(ValueError):
    """Raised when an input cannot safely be treated as a FHIR R4 document."""


@dataclass(frozen=True)
class DocumentBundle:
    payload: dict[str, Any]
    source_name: str
    source_format: str
    canonical_sha256: str
    bundle_id: str
    composition_id: str | None
    patient_id: str | None
    encounter_id: str | None
    patient_identifier_system: str | None
    patient_identifier_value: str | None
    document_date: str | None
    title: str | None

    @property
    def resources(self) -> list[tuple[str | None, dict[str, Any]]]:
        return [
            (entry.get("fullUrl"), entry["resource"])
            for entry in self.payload.get("entry", [])
        ]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_value(element: ET.Element) -> Any:
    if "value" in element.attrib and not list(element):
        return element.attrib["value"]
    if element.tag.startswith("{http://www.w3.org/1999/xhtml}"):
        return ET.tostring(element, encoding="unicode")
    # Normative FHIR XML wraps embedded resources (for example Bundle.entry
    # resources) in a <resource> element.  Older FastClinic exports placed the
    # resource directly under <entry>; retain support for those imports while
    # accepting the standards-shaped wrapper.
    if _local(element.tag) in {"resource", "contained", "outcome"}:
        children = list(element)
        if len(children) == 1:
            embedded = _xml_value(children[0])
            if isinstance(embedded, dict) and embedded.get("resourceType"):
                return embedded
    result: dict[str, Any] = {}
    if _local(element.tag) in {
        "Bundle", "Composition", "Patient", "Encounter", "DocumentReference",
        "Device", "Condition", "Observation", "Procedure", "Immunization",
        "MedicationRequest", "ServiceRequest", "Organization", "Practitioner",
    }:
        result["resourceType"] = _local(element.tag)
    for child in element:
        name = _local(child.tag)
        value = _xml_value(child)
        if _local(element.tag) == "entry" and isinstance(value, dict) and "resourceType" in value:
            result["resource"] = value
            continue
        if name in result:
            result[name] = result[name] + [value] if isinstance(result[name], list) else [result[name], value]
        else:
            result[name] = value
    return result


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _parse_json(path: Path) -> Iterable[tuple[dict[str, Any], str]]:
    if path.suffix.lower() == ".ndjson":
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                yield json.loads(line), f"{path.name}:{number}"
    else:
        yield json.loads(path.read_text(encoding="utf-8")), path.name


def _parse_xml(path: Path) -> Iterable[tuple[dict[str, Any], str]]:
    root = ET.parse(path).getroot()
    if not root.tag.startswith(f"{{{FHIR_NS}}}"):
        raise FHIRIngressError(f"{path.name}: XML root is not in the FHIR namespace")
    yield _xml_value(root), path.name


def discover_inputs(source: Path) -> list[Path]:
    """Choose one representation per source document when given a directory."""
    source = source.resolve()
    if source.is_file():
        return [source]
    if not source.is_dir():
        raise FHIRIngressError(f"Input does not exist: {source}")
    json_files = sorted(source.glob("*.fhir.json"))
    if json_files:
        return json_files
    xml_files = sorted(source.glob("*.fhir.xml"))
    if xml_files:
        return xml_files
    ndjson = sorted(source.glob("*.ndjson"))
    if ndjson:
        return ndjson
    raise FHIRIngressError(f"No FHIR JSON, XML, or NDJSON files found in {source}")


def read_bundles(source: Path) -> list[DocumentBundle]:
    bundles: list[DocumentBundle] = []
    for path in discover_inputs(source):
        parser = _parse_xml if path.suffix.lower() == ".xml" else _parse_json
        source_format = "xml" if parser is _parse_xml else ("ndjson" if path.suffix.lower() == ".ndjson" else "json")
        for payload, source_name in parser(path):
            bundles.append(normalize_bundle(payload, source_name, source_format))
    return bundles


def _reference_id(reference: Any) -> str | None:
    if not isinstance(reference, dict):
        return None
    value = reference.get("reference")
    return str(value).rsplit("/", 1)[-1] if value else None


def normalize_bundle(payload: dict[str, Any], source_name: str = "input", source_format: str = "json") -> DocumentBundle:
    if not isinstance(payload, dict) or payload.get("resourceType") != "Bundle":
        raise FHIRIngressError(f"{source_name}: expected a FHIR Bundle")
    if payload.get("type") != "document":
        raise FHIRIngressError(f"{source_name}: only Bundle.type=document is accepted")
    entries = _as_list(payload.get("entry"))
    if not entries or not isinstance(entries[0], dict) or entries[0].get("resource", {}).get("resourceType") != "Composition":
        raise FHIRIngressError(f"{source_name}: document Bundle must start with Composition")
    resources: list[dict[str, Any]] = []
    references: set[str] = set()
    identities: set[tuple[str, str]] = set()
    for entry in entries:
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict) or not resource.get("resourceType") or not resource.get("id"):
            raise FHIRIngressError(f"{source_name}: every entry needs resourceType and id")
        identity = (str(resource["resourceType"]), str(resource["id"]))
        if identity in identities:
            raise FHIRIngressError(f"{source_name}: duplicate resource {identity[0]}/{identity[1]}")
        identities.add(identity)
        resources.append(resource)
        if entry.get("fullUrl"):
            references.add(str(entry["fullUrl"]))
    composition = resources[0]
    for field in ("subject", "encounter"):
        ref = composition.get(field, {}).get("reference") if isinstance(composition.get(field), dict) else None
        if ref and ref not in references and not any(ref == f"{kind}/{ident}" for kind, ident in identities):
            raise FHIRIngressError(f"{source_name}: unresolved Composition.{field} reference")
    bundle_id = str(payload.get("id") or "")
    if not bundle_id:
        raise FHIRIngressError(f"{source_name}: Bundle.id is required for replay safety")
    patient = next((r for r in resources if r["resourceType"] == "Patient"), None)
    encounter = next((r for r in resources if r["resourceType"] == "Encounter"), None)
    identifiers = _as_list(patient.get("identifier") if patient else None)
    identifier = next((item for item in identifiers if isinstance(item, dict) and item.get("value")), {})
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return DocumentBundle(
        payload=payload,
        source_name=Path(source_name).name,
        source_format=source_format,
        canonical_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        bundle_id=bundle_id,
        composition_id=str(composition.get("id")) if composition.get("id") else None,
        patient_id=str(patient.get("id")) if patient and patient.get("id") else _reference_id(composition.get("subject")),
        encounter_id=str(encounter.get("id")) if encounter and encounter.get("id") else _reference_id(composition.get("encounter")),
        patient_identifier_system=identifier.get("system"),
        patient_identifier_value=str(identifier["value"]) if identifier.get("value") else None,
        document_date=composition.get("date"),
        title=composition.get("title"),
    )
