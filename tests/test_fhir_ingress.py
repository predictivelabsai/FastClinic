import json

import pytest

from web.fhir.ingress import FHIRIngressError, discover_inputs, normalize_bundle, read_bundles


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

