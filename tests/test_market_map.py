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


def test_geocoder_accepts_local_inflection_and_municipality_suffix():
    c = {**clinic(), "city": "Rīgā, Rīgas valstspilsēta", "country": "LV"}
    r = {
        **match(),
        "address": {
            "house_number": "12",
            "road": "Kotka iela",
            "city": "Rīga",
            "country_code": "lv",
        },
    }
    assert market_map.match_geocode(c, [r]) == r


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


def test_translated_address_variants_do_not_duplicate_a_branch():
    h = {"id": "hospital", "name": "Clinic", "country": "LV", "domain": "clinic.example"}
    base = {
        "country": "LV", "postal_code": "", "phone": "", "retrieved_at": market.now(),
        "source_url": "https://clinic.example/contact", "evidence": "Dzirnavu iela 57а, Rīga",
    }
    market_map.save_clinics(h, [{**base, "address": "Dzirnavu iela 57а", "city": "Rīga"}])
    market_map.save_clinics(h, [{**base, "address": "Dzirnavu street 57a", "city": "Riga"}])
    assert len(market_map.clinics("LV")) == 1


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


def test_geocoder_uses_localized_freeform_fallback(monkeypatch):
    h = {
        "id": "hospital", "name": "Northway", "country": "LT",
        "domain": "clinic.example",
    }
    loc = {
        "address": "Dragūnų str. 2", "city": "Klaipėda", "country": "LT",
        "source_url": "https://clinic.example/contact",
        "evidence": "Dragūnų str. 2, Klaipėda", "retrieved_at": market.now(),
    }
    market_map.save_clinics(h, [loc])
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    fallback = {
        "lat": "55.7502", "lon": "21.1300", "display_name": "Northway",
        "category": "amenity",
        "address": {
            "house_number": "2", "road": "Dragūnų g.", "city": "Klaipėda",
            "country_code": "lt", "amenity": "Northway",
        },
    }

    def get(*args, **kwargs):
        calls.append(kwargs["params"])
        return Response([] if "street" in kwargs["params"] else [fallback])

    monkeypatch.setattr(market_map.requests, "get", get)
    monkeypatch.setattr(market_map.time, "sleep", lambda _: None)
    market_map.geocode(market_map.clinics()[0])
    assert calls[0]["street"] == "Dragūnų g. 2"
    assert calls[1]["q"].startswith("Dragūnų g. 2, Klaipėda")
    assert market_map.clinics()[0]["geocode_status"] == "located"


def test_geocoder_prefers_named_clinic_at_shared_address():
    c = {**clinic(), "name": "Northway"}
    generic = {**match(), "lat": "59.4145", "category": "building"}
    named = {
        **match(), "display_name": "Northway medical clinic", "category": "amenity",
    }
    assert market_map.match_geocode(c, [generic, named]) == named


def test_geocoder_cleans_local_street_names_and_unit_suffixes():
    assert market_map._clean_geocode_address({
        **clinic(), "country": "LV", "address": "Brīvības gatve 234-75",
    }) == "Brīvības gatve 234"
    assert market_map._clean_geocode_address({
        **clinic(), "country": "LV", "address": "Tālivalža street 2a",
    }) == "Tālivalža iela 2a"
    assert market_map._clean_geocode_address({
        **clinic(), "country": "LV", "address": "Ģimnāzijas 10A-2а",
    }) == "Ģimnāzijas iela 10A"
    assert market_map._clean_geocode_address({
        **clinic(), "country": "RO", "address": "Strada Nicolae Jiga, Nr. 13",
    }) == "Strada Nicolae Jiga 13"
    assert market_map._clean_geocode_city({
        **clinic(), "country": "RO", "city": "Oras Pantelimon",
    }) == "Pantelimon"


def test_geocoder_accepts_named_venue_address_without_street_syntax():
    c = {
        **clinic(), "name": "Heal Kliinik",
        "address": "Tallinn, Ülemiste City, Tervisemaja 2, 5. korrusel",
    }
    result = {
        "lat": "59.4213526", "lon": "24.8065058",
        "name": "Ülemiste tervisemaja 2", "category": "building",
        "address": {
            "house_number": "12/1", "road": "Sepapaja", "city": "Tallinn",
            "country_code": "ee",
        },
    }
    assert market_map.match_geocode(c, [result]) == result


def test_photon_fallback_is_converted_to_validated_address_result():
    results = market_map._photon_features({"features": [{
        "geometry": {"coordinates": [24.7006625, 59.399555]},
        "properties": {
            "name": "Haavakliinik", "street": "Juhan Sütiste tee",
            "housenumber": "17/1", "city": "Tallinn", "countrycode": "EE",
            "osm_key": "building",
        },
    }]})
    c = {
        **clinic(), "name": "Haavakliinik", "address": "J. Sütiste tee 17/1",
    }
    assert market_map.match_geocode(c, results) == results[0]


def test_official_address_map_link_supplies_final_coordinates(monkeypatch):
    c = {
        **clinic(), "name": "KliinikPluss", "address": "Tulika 19c",
        "source_url": "https://clinic.example/contact",
        "evidence": "Tulika 19c, Tallinn",
    }
    text = (
        "[Tulika 19c, Tallinn](https://www.google.com/maps/dir/start/"
        "Tulika+19c/data=!2m2!1d24.7200972!2d59.4287324)"
    )
    monkeypatch.setattr(
        market_map,
        "scrape_url",
        lambda url: {"url": url, "text": text, "retrieved_at": market.now()},
    )
    assert market_map._official_map_match(c) == {
        "lat": "59.4287324", "lon": "24.7200972",
    }


def test_pending_addresses_are_drained_to_mapped(monkeypatch):
    h = {"id": "hospital", "name": "Clinic", "country": "EE", "domain": "clinic.example"}
    loc = {
        "address": "Kotka 12", "city": "Tallinn", "country": "EE",
        "source_url": "https://clinic.example/contact", "evidence": "Kotka 12, Tallinn",
        "retrieved_at": market.now(),
    }
    market_map.save_clinics(h, [loc])

    def resolve(clinic):
        with market_map.connect() as connection:
            connection.execute(
                "UPDATE market_clinic SET geocode_status='located',latitude='59.4',longitude='24.7' WHERE id=?",
                (clinic["id"],),
            )
            connection.commit()

    monkeypatch.setattr(market_map, "geocode", resolve)
    assert market_map.geocode_pending() == {
        "attempted": 1, "mapped": 1, "needs_review": 0, "pending": 0,
    }
    assert market_map.clinics()[0]["geocode_status"] == "located"


def test_review_addresses_can_be_explicitly_retried(monkeypatch):
    h = {"id": "hospital", "name": "Clinic", "country": "EE", "domain": "clinic.example"}
    loc = {
        "address": "Kotka 12", "city": "Tallinn", "country": "EE",
        "source_url": "https://clinic.example/contact", "evidence": "Kotka 12, Tallinn",
        "retrieved_at": market.now(),
    }
    market_map.save_clinics(h, [loc])
    with market_map.connect() as connection:
        connection.execute("UPDATE market_clinic SET geocode_status='needs_review'")
        connection.commit()
    monkeypatch.setattr(market_map, "geocode", lambda clinic: None)
    assert market_map.geocode_pending()["attempted"] == 0
    assert market_map.geocode_pending(retry_review=True)["attempted"] == 1


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


def test_address_source_discovery_follows_same_domain_contact_links(monkeypatch):
    hospital = {
        "id": "hospital",
        "name": "Clinic",
        "country": "EE",
        "domain": "clinic.example",
        "source_url": "https://clinic.example/services",
    }
    pages = {
        "https://clinic.example/services": "Services [Kontakt](/kontakt/)",
        "https://clinic.example/": "Footer [Kontakt](/kontakt/)",
        "https://clinic.example/kontakt/": "Aadress: Kotka 12, Tallinn",
    }

    def scrape(url):
        if url not in pages:
            raise RuntimeError("not found")
        return {"url": url, "text": pages[url], "retrieved_at": market.now(), "provider": "direct"}

    monkeypatch.setattr(market_map, "scrape_url", scrape)
    sources = market_map.discover_address_sources(hospital)
    assert sources[0]["url"] == "https://clinic.example/kontakt/"
    assert not any(market_map.domain(s["url"]) != "clinic.example" for s in sources)


def test_pending_address_repair_rotates_and_records_attempt(monkeypatch):
    for index in range(2):
        market.ingest(
            "seed",
            [{
                "country": "EE", "domain": f"clinic{index}.example", "clinic": f"Clinic {index}",
                "ownership_evidence": "Private clinic", "service": "Consultation",
                "original_name": "Consultation", "price": "50", "price_max": None,
                "price_type": "exact", "currency": "EUR",
                "source_url": f"https://clinic{index}.example/prices", "retrieved_at": market.now(),
                "published_at": None, "provider": "exa", "evidence": "Consultation 50 EUR",
            }],
        )
    calls = []
    monkeypatch.setattr(
        market_map,
        "refresh",
        lambda hospital, api_key=None, sources=None, **kwargs: (calls.append(hospital["id"]) or {"sources": 1, "locations": 0, "added": 0}),
    )
    assert market_map.repair_pending(limit=1)["attempted"] == 1
    assert market_map.repair_pending(limit=1)["attempted"] == 1
    assert len(set(calls)) == 2


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
    from web.market_search import COUNTRIES
    from web.market_views import watchlist_editor, workspace

    dashboard = to_xml(workspace("csrf"))
    assert "Lithuania Wellness Competition" in dashboard
    assert all(country in dashboard for country in COUNTRIES.values())
    assert "priority-competitors" in dashboard
    assert "market-chart-grid" in dashboard
    assert "Apply filters" not in dashboard
    editor = to_xml(watchlist_editor("csrf"))
    assert "Watchlist Editor" in editor
    assert "Deep scrape now" in editor
    assert "Discovery candidate review" in editor
    assert "Queue all 30 EEA markets" in editor
    assert "SYNC Longevity Clinic" in editor


def test_country_dashboard_and_clinic_drilldown_are_scoped():
    from fasthtml.common import to_xml
    from web.market_views import clinic_detail, workspace

    market.ingest(
        "seed",
        [{
            "country": "EE", "domain": "clinic.example", "clinic": "Clinic",
            "ownership_evidence": "Private clinic", "service": "Consultation",
            "original_name": "Consultation", "price": "50", "price_max": None,
            "price_type": "exact", "currency": "EUR", "source_url": "https://clinic.example/prices",
            "retrieved_at": market.now(), "published_at": None, "provider": "exa",
            "evidence": "Consultation 50 EUR",
        }],
    )
    hospital = market.rows("SELECT id FROM market_hospital WHERE domain='clinic.example'")[0]
    estonia = to_xml(workspace("csrf", country="EE"))
    assert "Estonia Wellness Competition" in estonia and "Clinic" in estonia
    detail = to_xml(clinic_detail("csrf", hospital["id"]))
    assert "‹ Back to Dashboard" in detail and "Observed services and prices" in detail
    assert "Estonia Wellness Competition" not in detail


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
