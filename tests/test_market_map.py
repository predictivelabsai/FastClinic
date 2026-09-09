import json
from pathlib import Path

import pytest
from web import market, market_map, market_assistant


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("FASTCLINIC_OPS_BACKEND", "sqlite")
    monkeypatch.setenv("FASTCLINIC_OPS_DB", str(tmp_path / "ops.sqlite"))


def clinic():
    return dict(
        id="site",
        hospital_id="hospital",
        name="Clinic",
        address="Kotka 12",
        city="Tallinn",
        country="EE",
    )


def match():
    return {
        "lat": "59.414",
        "lon": "24.729",
        "address": {
            "house_number": "12",
            "road": "Kotka",
            "city": "Tallinn",
            "country_code": "ee",
        },
    }


def test_geocoder_requires_country_street_house_and_city():
    c = clinic()
    r = match()
    assert market_map.match_geocode(c, [r]) == r
    for field, value in [
        ("country_code", "lv"),
        ("house_number", "13"),
        ("road", "Other street"),
        ("city", "Tartu"),
    ]:
        bad = {**r, "address": {**r["address"], field: value}}
        assert market_map.match_geocode(c, [bad]) is None
    assert market_map.match_geocode(c, [r, {**r, "lat": "59.9"}]) is None


def test_save_multiple_branches_idempotently():
    h = {
        "id": "hospital",
        "name": "Clinic",
        "country": "EE",
        "domain": "clinic.example",
    }
    loc = dict(
        address="Kotka 12",
        city="Tallinn",
        country="EE",
        source_url="https://clinic.example/contact",
        evidence="Kotka 12, Tallinn",
        retrieved_at=market.now(),
    )
    market_map.save_clinics(
        h, [loc, loc, {**loc, "address": "Kalevi 4", "city": "Tartu"}]
    )
    assert len(market_map.clinics()) == 2
    market_map.save_clinics(
        h, [{**loc, "source_url": "https://unrelated.example/contact"}]
    )
    assert len(market_map.clinics()) == 2


def test_geocoding_cached_and_unmatched_not_pinned(monkeypatch):
    h = {
        "id": "hospital",
        "name": "Clinic",
        "country": "EE",
        "domain": "clinic.example",
    }
    loc = dict(
        address="Kotka 12",
        city="Tallinn",
        country="EE",
        source_url="https://clinic.example/contact",
        evidence="Kotka 12, Tallinn",
        retrieved_at=market.now(),
    )
    market_map.save_clinics(h, [loc])
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return [match()]

    monkeypatch.setattr(
        market_map.requests, "get", lambda *a, **k: (calls.append(k) or Response())
    )
    monkeypatch.setattr(market_map.time, "sleep", lambda _: None)
    site = market_map.clinics()[0]
    market_map.geocode(site)
    market_map.geocode(site)
    assert len(calls) == 1
    assert calls[0]["params"]["countrycodes"] == "ee"
    assert "FastClinic" in calls[0]["headers"]["User-Agent"]
    assert market_map.clinics()[0]["geocode_status"] == "located"


def test_address_extraction_rejects_unverifiable_or_foreign_source(monkeypatch):
    h = {
        "id": "hospital",
        "name": "Clinic",
        "country": "EE",
        "domain": "clinic.example",
    }
    source = {
        "url": "https://clinic.example/contact",
        "text": "Kotka 12, Tallinn",
        "retrieved_at": market.now(),
    }
    location = {
        "address": "Kotka 12",
        "city": "Tallinn",
        "country": "EE",
        "source_url": source["url"],
        "evidence": source["text"],
    }
    response = lambda value: {
        "choices": [{"message": {"content": json.dumps({"locations": [value]})}}]
    }
    monkeypatch.setattr(market_map, "_post", lambda *a, **k: response(location))
    assert len(market_map.extract_addresses(h, [source])) == 1
    monkeypatch.setattr(
        market_map,
        "_post",
        lambda *a, **k: response({**location, "address": "Imagined 7"}),
    )
    assert market_map.extract_addresses(h, [source]) == []


def test_map_is_zoomable_and_popup_uses_text_nodes():
    from web.market_views import map_view
    from fasthtml.common import to_xml

    html = to_xml(map_view())
    assert "L.map('market-map'" in html
    assert "scrollWheelZoom:true" in html
    assert "textContent=p.name" in html
    assert "OpenStreetMap" in html and "google" not in html.lower()


def test_assistant_questions_and_context_match_market_page():
    from web.layout import _sample_cards, right_pane_chat
    from fasthtml.common import to_xml

    html = to_xml(_sample_cards("market"))
    assert "competitor prices" in html
    assert "patients" not in html
    assert 'name="page_context" value="market-map"' in to_xml(
        right_pane_chat("test", "market-map")
    )
    assert market_assistant.context_filters("/market/clinics/abc?country=EE") == {
        "country": "EE",
        "hospital": "abc",
    }
    assert market_assistant.context_filters("/patients?hospital=abc") == {}


def test_dashboard_and_watchlist_editor_render_visual_first_workspace():
    from fasthtml.common import to_xml
    from web.market_views import watchlist_editor, workspace

    dashboard = to_xml(workspace("csrf"))
    assert "Lithuania Wellness Competition" in dashboard
    assert "priority-competitors" in dashboard
    assert "market-chart-grid" in dashboard
    assert "Apply filters" not in dashboard
    editor = to_xml(watchlist_editor("csrf"))
    assert "Watchlist Editor" in editor
    assert "Deep scrape now" in editor
    assert "SYNC Longevity Clinic" in editor


def test_seed_has_all_countries_and_only_regular_source_backed_prices():
    data = json.loads(
        (Path(__file__).parents[1] / "data/market/baseline.json").read_text()
    )
    assert {r["country"] for r in data["observations"]} == {"EE", "LV", "LT"}
    assert {r["provider"] for r in data["observations"]} == {"exa"}
    assert all(
        r["source_url"].startswith("https://") and r["retrieved_at"] and r["evidence"]
        for r in data["observations"]
    )
    assert not any(
        "saatekirjaga" in r["evidence"].lower() for r in data["observations"]
    )
