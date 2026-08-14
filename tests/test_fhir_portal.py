from fasthtml.common import to_xml
from fastapi.testclient import TestClient

from web import fhir_portal


def test_narrative_extracts_text_without_markup():
    payload = {"entry": [{"resource": {"resourceType": "Composition", "section": [{
        "text": {"div": '<div xmlns="http://www.w3.org/1999/xhtml"><pre>Safe &amp; visible</pre></div>'}
    }]}}]}
    assert fhir_portal._narrative(payload) == "Safe & visible"


def test_records_query_normalizes_email(monkeypatch):
    captured = {}
    monkeypatch.setattr(fhir_portal.db, "query", lambda sql, params: captured.update(params=params) or [])
    assert fhir_portal.records_for_email(" User@Example.COM ") == []
    assert captured["params"] == ("user@example.com",)


def test_preformatted_episode_note_becomes_structured_safe_html():
    raw = """<div xmlns="http://www.w3.org/1999/xhtml" onclick="bad()"><pre>ASSESSMENT\nDiagnosis: Example\n- First point\n- Second point</pre><script>alert(1)</script><a href="javascript:alert(2)">unsafe</a><a href="https://example.test">safe</a></div>"""

    rendered = fhir_portal._sanitize_narrative(raw)

    assert '<h4>ASSESSMENT</h4>' in rendered
    assert '<strong>Diagnosis:</strong> Example' in rendered
    assert "<ul><li>First point</li><li>Second point</li></ul>" in rendered
    assert "script" not in rendered
    assert "alert(1)" not in rendered
    assert "javascript:" not in rendered
    assert 'href="https://example.test"' in rendered
    assert "onclick" not in rendered


def test_record_view_links_authorized_xml_download(monkeypatch):
    payload = {"resourceType": "Bundle", "entry": [{"resource": {
        "resourceType": "Composition",
        "section": [{"title": "Episode", "text": {
            "status": "additional",
            "div": '<div xmlns="http://www.w3.org/1999/xhtml"><p>Readable note</p></div>',
        }}],
    }}]}
    monkeypatch.setattr(fhir_portal, "record_for_email", lambda email, bundle_id: {
        "bundle_id": bundle_id,
        "document_date": "2026-08-14",
        "title": "Synthetic episode",
        "source_format": "json",
        "payload": payload,
    })

    rendered = to_xml(fhir_portal.record_view("person@example.test", "bundle-1"))

    assert 'href="/my-records/bundle-1/download"' in rendered
    assert 'download="bundle-1.fhir.xml"' in rendered
    assert "Readable note" in rendered


def test_xml_download_reuses_account_authorization(monkeypatch):
    monkeypatch.setattr(fhir_portal, "record_for_email", lambda email, bundle_id: None)
    assert fhir_portal.xml_for_email("other@example.test", "bundle-1") is None


def test_xml_download_route_is_not_shadowed_by_static_files(monkeypatch):
    import web_app

    monkeypatch.setattr(web_app, "_auth", lambda session: "person@example.test")
    monkeypatch.setattr(web_app.fhir_portal, "xml_for_email", lambda email, bundle_id: (
        b'<?xml version="1.0" encoding="UTF-8"?><Bundle xmlns="http://hl7.org/fhir"/>'
    ))

    with TestClient(web_app.app) as client:
        response = client.get("/my-records/bundle-1/download")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/fhir+xml")
    assert response.headers["content-disposition"] == 'attachment; filename="bundle-1.fhir.xml"'
    assert response.headers["cache-control"] == "private, no-store"
