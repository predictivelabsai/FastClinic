"""Convert private Terviseportaal HTML exports to lossless FHIR R4 XML documents.

This is a document-preserving conversion, not a claim of semantic CDA mapping.
Each output is a FHIR R4 document Bundle whose Composition narrative preserves
the rendered text and whose DocumentReference embeds the original HTML bytes.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html as html_module
import json
import os
import re
import uuid
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

FHIR = "http://hl7.org/fhir"
XHTML = "http://www.w3.org/1999/xhtml"
ET.register_namespace("", FHIR)

RESOURCE_TYPES = {"Bundle", "Composition", "Patient", "Encounter", "DocumentReference", "Device"}
REPEATING_PATHS = {
    "Bundle.entry",
    "Composition.author",
    "Composition.section",
    "Composition.section.entry",
    "Composition.type.coding",
    "Patient.identifier",
    "DocumentReference.type.coding",
    "DocumentReference.content",
    "Device.deviceName",
}


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        elif not self.skip and tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
        elif not self.skip and tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self) -> str:
        value = html_module.unescape("".join(self.parts)).replace("\xa0", " ")
        lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
        return "\n".join(line for line in lines if line)


def node(parent, name: str, value=None):
    child = ET.SubElement(parent, f"{{{FHIR}}}{name}")
    if value is not None:
        child.set("value", str(value))
    return child


def reference(parent, name: str, target: str):
    ref = node(parent, name)
    node(ref, "reference", target)
    return ref


def entry(bundle, full_url: str, resource):
    item = node(bundle, "entry")
    node(item, "fullUrl", full_url)
    item.append(resource)


def resource(name: str, resource_id: str):
    root = ET.Element(f"{{{FHIR}}}{name}")
    node(root, "id", resource_id)
    return root


def extract_text(raw: str) -> str:
    parser = TextExtractor()
    parser.feed(raw)
    return parser.text()


def source_date(text: str) -> str | None:
    match = re.search(r"\b(?:Algus|Start)\s*:\s*(\d{2})\.(\d{2})\.(\d{4})", text, re.I)
    if not match:
        return None
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def patient_identifier(text: str) -> str | None:
    # Estonian national personal code: 11 digits. Keep it only inside private output.
    match = re.search(r"(?<!\d)([1-6]\d{10})(?!\d)", text)
    return match.group(1) if match else None


def document_code(kind: str) -> tuple[str, str]:
    if kind == "vaktsineerimine":
        return "11369-6", "History of immunization narrative"
    if kind in {"confidoek", "confidooy", "medcovd19", "analuus"}:
        return "11502-2", "Laboratory report"
    return "34133-9", "Summarization of episode note"


def add_narrative(parent, text: str):
    narrative = node(parent, "text")
    node(narrative, "status", "generated")
    div = ET.SubElement(narrative, f"{{{XHTML}}}div")
    pre = ET.SubElement(div, f"{{{XHTML}}}pre")
    pre.text = text


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def fhir_json(element, resource_path: str = ""):
    """Translate the generated FHIR XML subset to normative FHIR JSON."""
    name = local_name(element.tag)
    if element.tag.startswith(f"{{{XHTML}}}"):
        rendered = ET.tostring(element, encoding="unicode")
        return rendered.replace("html:", "").replace(
            f'xmlns:html="{XHTML}"', f'xmlns="{XHTML}"'
        )
    if "value" in element.attrib and not list(element):
        return element.attrib["value"]
    is_resource = name in RESOURCE_TYPES
    current_path = name if is_resource else resource_path
    result = {"resourceType": name} if is_resource else {}
    for child in element:
        child_name = local_name(child.tag)
        if child.tag.startswith(f"{{{XHTML}}}"):
            result[child_name] = fhir_json(child)
            continue
        if name == "entry" and child_name in RESOURCE_TYPES:
            result["resource"] = fhir_json(child, child_name)
            continue
        child_path = f"{current_path}.{child_name}" if current_path else child_name
        value = fhir_json(child, child_path)
        if child_path in REPEATING_PATHS:
            result.setdefault(child_name, []).append(value)
        elif child_name in result:
            existing = result[child_name]
            result[child_name] = existing + [value] if isinstance(existing, list) else [existing, value]
        else:
            result[child_name] = value
    return result


def convert(path: Path, output: Path, exported_at: str) -> dict:
    raw_bytes = path.read_bytes()
    raw = raw_bytes.decode("utf-8", errors="replace")
    text = extract_text(raw)
    source_hash = hashlib.sha256(raw_bytes).hexdigest()
    stable = uuid.uuid5(uuid.NAMESPACE_URL, f"fastclinic:terviseportaal:{source_hash}")
    ids = {name: str(uuid.uuid5(stable, name)) for name in (
        "bundle", "composition", "patient", "encounter", "document", "device"
    )}
    urls = {name: f"urn:uuid:{value}" for name, value in ids.items()}
    kind = path.stem.split("-", 1)[-1]
    code, display = document_code(kind)
    date = source_date(text)
    timestamp = exported_at if exported_at.endswith("Z") else exported_at.replace("+00:00", "Z")

    bundle = resource("Bundle", ids["bundle"])
    identifier = node(bundle, "identifier")
    node(identifier, "system", "urn:ietf:rfc:3986")
    node(identifier, "value", urls["bundle"])
    node(bundle, "type", "document")
    node(bundle, "timestamp", timestamp)

    composition = resource("Composition", ids["composition"])
    identifier = node(composition, "identifier")
    node(identifier, "system", "urn:ietf:rfc:3986")
    node(identifier, "value", f"urn:sha256:{source_hash}")
    node(composition, "status", "final")
    type_node = node(composition, "type")
    coding = node(type_node, "coding")
    node(coding, "system", "http://loinc.org")
    node(coding, "code", code)
    node(coding, "display", display)
    reference(composition, "subject", urls["patient"])
    reference(composition, "encounter", urls["encounter"])
    node(composition, "date", f"{date}T00:00:00Z" if date else timestamp)
    reference(composition, "author", urls["device"])
    node(composition, "title", display)
    section = node(composition, "section")
    node(section, "title", "Source clinical document")
    section_text = node(section, "text")
    node(section_text, "status", "additional")
    div = ET.SubElement(section_text, f"{{{XHTML}}}div")
    pre = ET.SubElement(div, f"{{{XHTML}}}pre")
    pre.text = text
    reference(section, "entry", urls["document"])

    patient = resource("Patient", ids["patient"])
    identifier_value = patient_identifier(text)
    if identifier_value:
        identifier = node(patient, "identifier")
        node(identifier, "system", "https://fhir.ee/sid/pid/est/ni")
        node(identifier, "value", identifier_value)

    encounter = resource("Encounter", ids["encounter"])
    node(encounter, "status", "finished")
    class_node = node(encounter, "class")
    node(class_node, "system", "http://terminology.hl7.org/CodeSystem/v3-ActCode")
    node(class_node, "code", "AMB")
    node(class_node, "display", "ambulatory")
    reference(encounter, "subject", urls["patient"])
    if date:
        period = node(encounter, "period")
        node(period, "start", f"{date}T00:00:00Z")

    document = resource("DocumentReference", ids["document"])
    master = node(document, "masterIdentifier")
    node(master, "system", "urn:ietf:rfc:3986")
    node(master, "value", f"urn:sha256:{source_hash}")
    node(document, "status", "current")
    doc_type = node(document, "type")
    coding = node(doc_type, "coding")
    node(coding, "system", "http://loinc.org")
    node(coding, "code", code)
    node(coding, "display", display)
    reference(document, "subject", urls["patient"])
    content = node(document, "content")
    attachment = node(content, "attachment")
    node(attachment, "contentType", "text/html")
    node(attachment, "language", "et")
    node(attachment, "data", base64.b64encode(raw_bytes).decode("ascii"))
    node(attachment, "hash", base64.b64encode(bytes.fromhex(source_hash)).decode("ascii"))
    node(attachment, "title", path.name)

    device = resource("Device", ids["device"])
    node(device, "status", "active")
    device_name = node(device, "deviceName")
    node(device_name, "name", "FastClinic Terviseportaal HTML to FHIR R4 converter")
    node(device_name, "type", "model-name")

    for name, item in (
        ("composition", composition), ("patient", patient), ("encounter", encounter),
        ("document", document), ("device", device),
    ):
        entry(bundle, urls[name], item)

    tree = ET.ElementTree(bundle)
    ET.indent(tree, space="  ")
    tree.write(output, encoding="utf-8", xml_declaration=True)
    os.chmod(output, 0o600)
    ET.parse(output)  # well-formedness gate
    json_output = output.with_suffix("").with_suffix(".fhir.json")
    json_resource = fhir_json(bundle, "Bundle")
    json_output.write_text(json.dumps(json_resource, ensure_ascii=False, indent=2) + "\n")
    os.chmod(json_output, 0o600)
    return {
        "source": path.name,
        "xml": output.name,
        "json": json_output.name,
        "bundleId": ids["bundle"],
        "sourceSha256": source_hash,
        "fhirVersion": "4.0.1",
        "semanticLevel": "document-preserving",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, nargs="?", default=Path("data/private-health-records"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    output = (args.output or source / "fhir-r4").resolve()
    output.mkdir(parents=True, exist_ok=True)
    try:
        manifest = json.loads((source / "manifest.json").read_text())
        exported_at = manifest["exportedAt"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        exported_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    results = []
    for html_path in sorted(source.glob("*.html")):
        results.append(convert(html_path, output / f"{html_path.stem}.fhir.xml", exported_at))
    ndjson_lines = [
        (output / item["json"]).read_text().strip().replace("\n", "")
        for item in results
    ]
    ndjson_path = output / "bundles.ndjson"
    ndjson_path.write_text("\n".join(ndjson_lines) + ("\n" if ndjson_lines else ""))
    os.chmod(ndjson_path, 0o600)
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps({"resources": results}, indent=2) + "\n")
    os.chmod(manifest_path, 0o600)
    print(json.dumps({"converted": len(results), "formats": ["xml", "json", "ndjson"], "output": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
