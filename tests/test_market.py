from datetime import datetime, timedelta, timezone
import json

import pytest
from cryptography.fernet import Fernet
from web import market, search_provider


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("FASTCLINIC_OPS_BACKEND", "sqlite")
    monkeypatch.setenv("FASTCLINIC_OPS_DB", str(tmp_path / "ops.sqlite"))
    monkeypatch.setenv("MARKET_CREDENTIALS_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("FASTCLINIC_MARKET_WORKER_ENABLED", "false")


def observation(stamp, price="100", kind="exact", name="Consultation"):
    return dict(
        country="EE",
        domain="clinic.example",
        clinic="Private Clinic",
        ownership_evidence="Private clinic",
        service=name,
        original_name=name,
        price=price,
        price_max=None,
        price_type=kind,
        currency="EUR",
        source_url="https://clinic.example/prices",
        retrieved_at=stamp,
        published_at=None,
        provider="exa",
        evidence=name + " " + str(price),
    )


def test_defaults_include_future_entries_and_exa_only():
    cfg = market.config()
    assert set(cfg["countries"]) == {"LT", "LV", "EE"}
    assert cfg["hospitals"] == cfg["treatments"] == ["*"]
    assert cfg["providers"] == ["exa"] and cfg["weekly"]
    with pytest.raises(ValueError):
        market.save_config({**cfg, "providers": ["tavily"]})
    with pytest.raises(ValueError):
        market.save_config({**cfg, "hospitals": ["*", "fake"]})


def test_history_is_idempotent_and_missing_week_is_not_unchanged():
    market.ingest("one", [observation("2026-08-24T10:00:00+00:00")])
    market.ingest("one", [observation("2026-08-24T10:00:00+00:00")])
    assert len(market.observations()) == 1
    market.ingest("two", [observation("2026-08-31T10:00:00+00:00", "120")])
    r = market.latest_prices()[0]
    assert r["change"] == 20 and r["change_pct"] == 20
    market.ingest("three", [observation("2026-09-14T10:00:00+00:00", "125")])
    assert market.latest_prices()[0]["change"] is None
    assert len(market.observations()) == 3


def test_price_types_and_different_tariffs_do_not_mix():
    market.ingest("one", [observation("2026-08-31T10:00:00+00:00", "100")])
    market.ingest(
        "two",
        [
            observation("2026-09-07T10:00:00+00:00", "80", "from"),
            observation(
                "2026-09-07T10:00:00+00:00", "90", "exact", "Follow-up consultation"
            ),
        ],
    )
    assert all(r["change"] is None for r in market.latest_prices())


def test_weekly_and_manual_queue_deduplicate(monkeypatch):
    first = market.enqueue("a", at="2026-09-07T10:00:00+00:00")
    assert market.enqueue("b", at="2026-09-07T10:01:00+00:00") == first
    with market.connect() as c:
        c.execute("UPDATE market_run SET status='completed'")
        c.commit()
    weekly = market.enqueue("scheduler", "weekly", at="2026-09-07T11:00:00+00:00")
    with market.connect() as c:
        c.execute("UPDATE market_run SET status='completed'")
        c.commit()
    assert (
        market.enqueue("scheduler", "weekly", at="2026-09-08T11:00:00+00:00") == weekly
    )
    assert (
        market.enqueue("scheduler", "weekly", at="2026-09-14T11:00:00+00:00") != weekly
    )


def test_worker_completes_and_releases_lease(monkeypatch):
    market.save_config({**market.config(), "weekly": False})
    ident = market.enqueue("alice")
    called = []

    def collect(run, cfg, owner, actor):
        called.append((run, actor, cfg["providers"]))
        return dict(errors=0, deferred_pages=0, truncated_pages=0, pages=1)

    monkeypatch.setattr(market, "collect", collect)
    market.tick()
    assert called == [(ident, "alice", ["exa"])]
    assert market.rows("SELECT status FROM market_run")[0]["status"] == "completed"
    assert market.rows("SELECT owner FROM market_lock")[0]["owner"] == ""


def test_worker_does_not_steal_live_lease(monkeypatch):
    with market.connect() as c:
        c.execute(
            "UPDATE market_lock SET owner=?,expires_at=?",
            ("other", (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()),
        )
        c.commit()
    monkeypatch.setattr(market, "collect", lambda *a: pytest.fail("Lease stolen"))
    market.tick()
    assert market.rows("SELECT owner FROM market_lock")[0]["owner"] == "other"


def test_encrypted_user_keys_and_shared_fallback(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "environment-secret")
    search_provider.save("alice", "alice-private-secret")
    search_provider.save(search_provider.SHARED, "scheduled-secret")
    assert search_provider.resolve("alice") == "alice-private-secret"
    assert search_provider.resolve("bob") == "scheduled-secret"
    assert search_provider.resolve() == "scheduled-secret"
    raw = market.rows("SELECT * FROM search_provider_credentials")
    assert "alice-private-secret" not in json.dumps(raw)
    search_provider.remove("alice")
    assert search_provider.resolve("alice") == "scheduled-secret"
    search_provider.remove(search_provider.SHARED)
    assert search_provider.resolve() == "environment-secret"


def test_no_insecure_key_fallback(monkeypatch):
    monkeypatch.delenv("MARKET_CREDENTIALS_KEY", raising=False)
    monkeypatch.delenv("BYOK_ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValueError, match="persistent Fernet key"):
        search_provider.save("alice", "secret")


def test_market_navigation_order_and_staff_permissions(monkeypatch):
    from web.layout import NAV_ITEMS
    from web import access

    names = [section for section, _ in NAV_ITEMS]
    assert names[names.index("COMMUNICATIONS") + 1] == "MARKET"
    monkeypatch.setenv("FASTCLINIC_ADMIN_EMAIL", "admin@example.test")
    for role in ("practitioner", "receptionist", "billing"):
        email = f"{role}@example.test"
        access.set_profile(email, role)
        assert access.can(email, "market") and access.can(email, "search-provider")
        assert not access.can(email, "market-config")
    access.set_profile("patient@example.test", "patient")
    assert not access.can("patient@example.test", "market")


def test_routes_csrf_scope_keys_and_chart_rendering(monkeypatch):
    from fasthtml.common import fast_app, Div
    from starlette.testclient import TestClient
    from starlette.responses import Response
    from web import market_views

    app, rt = fast_app(secret_key="test-secret", live=False)

    @rt("/test-login")
    def login(session, role: str = "staff"):
        session["user_email"] = role + "@example.test"
        return "ok"

    def require(session, permission):
        email = session.get("user_email")
        if (
            not email
            or email.startswith("patient")
            or (permission == "market-config" and not email.startswith("admin"))
        ):
            return email, Response("Denied", status_code=403)
        return email, None

    market_views.register(rt, app, require, lambda session, key, content: Div(content))
    import re

    with TestClient(app) as client:
        assert client.get("/market/competitive-intelligence").status_code == 403
        client.get("/test-login")
        html = client.get("/integrations/search-provider").text
        csrf = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        assert client.post("/market/search", data={}).status_code == 403
        assert (
            client.post(
                "/integrations/search-provider",
                data={
                    "csrf": csrf,
                    "scope": "shared",
                    "action": "save",
                    "search_provider": "exa",
                    "api_key": "secret",
                },
            ).status_code
            == 403
        )
        response = client.post(
            "/integrations/search-provider",
            data={
                "csrf": csrf,
                "scope": "personal",
                "action": "save",
                "search_provider": "exa",
                "api_key": "my-private-test-key",
            },
        )
        assert (
            response.status_code == 200 and "my-private-test-key" not in response.text
        )
        assert search_provider.resolve("staff@example.test") == "my-private-test-key"
        assert client.get("/admin/market").status_code == 403
        market.ingest("one", [observation(market.now())])
        sid = market.rows("SELECT id FROM market_service")[0]["id"]
        html = client.get("/market/competitive-intelligence?service=" + sid).text
        assert "Plotly.newPlot" in html and "100 EUR" in html
        client.get("/test-login?role=admin")
        assert client.get("/admin/market").status_code == 200
        client.get("/test-login?role=patient")
        assert client.post("/market/search", data={"csrf": csrf}).status_code == 403


def test_collection_uses_exa_and_applies_country_service_scope(monkeypatch):
    from web import market_map

    cfg = {**market.config(), "countries": ["EE"], "max_queries": 2, "max_pages": 2}
    calls = []
    stamp = market.now()
    source = {
        "provider": "exa",
        "url": "https://clinic.example/prices",
        "text": "Private clinic. Consultation 100 EUR",
        "retrieved_at": stamp,
        "country": "EE",
    }

    def search(provider, query, **kwargs):
        calls.append((provider, kwargs["api_key"]))
        return [source]

    monkeypatch.setattr(market, "search", search)
    monkeypatch.setattr(search_provider, "resolve", lambda owner: "requester-key")
    monkeypatch.setattr(
        market,
        "extract_services",
        lambda source: [observation(stamp), {**observation(stamp), "country": "LV"}],
    )
    from web import market_search

    monkeypatch.setattr(market_search, "enrich_ownership", lambda source, key: source)
    monkeypatch.setattr(market_map, "refresh", lambda *a: None)
    stats = market.collect("run", cfg, "worker", "alice")
    assert calls == [("exa", "requester-key")]
    assert stats["queries"] <= cfg["max_queries"] and stats["pages"] == 1
    assert {r["country"] for r in market.observations()} == {"EE"}


def test_watchlist_is_seeded_editable_and_pause_preserves_entry():
    from web import market_watchlist

    entries = market_watchlist.items()
    assert {r["name"] for r in entries} >= {
        "SYNC Longevity Clinic",
        "AUM Wellness Clinic",
        "Northway",
        "Meliva",
    }
    ident = market_watchlist.save(
        "",
        name="New Wellness Clinic",
        country="LT",
        segment="IV / longevity specialist",
        cities="Vilnius, Kaunas",
        positioning="Manually curated target",
        urls="https://wellness.example/services\nhttps://wellness.example/about",
        priority=2,
        active=True,
        actor="staff@example.test",
    )
    saved = market_watchlist.get(ident)
    assert saved["origin"] == "manual" and len(saved["urls"]) == 2
    market_watchlist.save(
        ident,
        name=saved["name"],
        country=saved["country"],
        segment=saved["segment"],
        cities=", ".join(saved["cities"]),
        positioning=saved["positioning"],
        urls="\n".join(saved["urls"]),
        priority=saved["priority"],
        active=False,
        actor="staff@example.test",
    )
    assert not market_watchlist.get(ident)["active"]
    assert ident not in {r["id"] for r in market_watchlist.items(active_only=True)}


def test_direct_watchlist_scrape_uses_no_exa_search(monkeypatch):
    from web import market_map, market_search, market_watchlist

    item = market_watchlist.get("sync")
    cfg = {
        **market.config(),
        "mode": "direct",
        "watchlist_ids": [item["id"]],
        "countries": ["LT"],
        "max_pages": len(item["urls"]),
        "max_queries": 24,
    }
    stamp = market.now()
    fetched = []

    def scrape(url):
        fetched.append(url)
        return {
            "url": url,
            "text": "Private clinic. Vitamin IV 99 EUR",
            "provider": "direct",
            "retrieved_at": stamp,
            "published_at": None,
        }

    monkeypatch.setattr(market_search, "scrape_url", scrape)
    monkeypatch.setattr(market, "search", lambda *a, **k: pytest.fail("Exa search used"))
    monkeypatch.setattr(
        market,
        "extract_services",
        lambda source: [
            {
                **observation(stamp, "99", name="Vitamin IV"),
                "country": "LT",
                "domain": "syncclinic.lt",
                "clinic": "SYNC Longevity Clinic",
                "provider": "direct",
            }
        ],
    )
    monkeypatch.setattr(market_map, "refresh", lambda *a: None)
    stats = market.collect("direct-run", cfg, "worker", "staff@example.test")
    assert stats["queries"] == 0
    assert fetched == list(item["urls"])
    assert market.observations()[0]["provider"] == "direct"


def test_curated_official_domain_replaces_private_ownership_gate():
    from web.market_search import grounded_rows

    result = {
        "url": "https://syncclinic.lt/laselines-iv-terapijos/",
        "text": "Vitaminų lašelinė 99 EUR",
        "retrieved_at": market.now(),
        "published_at": None,
        "provider": "direct",
        "curated_target": {
            "id": "sync",
            "name": "SYNC Longevity Clinic",
            "country": "LT",
            "domains": ("syncclinic.lt",),
        },
    }
    proposed = {
        "clinic": {
            "name": "Unknown",
            "country": "LT",
            "ownership": "unknown",
            "official_source": False,
            "evidence": "",
        },
        "services": [
            {
                "name": "Vitamin IV",
                "original_name": "Vitaminų lašelinė",
                "price": "99",
                "price_max": None,
                "price_type": "exact",
                "currency": "EUR",
                "evidence": "Vitaminų lašelinė 99 EUR",
            }
        ],
    }

    rows = grounded_rows(result, proposed)
    assert len(rows) == 1
    assert rows[0]["clinic"] == "SYNC Longevity Clinic"
    assert rows[0]["ownership_evidence"].startswith("Authenticated watchlist:")


def test_curated_provider_identity_never_crosses_domains():
    from web.market_search import grounded_rows

    result = {
        "url": "https://unrelated.example/prices",
        "text": "Vitamin IV 99 EUR",
        "retrieved_at": market.now(),
        "provider": "direct",
        "curated_target": {
            "name": "SYNC Longevity Clinic",
            "country": "LT",
            "domains": ("syncclinic.lt",),
        },
    }
    assert grounded_rows(result, {"clinic": {}, "services": []}) == []
