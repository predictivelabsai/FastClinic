import json
from xml.etree import ElementTree as ET

import pytest

from web.fhir.ingress import FHIRIngressError, _xml_value, discover_inputs, normalize_bundle, read_bundles


def bundle(bundle_id="bundle-1"):
    return {
        "resourceType": "Bundle", "id": bundle_id, "type": "document",
        "entry": [
            {"fullUrl": "urn:uuid:composition-1", "resource": {
                "resourceType": "Composition", "id": "composition-1", "status": "final",
                "subject": {"reference": "urn:uuid:patient-1"},
                "encounter": {"reference": "urn:uuid:encounter-1"},
                "date": "2026-08-14T00:00:00Z", "title": "Synthetic test document",
            }},
            {"fullUrl": "urn:uuid:patient-1", "resource": {
                "resourceType": "Patient", "id": "patient-1",
                "identifier": [{"system": "https://example.test/pid", "value": "synthetic-1"}],
            }},
            {"fullUrl": "urn:uuid:encounter-1", "resource": {
                "resourceType": "Encounter", "id": "encounter-1", "status": "finished",
            }},
        ],
    }


def test_normalizes_document_and_index_fields():
    document = normalize_bundle(bundle())
    assert document.bundle_id == "bundle-1"
    assert document.patient_identifier_value == "synthetic-1"
    assert len(document.resources) == 3
    assert len(document.canonical_sha256) == 64


def test_rejects_non_document_bundle():
    payload = bundle()
    payload["type"] = "collection"
    with pytest.raises(FHIRIngressError, match="type=document"):
        normalize_bundle(payload)


def test_directory_prefers_json_over_duplicate_xml(tmp_path):
    (tmp_path / "record.fhir.json").write_text(json.dumps(bundle()))
    (tmp_path / "record.fhir.xml").write_text("<not-used />")
    assert [path.name for path in discover_inputs(tmp_path)] == ["record.fhir.json"]
    assert len(read_bundles(tmp_path)) == 1


def test_ingress_accepts_normative_bundle_entry_resource_wrapper():
    root = ET.fromstring("""<Bundle xmlns="http://hl7.org/fhir">
      <id value="bundle-1"/><type value="document"/>
      <entry><fullUrl value="urn:uuid:composition-1"/><resource>
        <Composition><id value="composition-1"/><status value="final"/>
        <subject><reference value="urn:uuid:patient-1"/></subject></Composition>
      </resource></entry>
      <entry><fullUrl value="urn:uuid:patient-1"/><resource>
        <Patient><id value="patient-1"/></Patient>
      </resource></entry>
    </Bundle>""")

    parsed = _xml_value(root)

    assert parsed["entry"][0]["resource"]["resourceType"] == "Composition"
    assert parsed["entry"][1]["resource"]["resourceType"] == "Patient"
