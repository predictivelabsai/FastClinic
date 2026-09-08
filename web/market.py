"""Durable market configuration, collection queue and append-only price history."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from web import ops_db
from web.market_search import COUNTRIES, QUERIES, domain, now, search, extract_services

log = logging.getLogger(__name__)
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
    "CREATE INDEX IF NOT EXISTS market_obs_time ON market_observation(retrieved_at)",
    "CREATE INDEX IF NOT EXISTS market_obs_match ON market_observation(hospital_id,service_id,price_type)",
]


def connect():
    c = ops_db.connect()
    for sql in SCHEMA:
        c.execute(sql)
    c.execute(
        "INSERT INTO market_config (id,payload) VALUES (1,?) ON CONFLICT(id) DO NOTHING",
        (json.dumps(DEFAULT_CONFIG),),
    )
    c.execute(
        "INSERT INTO market_lock (id,owner,expires_at) VALUES (1,'','') ON CONFLICT(id) DO NOTHING"
    )
    c.commit()
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


def enqueue(actor, trigger="manual", at=None):
    stamp = at or now()
    cfg = config()
    scheduled = week(stamp) if trigger == "weekly" else None
    with connect() as c:
        # Serialize enqueue requests independently of the long-running worker lease.
        if c.postgres:
            c.execute("SELECT id FROM market_lock WHERE id=1 FOR UPDATE")
        else:
            c.execute("BEGIN IMMEDIATE")
        active = c.execute(
            "SELECT id FROM market_run WHERE status IN ('queued','running') ORDER BY created_at LIMIT 1"
        ).fetchone()
        if active:
            return active["id"]
        if scheduled:
            existing = c.execute(
                "SELECT id FROM market_run WHERE scheduled_week=?", (scheduled,)
            ).fetchone()
            if existing:
                return existing["id"]
        recent = (datetime.fromisoformat(stamp) - timedelta(minutes=5)).isoformat(
            timespec="seconds"
        )
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
    with connect() as c:
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

    api_key = resolve(actor)
    cfg = {**cfg, "providers": ["exa"]}
    if not api_key:
        raise ValueError("Configure an Exa key under Integrations → search_provider")
    stats = dict(queries=0, pages=0, observations=0, errors=0, truncated_pages=0)
    candidates = {}
    jobs = [
        (p, c, QUERIES[c][i], None)
        for i in range(3)
        for c in cfg["countries"]
        for p in cfg["providers"]
    ]
    hospitals = rows("SELECT * FROM market_hospital ORDER BY first_seen")
    if cfg["hospitals"] != ["*"]:
        hospitals = [h for h in hospitals if h["id"] in cfg["hospitals"]]
        jobs = []
    # Refresh known providers first, rotating by week so budgets do not permanently starve the tail.
    if hospitals:
        rotation = datetime.now(timezone.utc).isocalendar().week % len(hospitals)
        hospitals = hospitals[rotation:] + hospitals[:rotation]
    targeted = [
        (
            p,
            h["country"],
            f"site:{h['domain']} treatment services prices kainynas cenrādis hinnakiri",
            [h["domain"]],
        )
        for h in hospitals
        if h["country"] in cfg["countries"]
        for p in cfg["providers"]
    ]
    # Reserve discovery slots even after the provider registry grows.
    jobs = (
        jobs[: min(len(jobs), cfg["max_queries"] // 2)]
        + targeted
        + jobs[min(len(jobs), cfg["max_queries"] // 2) :]
    )
    for p, country, q, domains in jobs[: max(1, cfg["max_queries"] // 2)]:
        _lease(owner)
        stats["queries"] += 1
        try:
            for r in search(
                p,
                q,
                domains=domains,
                api_key=api_key,
                excluded_domains=(
                    [h["domain"] for h in hospitals] if not domains else None
                ),
            ):
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
    # Country/provider round-robin prevents the first country consuming the page budget.
    buckets = {(c, p): [] for c in cfg["countries"] for p in cfg["providers"]}
    for r in candidates.values():
        buckets[(r["country"], r["provider"])].append(r)
    ordered = []
    while any(buckets.values()):
        for bucket in buckets.values():
            if bucket:
                ordered.append(bucket.pop(0))
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

            host = domain(r["url"])
            if host not in ownership_cache and stats["queries"] < cfg["max_queries"]:
                stats["queries"] += 1
                ownership_cache[host] = enrich_ownership(r, api_key).get(
                    "ownership_sources", []
                )
            r = {**r, "ownership_sources": ownership_cache.get(host, [])}
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
    for h in rows("SELECT * FROM market_hospital ORDER BY name"):
        if h["domain"] not in location_sources:
            continue
        _lease(owner)
        try:
            sources = list(
                {s["url"]: s for s in location_sources[h["domain"]]}.values()
            )
            market_map.refresh(h, api_key, sources)
        except Exception as exc:
            stats["errors"] += 1
            log.warning("Market address lookup failed: %s", type(exc).__name__)
    stats["locations"] = len(market_map.clinics())
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
        if config()["weekly"]:
            enqueue("scheduler", "weekly")
        queued = rows(
            "SELECT * FROM market_run WHERE status='queued' ORDER BY created_at LIMIT 1"
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
            run["actor"] if run["trigger_kind"] == "manual" else None,
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
    finally:
        heartbeat_stop.set()
        with connect() as c:
            c.execute(
                "UPDATE market_lock SET owner='',expires_at='' WHERE id=1 AND owner=?",
                (owner,),
            )
            c.commit()
