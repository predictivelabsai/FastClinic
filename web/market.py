"""Durable market configuration, collection queue and append-only price history."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from web import ops_db
from web.market_search import COUNTRIES, QUERIES, domain, now, search, extract_services

log = logging.getLogger(__name__)
_READY_SCHEMAS = set()
_SCHEMA_LOCK = threading.Lock()
DEFAULT_CONFIG = dict(
    countries=list(COUNTRIES),
    hospitals=["*"],
    treatments=["*"],
    providers=["exa"],
    weekly=True,
    max_queries=24,
    max_pages=30,
)
SCHEMA = [
    "CREATE TABLE IF NOT EXISTS market_config (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS market_run (id TEXT PRIMARY KEY, scheduled_week TEXT UNIQUE,
       status TEXT NOT NULL, trigger_kind TEXT NOT NULL, actor TEXT, created_at TEXT NOT NULL,
       finished_at TEXT, config TEXT NOT NULL, stats TEXT NOT NULL, error TEXT)""",
    """CREATE TABLE IF NOT EXISTS market_lock (id INTEGER PRIMARY KEY, owner TEXT, expires_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS market_hospital (id TEXT PRIMARY KEY, country TEXT NOT NULL,
       name TEXT NOT NULL, domain TEXT NOT NULL, evidence TEXT NOT NULL, source_url TEXT NOT NULL,
       first_seen TEXT NOT NULL, UNIQUE(country, domain))""",
    """CREATE TABLE IF NOT EXISTS market_service (id TEXT PRIMARY KEY, name TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS market_source (id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
       country TEXT NOT NULL, provider TEXT NOT NULL, url TEXT NOT NULL, retrieved_at TEXT NOT NULL,
       payload TEXT NOT NULL, status TEXT NOT NULL, error TEXT)""",
    """CREATE TABLE IF NOT EXISTS market_observation (id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
       hospital_id TEXT NOT NULL, service_id TEXT NOT NULL, original_name TEXT NOT NULL,
       price TEXT, price_max TEXT, price_type TEXT NOT NULL, currency TEXT NOT NULL,
       source_url TEXT NOT NULL, provider TEXT NOT NULL, retrieved_at TEXT NOT NULL,
       published_at TEXT, evidence TEXT NOT NULL, ownership_evidence TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS market_taxonomy_node (id TEXT PRIMARY KEY,parent_id TEXT,
       level TEXT NOT NULL,label TEXT NOT NULL,source TEXT NOT NULL,version TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS market_service_taxonomy (service_id TEXT PRIMARY KEY,
       taxonomy_id TEXT NOT NULL,method TEXT NOT NULL,confidence TEXT NOT NULL,version TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS market_obs_time ON market_observation(retrieved_at)",
    "CREATE INDEX IF NOT EXISTS market_obs_match ON market_observation(hospital_id,service_id,price_type)",
]


def _storage_key(connection):
    if connection.postgres:
        value = os.getenv("DATABASE_URL_PROD") or os.getenv("DATABASE_URL") or ""
        return ("postgresql", hashlib.sha256(value.encode()).hexdigest(), os.getenv("FASTCLINIC_DB_SCHEMA", "fast_clinic"))
    from pathlib import Path

    path = Path(os.getenv("FASTCLINIC_OPS_DB") or ops_db.DEFAULT_PATH).resolve()
    return ("sqlite", str(path), str(path.stat().st_ino))


def ensure_schema(connection, name, statements, initialize=None):
    """Initialize one operational schema once per process/database instance."""
    key = (_storage_key(connection), name)
    if key in _READY_SCHEMAS:
        return
    with _SCHEMA_LOCK:
        if key in _READY_SCHEMAS:
            return
        for sql in statements:
            connection.execute(sql)
        if initialize:
            initialize(connection)
        connection.commit()
        _READY_SCHEMAS.add(key)


def connect():
    c = ops_db.connect()

    def initialize(connection):
        connection.execute(
            "INSERT INTO market_config (id,payload) VALUES (1,?) ON CONFLICT(id) DO NOTHING",
            (json.dumps(DEFAULT_CONFIG),),
        )
        connection.execute(
            "INSERT INTO market_lock (id,owner,expires_at) VALUES (1,'','') ON CONFLICT(id) DO NOTHING"
        )

    ensure_schema(c, "market", SCHEMA, initialize)
    return c


def rows(sql, params=()):
    with connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def config():
    return json.loads(
        rows("SELECT payload FROM market_config WHERE id=1")[0]["payload"]
    )


def save_config(value):
    value = {**DEFAULT_CONFIG, **value}
    if not value["countries"] or set(value["countries"]) - set(COUNTRIES):
        raise ValueError("Select at least one supported country")
    if not value["providers"] or set(value["providers"]) - {"exa"}:
        raise ValueError("Select at least one search provider")
    for key, table in [
        ("hospitals", "market_hospital"),
        ("treatments", "market_service"),
    ]:
        selected = value[key]
        if not selected or ("*" in selected and selected != ["*"]):
            raise ValueError("Choose all or select individual entries")
        known = {r["id"] for r in rows(f"SELECT id FROM {table}")}
        if selected != ["*"] and set(selected) - known:
            raise ValueError("Unknown configuration selection")
    value["max_queries"] = max(1, min(200, int(value["max_queries"])))
    value["max_pages"] = max(1, min(300, int(value["max_pages"])))
    value["weekly"] = bool(value["weekly"])
    with connect() as c:
        c.execute("UPDATE market_config SET payload=? WHERE id=1", (json.dumps(value),))
        c.commit()
    return value


def week(stamp):
    dt = datetime.fromisoformat(stamp)
    return (dt.date() - timedelta(days=dt.weekday())).isoformat()


def enqueue(actor, trigger="manual", at=None, config_override=None):
    stamp = at or now()
    cfg = {**config(), **(config_override or {})}
    scheduled = week(stamp) if trigger == "weekly" else None
    with connect() as c:
        # Serialize enqueue requests independently of the long-running worker lease.
        if c.postgres:
            c.execute("SELECT id FROM market_lock WHERE id=1 FOR UPDATE")
        else:
            c.execute("BEGIN IMMEDIATE")
        active = c.execute(
            """SELECT id,trigger_kind,config FROM market_run
               WHERE status IN ('queued','running') ORDER BY created_at"""
        ).fetchall()
        if trigger == "watchlist":
            requested = set(cfg.get("watchlist_ids") or [])
            for row in active:
                if row["trigger_kind"] != "watchlist":
                    continue
                existing = set(json.loads(row["config"]).get("watchlist_ids") or [])
                if requested and requested <= existing:
                    return row["id"]
        elif active:
            return active[0]["id"]
        if scheduled:
            existing = c.execute(
                "SELECT id FROM market_run WHERE scheduled_week=?", (scheduled,)
            ).fetchone()
            if existing:
                return existing["id"]
        recent = (datetime.fromisoformat(stamp) - timedelta(minutes=5)).isoformat(
            timespec="seconds"
        )
        if trigger == "manual":
            last = c.execute(
                "SELECT id FROM market_run WHERE created_at>? ORDER BY created_at DESC LIMIT 1",
                (recent,),
            ).fetchone()
            if last:
                return last["id"]
        ident = uuid.uuid4().hex
        c.execute(
            "INSERT INTO market_run (id,scheduled_week,status,trigger_kind,actor,created_at,config,stats) VALUES (?,?,?,?,?,?,?,?)",
            (ident, scheduled, "queued", trigger, actor, stamp, json.dumps(cfg), "{}"),
        )
        c.commit()
    return ident


def identity(*parts):
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()[:32]


def ingest(run_id, observations):
    """Repeatable import; never overwrite a previous observation or its evidence."""
    from web import market_taxonomy

    with connect() as c:
        market_taxonomy.ensure(c)
        for r in observations:
            hid = identity(r["country"], r["domain"])
            sid = identity(r["service"].strip().casefold())
            c.execute(
                """INSERT INTO market_hospital (id,country,name,domain,evidence,source_url,first_seen)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING""",
                (
                    hid,
                    r["country"],
                    r["clinic"],
                    r["domain"],
                    r["ownership_evidence"],
                    r.get("ownership_url") or r["source_url"],
                    r["retrieved_at"],
                ),
            )
            c.execute(
                "INSERT INTO market_service (id,name) VALUES (?,?) ON CONFLICT(id) DO NOTHING",
                (sid, r["service"]),
            )
            market_taxonomy.map_service(
                c, sid, r["service"] + " " + r.get("original_name", "")
            )
            oid = identity(
                run_id,
                hid,
                sid,
                r["original_name"],
                r["price_type"],
                r["price"],
                r["price_max"],
                r["source_url"],
                r["provider"],
            )
            c.execute(
                """INSERT INTO market_observation
                (id,run_id,hospital_id,service_id,original_name,price,price_max,price_type,currency,
                 source_url,provider,retrieved_at,published_at,evidence,ownership_evidence)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING""",
                (
                    oid,
                    run_id,
                    hid,
                    sid,
                    r["original_name"],
                    r["price"],
                    r["price_max"],
                    r["price_type"],
                    r["currency"],
                    r["source_url"],
                    r["provider"],
                    r["retrieved_at"],
                    r.get("published_at"),
                    r["evidence"],
                    r["ownership_evidence"],
                ),
            )
        c.commit()


def observations():
    return rows(
        """SELECT o.*,h.name AS hospital,h.country,h.domain,h.source_url AS ownership_url,s.name AS service
        FROM market_observation o JOIN market_hospital h ON h.id=o.hospital_id
        JOIN market_service s ON s.id=o.service_id ORDER BY o.retrieved_at DESC,o.id"""
    )


def comparison_key(r):
    # Original labels and URL keep different doctor/site/unit tariffs separate.
    return (
        r["hospital_id"],
        r["service_id"],
        r["original_name"],
        r["price_type"],
        r["currency"],
        r["source_url"],
    )


def latest_prices(history=None):
    history = observations() if history is None else history
    weekly = {}
    for r in sorted(history, key=lambda v: (v["retrieved_at"], v["id"]), reverse=True):
        weekly.setdefault((comparison_key(r), week(r["retrieved_at"])), r)
    latest = {}
    for r in sorted(history, key=lambda v: (v["retrieved_at"], v["id"]), reverse=True):
        key = comparison_key(r)
        if key in latest:
            continue
        entry = dict(r, change=None, change_pct=None, change_max=None)
        previous_week = (
            (datetime.fromisoformat(week(r["retrieved_at"])) - timedelta(days=7))
            .date()
            .isoformat()
        )
        previous = weekly.get((key, previous_week))
        if previous and r["price"] is not None and previous["price"] is not None:
            old, new = Decimal(previous["price"]), Decimal(r["price"])
            entry["change"] = float(new - old)
            entry["change_pct"] = float((new - old) / old * 100) if old else None
            if r["price_type"] == "range" and previous["price_max"] and r["price_max"]:
                entry["change_max"] = float(
                    Decimal(r["price_max"]) - Decimal(previous["price_max"])
                )
        entry["stale"] = week(r["retrieved_at"]) != week(now())
        latest[key] = entry
    return list(latest.values())


def _lease(owner):
    with connect() as c:
        c.execute(
            "UPDATE market_lock SET expires_at=? WHERE id=1 AND owner=?",
            (
                (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(
                    timespec="seconds"
                ),
                owner,
            ),
        )
        c.commit()


def collect(run_id, cfg, owner, actor=None):
    from web.search_provider import resolve
    from web import market_candidates, market_watchlist
    from web.market_search import scrape_url

    cfg = {**cfg, "providers": ["exa"]}
    direct_only = cfg.get("mode") == "direct"
    api_key = None if direct_only else resolve(actor)
    if not api_key and not direct_only:
        raise ValueError("Configure an Exa key under Integrations → search_provider")
    stats = dict(
        queries=0,
        pages=0,
        observations=0,
        errors=0,
        truncated_pages=0,
        direct_fetches=0,
        discovery_content_fallbacks=0,
        candidates_seen=0,
        candidates_new=0,
    )
    candidates = {}
    hospitals = rows("SELECT * FROM market_hospital ORDER BY first_seen")
    if cfg["hospitals"] != ["*"]:
        hospitals = [h for h in hospitals if h["id"] in cfg["hospitals"]]
    search_budget = 0 if direct_only else max(1, cfg["max_queries"] // 2)
    providers = cfg["providers"]
    discovery = [
        (provider, country, query, None)
        for query_index in range(max(len(v) for v in QUERIES.values()))
        for country in cfg["countries"]
        for provider in providers
        for query in QUERIES[country][query_index : query_index + 1]
    ]
    if cfg["hospitals"] == ["*"]:
        targets = [
            (provider, country, query, domains)
            for country, query, domains, _slug in market_watchlist.search_jobs(cfg["countries"])
            if country in cfg["countries"]
            for provider in providers
        ]
        # Rotate the named list weekly, while always leaving room for open discovery.
        if targets:
            rotation = datetime.now(timezone.utc).isocalendar().week % len(targets)
            targets = targets[rotation:] + targets[:rotation]
        target_slots = (
            0
            if cfg.get("campaign_country")
            else min(len(targets), max(1, (search_budget * 2) // 3))
            if search_budget
            else 0
        )
        jobs = targets[:target_slots] + discovery[: search_budget - target_slots]
    else:
        jobs = [
            (
                provider,
                h["country"],
                f"site:{h['domain']} treatment services prices kainynas cenrādis hinnakiri lašelinė infuzija IV wellness",
                [h["domain"]],
            )
            for h in hospitals
            if h["country"] in cfg["countries"]
            for provider in providers
        ][:search_budget]
    excluded = sorted(
        {h["domain"] for h in hospitals}
        | {
            host
            for country, _query, domains, _slug in market_watchlist.search_jobs(cfg["countries"])
            if country in cfg["countries"]
            for host in domains
        }
    )
    for p, country, q, domains in jobs:
        _lease(owner)
        stats["queries"] += 1
        try:
            results = search(
                p,
                q,
                domains=domains,
                api_key=api_key,
                excluded_domains=(
                    excluded if not domains else None
                ),
            )
            captured = market_candidates.capture(results, country, run_id)
            stats["candidates_seen"] += captured["seen"]
            stats["candidates_new"] += captured["new"]
            for r in results:
                if cfg["hospitals"] != ["*"] and domain(r["url"]) not in {
                    h["domain"] for h in hospitals
                }:
                    continue
                key = (p, r["url"])
                if key not in candidates or len(r["text"]) > len(
                    candidates[key]["text"]
                ):
                    candidates[key] = {**r, "country": country}
        except Exception as exc:
            stats["errors"] += 1
            log.warning("Market search failed: %s", type(exc).__name__)
    # Identified URLs do not need Exa discovery. They join the same extraction,
    # evidence, price-history and map pipeline as search-discovered pages.
    selected_watchlist = set(cfg.get("watchlist_ids") or [])
    watched = [
        item
        for item in market_watchlist.items(active_only=True)
        if item["country"] in cfg["countries"]
        and (not selected_watchlist or item["id"] in selected_watchlist)
    ]
    watched_by_domain = {
        host: {
            "id": item["id"],
            "name": item["name"],
            "country": item["country"],
            "domains": item["domains"],
        }
        for item in watched
        for host in item["domains"]
    }
    manual_candidates = []
    for item in watched:
        fetched = []
        for url in item["urls"]:
            if len(manual_candidates) + len(fetched) >= cfg["max_pages"]:
                break
            try:
                fetched.append(
                    {
                        **scrape_url(url),
                        "country": item["country"],
                        "watchlist_id": item["id"],
                        "curated_target": watched_by_domain.get(domain(url)),
                        "fetch_method": "direct",
                    }
                )
                stats["direct_fetches"] += 1
            except Exception as exc:
                stats["errors"] += 1
                log.warning("Watchlist URL scrape failed for %s: %s", item["id"], type(exc).__name__)
        source_context = [dict(source) for source in fetched]
        for result in fetched:
            result["ownership_sources"] = [
                source
                for source in source_context
                if domain(source["url"]) == domain(result["url"])
            ]
            manual_candidates.append(result)
    # Country/provider round-robin prevents the first country consuming the page budget.
    buckets = {(c, p): [] for c in cfg["countries"] for p in cfg["providers"]}
    for r in candidates.values():
        buckets[(r["country"], r["provider"])].append(r)
    ordered = []
    while any(buckets.values()):
        for bucket in buckets.values():
            if bucket:
                ordered.append(bucket.pop(0))
    searched_ordered = ordered
    seen_urls = {r["url"] for r in manual_candidates}
    ordered = manual_candidates + [r for r in searched_ordered if r["url"] not in seen_urls]
    stats["candidate_pages"] = len(ordered)
    stats["deferred_pages"] = max(0, len(ordered) - cfg["max_pages"])
    allowed_services = set(cfg["treatments"])
    ownership_cache = {}
    location_sources = {}
    for r in ordered[: cfg["max_pages"]]:
        _lease(owner)
        stats["pages"] += 1
        status, error = "processed", None
        try:
            from web.market_search import enrich_ownership

            if r["provider"] != "direct":
                # Exa discovers the URL; the same direct deep scraper used by the
                # manual watchlist obtains the page when the site permits it.
                try:
                    fetched = scrape_url(r["url"])
                    r = {
                        **r,
                        "text": fetched["text"],
                        "retrieved_at": fetched["retrieved_at"],
                        "fetch_method": "direct",
                    }
                    stats["direct_fetches"] += 1
                except Exception:
                    # Exa's retained live-crawl text is a useful, auditable fallback.
                    r = {**r, "fetch_method": "exa_content_fallback"}
                    stats["discovery_content_fallbacks"] += 1
            host = domain(r["url"])
            if host in watched_by_domain:
                r = {**r, "curated_target": watched_by_domain[host]}
            if (
                not r.get("ownership_sources")
                and not r.get("curated_target")
                and host not in ownership_cache
                and stats["queries"] < cfg["max_queries"]
            ):
                stats["queries"] += 1
                ownership_cache[host] = enrich_ownership(r, api_key).get(
                    "ownership_sources", []
                )
            r = {
                **r,
                "ownership_sources": r.get("ownership_sources")
                or ownership_cache.get(host, []),
            }
            extracted = extract_services(r)
            extracted = [o for o in extracted if o["country"] == r["country"]]
            if "*" not in allowed_services:
                extracted = [
                    o
                    for o in extracted
                    if identity(o["service"].strip().casefold()) in allowed_services
                ]
            ingest(run_id, extracted)
            if extracted:
                location_sources.setdefault(host, []).extend(
                    [r] + r.get("ownership_sources", [])
                )
            stats["observations"] += len(extracted)
            stats["truncated_pages"] += int(len(r["text"]) > 120000)
            if not extracted:
                status = "no_grounded_services"
        except Exception as exc:
            stats["errors"] += 1
            status, error = "failed", type(exc).__name__
        with connect() as c:
            c.execute(
                """INSERT INTO market_source (id,run_id,country,provider,url,retrieved_at,payload,status,error)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING""",
                (
                    identity(run_id, r["provider"], r["url"]),
                    run_id,
                    r["country"],
                    r["provider"],
                    r["url"],
                    r["retrieved_at"],
                    json.dumps(r, ensure_ascii=False),
                    status,
                    error,
                ),
            )
            c.execute(
                "UPDATE market_run SET stats=? WHERE id=?", (json.dumps(stats), run_id)
            )
            c.commit()
    from web import market_map

    stats["locations"] = 0
    refreshed_ids = []
    for h in rows("SELECT * FROM market_hospital ORDER BY name"):
        if h["domain"] not in location_sources:
            continue
        _lease(owner)
        try:
            sources = list(
                {s["url"]: s for s in location_sources[h["domain"]]}.values()
            )
            market_map.refresh(h, api_key, sources, True)
            refreshed_ids.append(h["id"])
        except Exception as exc:
            stats["errors"] += 1
            log.warning("Market address lookup failed: %s", type(exc).__name__)
    _lease(owner)
    stats["address_repair"] = market_map.repair_pending(
        api_key,
        limit=max(0, min(20, int(cfg.get("max_address_clinics", 6)))),
        exclude_ids=refreshed_ids,
    )
    stats["geocoding"] = market_map.geocode_pending(limit=100)
    stats["locations"] = len(market_map.clinics())
    stats["candidates_verified"] = market_candidates.sync_verified()
    return stats


def tick():
    """One durable worker claim, safe with multiple application processes."""
    owner = uuid.uuid4().hex
    stamp = now()
    with connect() as c:
        claimed = c.execute(
            "UPDATE market_lock SET owner=?,expires_at=? WHERE id=1 AND expires_at<?",
            (
                owner,
                (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(
                    timespec="seconds"
                ),
                stamp,
            ),
        ).raw.rowcount
        c.commit()
        if not claimed:
            return
    import threading

    heartbeat_stop = threading.Event()

    def heartbeat():
        while not heartbeat_stop.wait(60):
            try:
                _lease(owner)
            except Exception:
                log.exception("Market lease renewal failed")

    threading.Thread(target=heartbeat, name="market-lease", daemon=True).start()
    run_id = None
    try:
        # A lease expired after a crash; preserve observations and show interrupted status.
        with connect() as c:
            c.execute(
                "UPDATE market_run SET status='interrupted',finished_at=?,error='Worker interrupted; manual retry available' WHERE status='running'",
                (stamp,),
            )
            c.commit()
        from web import market_map

        market_map.geocode_pending(limit=100)
        if config()["weekly"]:
            enqueue("scheduler", "weekly")
        queued = rows(
            "SELECT * FROM market_run WHERE status='queued' ORDER BY created_at LIMIT 1"
        )
        if not queued:
            from web import market_candidates

            campaign = market_candidates.next_campaign()
            if campaign:
                campaign_run = enqueue(
                    campaign["requested_by"],
                    "campaign",
                    config_override=market_candidates.campaign_config(campaign["country"]),
                )
                market_candidates.mark_campaign_started(
                    campaign["country"], campaign_run
                )
                queued = rows(
                    "SELECT * FROM market_run WHERE id=? AND status='queued'",
                    (campaign_run,),
                )
        if not queued:
            return
        run = queued[0]
        run_id = run["id"]
        with connect() as c:
            c.execute("UPDATE market_run SET status='running' WHERE id=?", (run_id,))
            c.commit()
        stats = collect(
            run_id,
            json.loads(run["config"]),
            owner,
            run["actor"] if run["trigger_kind"] in ("manual", "watchlist") else None,
        )
        with connect() as c:
            status = (
                "partial"
                if stats["errors"]
                or stats["deferred_pages"]
                or stats["truncated_pages"]
                else "completed"
            )
            if not stats["pages"] and stats["errors"]:
                status = "failed"
            c.execute(
                "UPDATE market_run SET status=?,stats=?,finished_at=? WHERE id=?",
                (status, json.dumps(stats), now(), run_id),
            )
            c.commit()
        campaign_country = json.loads(run["config"]).get("campaign_country")
        if campaign_country:
            from web import market_candidates

            market_candidates.finish_campaign(
                campaign_country, run_id, status
            )
    except Exception as exc:
        log.exception("Market worker failed")
        if run_id:
            with connect() as c:
                c.execute(
                    "UPDATE market_run SET status='failed',error=?,finished_at=? WHERE id=?",
                    (
                        (
                            str(exc)[:200]
                            if isinstance(exc, (ValueError, RuntimeError))
                            else type(exc).__name__
                        ),
                        now(),
                        run_id,
                    ),
                )
                c.commit()
            try:
                cfg = json.loads(run["config"]) if run_id and run else {}
                if cfg.get("campaign_country"):
                    from web import market_candidates

                    market_candidates.finish_campaign(
                        cfg["campaign_country"], run_id, "failed", str(exc)
                    )
            except Exception:
                log.exception("Market campaign status update failed")
    finally:
        heartbeat_stop.set()
        with connect() as c:
            c.execute(
                "UPDATE market_lock SET owner='',expires_at='' WHERE id=1 AND owner=?",
                (owner,),
            )
            c.commit()
