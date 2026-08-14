import json
from xml.etree import ElementTree as ET

import pytest

from web.fhir.ingress import FHIR_NS, _xml_value, normalize_bundle
from web.fhir.xml import FHIRXMLSerializationError, XHTML_NS, bundle_to_xml
from scripts.convert_health_exports_to_fhir import convert


def _document_bundle():
    # Deliberately shuffled to mirror PostgreSQL JSONB key ordering.
    return {
        "entry": [
            {
                "resource": {
                    "title": "Synthetic episode note",
                    "date": "2026-08-14T10:00:00Z",
                    "status": "final",
                    "type": {"coding": [{"display": "Episode note", "code": "34133-9", "system": "http://loinc.org"}]},
                    "id": "composition-1",
                    "subject": {"reference": "urn:uuid:patient-1"},
                    "section": [{
                        "title": "Clinical note",
                        "text": {
                            "div": '<div xmlns="http://www.w3.org/1999/xhtml"><p>Safe &amp; readable</p></div>',
                            "status": "additional",
                        },
                    }],
                    "resourceType": "Composition",
                },
                "fullUrl": "urn:uuid:composition-1",
            },
            {
                "resource": {
                    "identifier": [{"value": "synthetic-1", "system": "https://example.test/pid"}],
                    "id": "patient-1",
                    "resourceType": "Patient",
                },
                "fullUrl": "urn:uuid:patient-1",
            },
        ],
        "timestamp": "2026-08-14T10:00:00Z",
        "type": "document",
        "identifier": {"value": "urn:uuid:bundle-1", "system": "urn:ietf:rfc:3986"},
        "id": "bundle-1",
        "resourceType": "Bundle",
    }


def test_bundle_xml_uses_normative_namespaces_wrappers_and_order():
    raw = bundle_to_xml(_document_bundle())
    root = ET.fromstring(raw)

    assert raw.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')
    assert root.tag == f"{{{FHIR_NS}}}Bundle"
    assert [child.tag.rsplit("}", 1)[-1] for child in root] == [
        "id", "identifier", "type", "timestamp", "entry", "entry",
    ]
    first_entry = root.findall(f"{{{FHIR_NS}}}entry")[0]
    assert [child.tag.rsplit("}", 1)[-1] for child in first_entry] == ["fullUrl", "resource"]
    wrapper = first_entry.find(f"{{{FHIR_NS}}}resource")
    assert wrapper is not None
    assert wrapper[0].tag == f"{{{FHIR_NS}}}Composition"
    assert root.find(f".//{{{XHTML_NS}}}div") is not None


def test_generated_xml_round_trips_through_shared_ingress_adapter():
    parsed = _xml_value(ET.fromstring(bundle_to_xml(_document_bundle())))
    document = normalize_bundle(parsed, "download.fhir.xml", "xml")

    assert document.bundle_id == "bundle-1"
    assert document.patient_identifier_value == "synthetic-1"
    assert [resource["resourceType"] for _, resource in document.resources] == ["Composition", "Patient"]


def test_serializer_fails_closed_for_unknown_fields():
    payload = _document_bundle()
    payload["notAField"] = "unsafe"

    with pytest.raises(FHIRXMLSerializationError, match="Unsupported field"):
        bundle_to_xml(payload)


def test_existing_html_adapter_emits_normative_resource_wrappers(tmp_path):
    source = tmp_path / "synthetic-episode.html"
    output = tmp_path / "synthetic-episode.fhir.xml"
    source.write_text("<html><body><h1>Synthetic episode</h1><p>Start: 14.08.2026</p></body></html>")

    result = convert(source, output, "2026-08-14T10:00:00Z")
    root = ET.parse(output).getroot()
    entries = root.findall(f"{{{FHIR_NS}}}entry")
    generated_json = json.loads((tmp_path / result["json"]).read_text())

    assert len(entries) == 5
    assert all(entry.find(f"{{{FHIR_NS}}}resource") is not None for entry in entries)
    assert generated_json["entry"][0]["resource"]["resourceType"] == "Composition"
