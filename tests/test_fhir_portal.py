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

