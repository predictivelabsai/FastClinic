"""Persistent discovery candidates, review workflow and EEA campaign queue."""

from __future__ import annotations

import json
import re
from urllib.parse import unquote, urljoin, urlsplit

from web import market
from web.market_countries import CAMPAIGN_ORDER, COUNTRIES, COUNTRY_BY_SLUG
from web.market_search import domain, safe_url, scrape_url


STATES = ("discovered", "watchlisted", "verified", "rejected")
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS market_candidate (
       id TEXT PRIMARY KEY, country TEXT NOT NULL, candidate_key TEXT NOT NULL,
       name TEXT NOT NULL, official_domain TEXT NOT NULL, source_url TEXT NOT NULL,
       source_type TEXT NOT NULL, state TEXT NOT NULL, discovered_at TEXT NOT NULL,
       last_seen_at TEXT NOT NULL, reviewed_by TEXT, reviewed_at TEXT,
       rejection_reason TEXT, watchlist_id TEXT, UNIQUE(country,candidate_key))""",
    """CREATE TABLE IF NOT EXISTS market_candidate_source (
       id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, source_url TEXT NOT NULL,
       source_type TEXT NOT NULL, discovery_query TEXT NOT NULL, title TEXT NOT NULL,
       evidence TEXT NOT NULL, retrieved_at TEXT NOT NULL,
       UNIQUE(candidate_id,source_url,source_type))""",
    """CREATE TABLE IF NOT EXISTS market_country_campaign (
       country TEXT PRIMARY KEY, priority INTEGER NOT NULL, target INTEGER NOT NULL, status TEXT NOT NULL,
       requested_by TEXT NOT NULL, queued_at TEXT NOT NULL, started_at TEXT,
       finished_at TEXT, last_run_id TEXT, error TEXT)""",
    "CREATE INDEX IF NOT EXISTS market_candidate_state ON market_candidate(country,state,last_seen_at)",
    "CREATE INDEX IF NOT EXISTS market_candidate_source_parent ON market_candidate_source(candidate_id)",
    "CREATE INDEX IF NOT EXISTS market_campaign_status ON market_country_campaign(status,queued_at)",
]


def connect():
    c = market.connect()
    market.ensure_schema(c, "market-candidates", SCHEMA)
    return c


def _name(title: str, host: str, source_url: str) -> str:
    value = re.sub(r"\s+", " ", str(title or "")).strip()
    if value:
        for separator in (" | ", " — ", " – "):
            if separator in value:
                value = value.split(separator, 1)[0].strip()
        if value:
            return value[:180]
    if host:
        return host.split(".", 1)[0].replace("-", " ").title()[:180]
    slug = unquote(urlsplit(source_url).path.rstrip("/").rsplit("/", 1)[-1])
    value = slug.replace("-", " ").title()
    return re.sub(r"\bHm\b", "HM", value)[:180] or "Unnamed provider candidate"


def capture(results, country: str, run_id: str = "", source_type: str = "exa") -> dict:
    """Persist search/aggregator leads before strict service extraction runs."""
    if country not in COUNTRIES:
        raise ValueError("Unsupported EEA country")
    prepared = []
    for result in results:
        source_url = safe_url(result.get("url", ""))
        if not source_url:
            continue
        host = "" if source_type == "mymedicalgateway" else domain(source_url)
        key = host or "source:" + urlsplit(source_url).path.casefold().rstrip("/")
        prepared.append((result, source_url, host, key))
    if not prepared:
        return {"seen": 0, "new": 0}
    stamp = market.now()
    added = 0
    with connect() as c:
        for result, source_url, host, key in prepared:
            ident = market.identity("candidate", country, key)
            existed = c.execute(
                "SELECT id FROM market_candidate WHERE country=? AND candidate_key=?",
                (country, key),
            ).fetchone()
            candidate_name = _name(result.get("title", ""), host, source_url)
            c.execute(
                """INSERT INTO market_candidate
                (id,country,candidate_key,name,official_domain,source_url,source_type,state,
                 discovered_at,last_seen_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(country,candidate_key) DO UPDATE SET
                 last_seen_at=excluded.last_seen_at,
                 source_url=CASE WHEN market_candidate.source_type='mymedicalgateway'
                   AND excluded.source_type!='mymedicalgateway' THEN excluded.source_url
                   ELSE market_candidate.source_url END,
                 official_domain=CASE WHEN excluded.official_domain!=''
                   THEN excluded.official_domain ELSE market_candidate.official_domain END""",
                (
                    ident,
                    country,
                    key,
                    candidate_name,
                    host,
                    source_url,
                    source_type,
                    "discovered",
                    stamp,
                    stamp,
                ),
            )
            source_id = market.identity("candidate-source", ident, source_type, source_url)
            text = re.sub(r"\s+", " ", str(result.get("text", ""))).strip()
            c.execute(
                """INSERT INTO market_candidate_source
                (id,candidate_id,source_url,source_type,discovery_query,title,evidence,retrieved_at)
                VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                 discovery_query=excluded.discovery_query,title=excluded.title,
                 evidence=excluded.evidence,retrieved_at=excluded.retrieved_at""",
                (
                    source_id,
                    ident,
                    source_url,
                    source_type,
                    str(result.get("query") or run_id or "")[:1000],
                    str(result.get("title") or "")[:500],
                    text[:1000],
                    result.get("retrieved_at") or stamp,
                ),
            )
            added += int(not existed)
        c.commit()
    return {"seen": len(prepared), "new": added}


def items(country: str = "", state: str = "", query: str = "", limit: int = 500):
    clauses, params = [], []
    if country:
        if country not in COUNTRIES:
            raise ValueError("Unsupported EEA country")
        clauses.append("c.country=?")
        params.append(country)
    if state:
        if state not in STATES:
            raise ValueError("Unsupported candidate state")
        clauses.append("c.state=?")
        params.append(state)
    if query:
        clauses.append("(LOWER(c.name) LIKE ? OR LOWER(c.official_domain) LIKE ?)")
        term = "%" + query.casefold() + "%"
        params.extend((term, term))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as c:
        rows = c.execute(
            """SELECT c.*,(SELECT COUNT(*) FROM market_candidate_source s
               WHERE s.candidate_id=c.id) AS source_count
               FROM market_candidate c"""
            + where
            + " ORDER BY c.last_seen_at DESC,c.name LIMIT ?",
            tuple(params + [max(1, min(2000, int(limit)))]),
        ).fetchall()
    return [dict(row) for row in rows]


def get(ident: str):
    with connect() as c:
        row = c.execute(
            """SELECT c.*,(SELECT COUNT(*) FROM market_candidate_source s
               WHERE s.candidate_id=c.id) AS source_count
               FROM market_candidate c WHERE c.id=?""",
            (ident,),
        ).fetchone()
    return dict(row) if row else None


def sources(ident: str):
    with connect() as c:
        return [
            dict(row)
            for row in c.execute(
                "SELECT * FROM market_candidate_source WHERE candidate_id=? ORDER BY retrieved_at DESC",
                (ident,),
            ).fetchall()
        ]


def promote(
    ident: str,
    *,
    actor: str,
    official_url: str,
    name: str,
    cities: str,
    segment: str,
):
    """Move a reviewed candidate to the watchlist without claiming verification."""
    from web import market_watchlist

    candidate = get(ident)
    url = safe_url(official_url)
    host = domain(url)
    if not candidate or candidate["state"] == "rejected":
        raise ValueError("Candidate is not available for review")
    if not url or not host or host == "mymedicalgateway.com":
        raise ValueError("Enter the provider's official public website URL")
    watchlist_id = market_watchlist.save(
        "",
        name=name or candidate["name"],
        country=candidate["country"],
        segment=segment,
        cities=cities,
        positioning=f"Reviewed discovery candidate from {candidate['source_type']}",
        urls=[url],
        priority=len(market_watchlist.items()) + 1,
        active=True,
        actor=actor,
    )
    stamp = market.now()
    with connect() as c:
        c.execute(
            """UPDATE market_candidate SET state='watchlisted',official_domain=?,
               watchlist_id=?,reviewed_by=?,reviewed_at=?,rejection_reason=NULL WHERE id=?""",
            (host, watchlist_id, actor, stamp, ident),
        )
        c.execute(
            "UPDATE market_watchlist SET origin='candidate' WHERE id=?", (watchlist_id,)
        )
        c.commit()
    return watchlist_id


def set_state(ident: str, state: str, actor: str, reason: str = "") -> None:
    if state not in ("discovered", "rejected"):
        raise ValueError("Unsupported review action")
    if not get(ident):
        raise ValueError("Candidate not found")
    stamp = market.now()
    with connect() as c:
        c.execute(
            """UPDATE market_candidate SET state=?,reviewed_by=?,reviewed_at=?,
               rejection_reason=? WHERE id=?""",
            (state, actor, stamp, reason[:500] if state == "rejected" else None, ident),
        )
        c.commit()


def sync_verified() -> int:
    """Mark candidates verified only after a grounded provider and branch exist."""
    from web import market_map

    facilities = market_map.clinics()
    hospital_rows = market.rows("SELECT id,domain FROM market_hospital")
    facility_hospitals = {branch["hospital_id"] for branch in facilities}
    verified_domains = {
        row["domain"] for row in hospital_rows if row["id"] in facility_hospitals
    }
    changed = 0
    with connect() as c:
        rows = c.execute(
            "SELECT id,official_domain,state FROM market_candidate WHERE state!='rejected'"
        ).fetchall()
        for row in rows:
            if row["official_domain"] in verified_domains and row["state"] != "verified":
                c.execute(
                    "UPDATE market_candidate SET state='verified' WHERE id=?", (row["id"],)
                )
                changed += 1
        c.commit()
    return changed


def coverage(target: int = 10):
    from web import market_map, market_watchlist

    watched = market_watchlist.items()
    facilities = market_map.clinics()
    hospitals = market.rows("SELECT id,country FROM market_hospital")
    facility_hospitals = {branch["hospital_id"] for branch in facilities}
    with connect() as c:
        candidate_counts = {
            (row["country"], row["state"]): int(row["total"])
            for row in c.execute(
                """SELECT country,state,COUNT(*) AS total FROM market_candidate
                   GROUP BY country,state"""
            ).fetchall()
        }
        campaigns = {
            row["country"]: dict(row)
            for row in c.execute("SELECT * FROM market_country_campaign").fetchall()
        }
    watched_counts = {}
    for row in watched:
        watched_counts[row["country"]] = watched_counts.get(row["country"], 0) + 1
    verified_counts = {}
    for row in hospitals:
        if row["id"] in facility_hospitals:
            verified_counts[row["country"]] = verified_counts.get(row["country"], 0) + 1
    result = []
    for code, name in COUNTRIES.items():
        candidate_count = sum(
            candidate_counts.get((code, state), 0) for state in STATES
        )
        verified_count = verified_counts.get(code, 0)
        campaign = campaigns.get(code, {})
        country_target = int(campaign.get("target", target))
        result.append(
            {
                "country": code,
                "name": name,
                "candidates": candidate_count,
                "review": candidate_counts.get((code, "discovered"), 0),
                "watchlisted": watched_counts.get(code, 0),
                "verified": verified_count,
                "target": country_target,
                "remaining": max(0, country_target - verified_count),
                "campaign_status": campaign.get("status", "not queued"),
            }
        )
    return result


def queue_campaign(countries, actor: str, target: int = 10) -> int:
    codes = list(dict.fromkeys(str(code).upper() for code in countries))
    if not codes or set(codes) - set(COUNTRIES):
        raise ValueError("Select one or more EEA countries")
    stamp = market.now()
    queued = 0
    readiness = {row["country"]: row for row in coverage(target)}
    with connect() as c:
        for code in codes:
            status = "complete" if readiness[code]["verified"] >= target else "queued"
            c.execute(
                """INSERT INTO market_country_campaign
                (country,priority,target,status,requested_by,queued_at,started_at,finished_at,last_run_id,error)
                VALUES (?,?,?,?,?,?,NULL,NULL,NULL,NULL)
                ON CONFLICT(country) DO UPDATE SET priority=excluded.priority,
                 target=excluded.target,status=excluded.status,
                 requested_by=excluded.requested_by,queued_at=excluded.queued_at,
                 started_at=NULL,finished_at=NULL,last_run_id=NULL,error=NULL""",
                (code, CAMPAIGN_ORDER.index(code), target, status, actor, stamp),
            )
            queued += int(status == "queued")
        c.commit()
    return queued


def next_campaign():
    with connect() as c:
        row = c.execute(
            """SELECT * FROM market_country_campaign WHERE status='queued'
               ORDER BY priority,queued_at,country LIMIT 1"""
        ).fetchone()
    return dict(row) if row else None


def campaign_config(country: str) -> dict:
    return {
        "countries": [country],
        "hospitals": ["*"],
        "treatments": ["*"],
        "providers": ["exa"],
        "weekly": False,
        "max_queries": 30,
        "max_pages": 24,
        "max_address_clinics": 0,
        "campaign_country": country,
    }


def mark_campaign_started(country: str, run_id: str) -> None:
    with connect() as c:
        c.execute(
            """UPDATE market_country_campaign SET status='running',started_at=?,
               last_run_id=?,error=NULL WHERE country=?""",
            (market.now(), run_id, country),
        )
        c.commit()


def finish_campaign(country: str, run_id: str, run_status: str, error: str = "") -> None:
    sync_verified()
    readiness = next(row for row in coverage() if row["country"] == country)
    status = (
        "complete"
        if readiness["verified"] >= readiness["target"]
        else "review required"
    )
    if run_status == "failed":
        status = "failed"
    with connect() as c:
        c.execute(
            """UPDATE market_country_campaign SET status=?,finished_at=?,last_run_id=?,error=?
               WHERE country=?""",
            (status, market.now(), run_id, error[:500] or None, country),
        )
        c.commit()


MMG_INDEX = "https://www.mymedicalgateway.com/hospitals"


def import_mmg(index_url: str = MMG_INDEX) -> dict:
    """Import public MMG hospital profiles as unverified discovery seeds."""
    page = scrape_url(index_url)
    paths = re.findall(r"\]\(([^)\s]*?/hospitals/[^)\s]+)\)", page["text"])
    results_by_country = {}
    for raw in dict.fromkeys(paths):
        url = safe_url(urljoin(index_url, raw))
        parts = urlsplit(url).path.strip("/").split("/")
        if len(parts) < 3 or parts[0] != "hospitals":
            continue
        code = COUNTRY_BY_SLUG.get(unquote(parts[1]).casefold())
        if not code:
            continue
        results_by_country.setdefault(code, []).append(
            {
                "url": url,
                "title": _name("", "", url),
                "text": "Listed in the public My Medical Gateway hospital catalogue.",
                "query": "My Medical Gateway public hospital catalogue",
                "retrieved_at": page["retrieved_at"],
            }
        )
    stats = {"seen": 0, "new": 0, "countries": len(results_by_country)}
    for country, results in results_by_country.items():
        captured = capture(results, country, source_type="mymedicalgateway")
        stats["seen"] += captured["seen"]
        stats["new"] += captured["new"]
    return stats


def backfill_market_sources() -> dict:
    """Turn retained historical Exa sources into reviewable candidates."""
    grouped = {}
    for row in market.rows(
        "SELECT run_id,country,url,retrieved_at,payload FROM market_source WHERE provider='exa'"
    ):
        try:
            payload = json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        grouped.setdefault(row["country"], []).append(
            {
                "url": row["url"],
                "title": payload.get("title", ""),
                "text": payload.get("text", ""),
                "query": payload.get("query") or row["run_id"],
                "retrieved_at": row["retrieved_at"],
            }
        )
    stats = {"seen": 0, "new": 0}
    for country, results in grouped.items():
        if country not in COUNTRIES:
            continue
        captured = capture(results, country)
        stats["seen"] += captured["seen"]
        stats["new"] += captured["new"]
    return stats
