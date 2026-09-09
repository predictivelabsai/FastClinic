import pytest
from cryptography.fernet import Fernet

from web import market, market_candidates
from web.market_countries import COUNTRIES, discovery_queries


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("FASTCLINIC_OPS_BACKEND", "sqlite")
    monkeypatch.setenv("FASTCLINIC_OPS_DB", str(tmp_path / "ops.sqlite"))
    monkeypatch.setenv("MARKET_CREDENTIALS_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("FASTCLINIC_MARKET_WORKER_ENABLED", "false")


def result(url="https://clinic.example/prices", title="Clinic | Prices"):
    return {
        "url": url,
        "title": title,
        "text": "Private clinic services and prices",
        "query": "private clinic prices",
        "retrieved_at": market.now(),
    }


def test_eea_registry_has_30_markets_and_900_query_campaign_budget():
    assert len(COUNTRIES) == 30
    assert {"LT", "LV", "EE", "RO", "IS", "LI", "NO"} <= set(COUNTRIES)
    assert all(len(discovery_queries(code)) == 15 for code in COUNTRIES)
    assert 2 * sum(len(discovery_queries(code)) for code in COUNTRIES) == 900


def test_versioned_treatment_hierarchy_maps_raw_services_without_replacing_them():
    from web import market_taxonomy

    assert market_taxonomy.classify("Total knee replacement") == "orthopaedics:knee"
    assert market_taxonomy.classify("Vitamin IV infusion") == "wellness:IV therapy"
    market.ingest(
        "taxonomy-run",
        [{
            "country": "EE", "domain": "clinic.example", "clinic": "Clinic",
            "ownership_evidence": "Private clinic", "service": "Vitamin IV infusion",
            "original_name": "Vitamiiniinfusioon", "price": "50", "price_max": None,
            "price_type": "exact", "currency": "EUR",
            "source_url": "https://clinic.example/prices", "retrieved_at": market.now(),
            "published_at": None, "provider": "exa", "evidence": "Vitamiiniinfusioon 50 EUR",
        }],
    )
    mapping = market.rows("SELECT * FROM market_service_taxonomy")[0]
    assert mapping["taxonomy_id"] == "wellness:IV therapy"
    assert market.observations()[0]["original_name"] == "Vitamiiniinfusioon"


def test_candidates_survive_strict_extraction_and_deduplicate_by_domain():
    first = market_candidates.capture([result()], "EE", "run-one")
    second = market_candidates.capture(
        [result("https://clinic.example/about", "Clinic | About")], "EE", "run-two"
    )
    assert first == {"seen": 1, "new": 1}
    assert second == {"seen": 1, "new": 0}
    rows = market_candidates.items("EE")
    assert len(rows) == 1 and rows[0]["state"] == "discovered"
    assert rows[0]["official_domain"] == "clinic.example"


def test_mmg_import_creates_unverified_profile_candidates(monkeypatch):
    monkeypatch.setattr(
        market_candidates,
        "scrape_url",
        lambda url: {
            "url": url,
            "retrieved_at": market.now(),
            "text": "[Monza](/hospitals/romania/monza-hospital) "
            "[Saint James](/hospitals/malta/saint-james-hospital)",
        },
    )
    stats = market_candidates.import_mmg()
    assert stats == {"seen": 2, "new": 2, "countries": 2}
    monza = market_candidates.items("RO")[0]
    assert monza["source_type"] == "mymedicalgateway"
    assert monza["official_domain"] == "" and monza["state"] == "discovered"


def test_review_promotes_official_url_without_claiming_verification():
    from web import market_watchlist

    market_candidates.capture([result()], "EE")
    candidate = market_candidates.items("EE")[0]
    watchlist_id = market_candidates.promote(
        candidate["id"],
        actor="reviewer@example.test",
        official_url="https://clinic.example/",
        name="Clinic",
        cities="Tallinn",
        segment="Multi-specialty clinic",
    )
    assert market_candidates.get(candidate["id"])["state"] == "watchlisted"
    watched = market_watchlist.get(watchlist_id)
    assert watched["origin"] == "candidate" and watched["country"] == "EE"
    coverage = {row["country"]: row for row in market_candidates.coverage()}
    assert coverage["EE"]["verified"] == 0


def test_campaign_queue_is_country_scoped_and_worker_advances(monkeypatch):
    from web import search_provider

    market.save_config({**market.config(), "weekly": False})
    assert market_candidates.queue_campaign(["EE", "RO"], "admin@example.test") == 2
    monkeypatch.setattr(search_provider, "resolve", lambda actor=None: "key")
    monkeypatch.setattr(
        market,
        "collect",
        lambda run_id, cfg, owner, actor=None: {
            "errors": 0,
            "deferred_pages": 0,
            "truncated_pages": 0,
            "pages": 1,
        },
    )
    monkeypatch.setattr(market_candidates, "sync_verified", lambda: 0)
    market.tick()
    campaign = {r["country"]: r for r in market_candidates.coverage()}
    assert campaign["EE"]["campaign_status"] == "review required"
    assert campaign["RO"]["campaign_status"] == "queued"
    run = market.rows("SELECT trigger_kind,config FROM market_run")[0]
    assert run["trigger_kind"] == "campaign" and '"countries": ["EE"]' in run["config"]
