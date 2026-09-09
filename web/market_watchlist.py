"""Authenticated, manually curated competitor watchlist.

Entries are seeded from the product brief, then become ordinary database rows.  Manual
URLs are fetched directly by the deep scraper and never require a discovery search.
"""

from __future__ import annotations

import json

from web import market
from web.market_catalog import TARGETS
from web.market_search import COUNTRIES, domain, safe_url


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS market_watchlist (
       id TEXT PRIMARY KEY, name TEXT NOT NULL, country TEXT NOT NULL,
       segment TEXT NOT NULL, cities TEXT NOT NULL, positioning TEXT NOT NULL,
       capabilities TEXT NOT NULL, scope INTEGER NOT NULL, iv_focus INTEGER NOT NULL,
       urls TEXT NOT NULL, active INTEGER NOT NULL, priority INTEGER NOT NULL,
       origin TEXT NOT NULL, created_by TEXT, created_at TEXT NOT NULL,
       updated_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS market_watchlist_active ON market_watchlist(active,priority)",
]


def connect():
    c = market.connect()
    for sql in SCHEMA:
        c.execute(sql)
    stamp = market.now()
    for priority, target in enumerate(TARGETS, 1):
        urls = list(dict.fromkeys([target["service_url"], f"https://{target['domains'][0]}/"]))
        c.execute(
            """INSERT INTO market_watchlist
            (id,name,country,segment,cities,positioning,capabilities,scope,iv_focus,
             urls,active,priority,origin,created_by,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING""",
            (
                target["slug"],
                target["name"],
                "LT",
                target["segment"],
                json.dumps(target["cities"], ensure_ascii=False),
                target["positioning"],
                json.dumps(target["capabilities"]),
                target["scope"],
                target["iv_focus"],
                json.dumps(urls, ensure_ascii=False),
                1,
                priority,
                "seeded",
                "product-brief",
                stamp,
                stamp,
            ),
        )
    c.commit()
    return c


def _decode(row):
    value = dict(row)
    value["cities"] = tuple(json.loads(value["cities"]))
    value["capabilities"] = tuple(json.loads(value["capabilities"]))
    value["urls"] = tuple(json.loads(value["urls"]))
    value["domains"] = tuple(dict.fromkeys(domain(url) for url in value["urls"] if domain(url)))
    value["service_url"] = value["urls"][0] if value["urls"] else ""
    value["active"] = bool(value["active"])
    return value


def items(active_only=False):
    with connect() as c:
        rows = c.execute(
            "SELECT * FROM market_watchlist"
            + (" WHERE active=1" if active_only else "")
            + " ORDER BY priority,name"
        ).fetchall()
    return [_decode(r) for r in rows]


def get(ident):
    with connect() as c:
        row = c.execute("SELECT * FROM market_watchlist WHERE id=?", (ident,)).fetchone()
    return _decode(row) if row else None


def _urls(value):
    raw = value.splitlines() if isinstance(value, str) else value
    urls = list(dict.fromkeys(safe_url(str(url).strip()) for url in raw if str(url).strip()))
    if not urls or any(not url for url in urls) or len(urls) > 8:
        raise ValueError("Add between one and eight public HTTP(S) URLs")
    return urls


def save(
    ident,
    *,
    name,
    country,
    segment,
    cities,
    positioning,
    urls,
    priority,
    active,
    actor,
):
    name = str(name).strip()[:160]
    country = str(country).strip().upper()
    segment = str(segment).strip()
    city_list = list(dict.fromkeys(v.strip() for v in str(cities).split(",") if v.strip()))
    clean_urls = _urls(urls)
    if not name or country not in COUNTRIES or not city_list:
        raise ValueError("Name, supported country and at least one city are required")
    if segment not in ("IV / longevity specialist", "Multi-specialty clinic"):
        raise ValueError("Choose a supported competitor model")
    priority = max(1, min(999, int(priority)))
    current = get(ident) if ident else None
    ident = ident or market.identity(country, name, clean_urls[0])[:20]
    stamp = market.now()
    # Manually created entries start with conservative chart classifications.
    capabilities = current["capabilities"] if current else ("iv_therapy",)
    scope = current["scope"] if current else (2 if segment.startswith("IV") else 4)
    iv_focus = current["iv_focus"] if current else (5 if segment.startswith("IV") else 2)
    with connect() as c:
        c.execute(
            """INSERT INTO market_watchlist
            (id,name,country,segment,cities,positioning,capabilities,scope,iv_focus,
             urls,active,priority,origin,created_by,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country,
             segment=excluded.segment,cities=excluded.cities,positioning=excluded.positioning,
             urls=excluded.urls,active=excluded.active,priority=excluded.priority,
             updated_at=excluded.updated_at""",
            (
                ident,
                name,
                country,
                segment,
                json.dumps(city_list, ensure_ascii=False),
                str(positioning).strip()[:500],
                json.dumps(capabilities),
                scope,
                iv_focus,
                json.dumps(clean_urls, ensure_ascii=False),
                int(bool(active)),
                priority,
                current["origin"] if current else "manual",
                current["created_by"] if current else actor,
                current["created_at"] if current else stamp,
                stamp,
            ),
        )
        c.commit()
    return ident


def search_jobs(countries):
    """Exa discovery jobs for active entries; direct scraping is handled separately."""
    terms = "intraveninė terapija lašelinė infuzija vitaminai NAD glutationas kainos kainynas paslaugos kontaktai"
    return [
        (
            item["country"],
            f"site:{item['domains'][0]} {terms}",
            list(item["domains"]),
            item["id"],
        )
        for item in items(active_only=True)
        if item["country"] in countries and item["domains"]
    ]
