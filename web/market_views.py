"""Market workspace and administrator configuration using the existing FastHTML shell."""

from __future__ import annotations

import json
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fasthtml.common import (
    A,
    Button,
    Div,
    Form,
    H1,
    H2,
    Input,
    Label,
    Option,
    P,
    Select,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
    Details,
    Summary,
)
from starlette.responses import RedirectResponse, Response

from web import market
from web.layout import plot_div
from web.market_search import COUNTRIES


MARKET_CSS = """
.market-shell {max-width:1500px;margin:auto;color:#1b2733}
.market-shell h1 {margin:0 0 16px;font-size:28px}
.market-shell h2 {margin-top:24px}
.market-shell p {line-height:1.5;color:#526576}
.market-shell form {display:flex;flex-wrap:wrap;gap:14px;align-items:end;background:#fff;border:1px solid #dbe6e6;border-radius:12px;padding:18px;margin:18px 0}
.market-shell label {display:flex;flex:1 1 180px;min-width:0;flex-direction:column;gap:7px;font-size:13px;font-weight:600}
.market-shell input:not([type=hidden]):not([type=checkbox]),.market-shell select {box-sizing:border-box;width:100%;max-width:100%;min-width:0;padding:9px 10px;border:1px solid #ccdada;border-radius:7px;background:#fff;color:#1b2733}
.market-shell select[multiple] {min-height:110px}
.market-shell button {padding:10px 16px;border:0;border-radius:8px;background:#1e6fb8;color:white;font-weight:600;cursor:pointer}
.market-shell table {width:100%;border-collapse:collapse;background:white;border-radius:10px;font-size:13px}
.market-shell th {text-align:left;background:#eaf2f7;color:#28516c;padding:12px}
.market-shell td {padding:12px;border-bottom:1px solid #e5ecef;vertical-align:top;overflow-wrap:anywhere}
.market-shell details {margin:8px 0;max-width:100%}
.market-shell summary {cursor:pointer;color:#1e6fb8;font-size:13px}
.market-shell .plot {border:1px solid #dbe6e6;border-radius:12px;overflow:hidden;margin:16px 0}
.market-shell .leaflet-container {border:1px solid #dbe6e6;margin:18px 0}
"""


def options(name, values, selected="", all_label="All"):
    return Select(
        Option(all_label, value=""),
        *[Option(label, value=key, selected=key == selected) for key, label in values],
        name=name,
    )


def price(r):
    if r["price"] is None:
        return "Unavailable"
    prefix = "From " if r["price_type"] == "from" else ""
    end = "–" + r["price_max"] if r["price_type"] == "range" and r["price_max"] else ""
    return f"{prefix}{r['price']}{end} {r['currency']}"


def chart(data, title):
    spec = json.dumps(
        {
            "data": data,
            "layout": {
                "title": title,
                "height": 340,
                "margin": {"l": 70, "r": 20, "b": 100, "t": 50},
                "xaxis": {"automargin": True},
                "yaxis": {"title": "EUR", "automargin": True},
                "barmode": "group",
            },
        },
        ensure_ascii=False,
    ).replace("<", "\\u003c")
    return plot_div("market-" + secrets.token_hex(6), spec)


def workspace(
    csrf,
    country="",
    hospital="",
    service="",
    price_type="",
    q="",
    page_number=1,
    sort="newest",
    min_price="",
    max_price="",
    freshness="",
    changed="",
):
    history = market.observations()
    latest = market.latest_prices(history)
    hospitals = market.rows("SELECT id,name,country FROM market_hospital ORDER BY name")
    services = market.rows("SELECT id,name FROM market_service ORDER BY name")

    def matches(r):
        return (
            (not country or r["country"] == country)
            and (not hospital or r["hospital_id"] == hospital)
            and (not service or r["service_id"] == service)
            and (not price_type or r["price_type"] == price_type)
            and (
                not q
                or q.casefold()
                in (
                    r["service"] + " " + r["original_name"] + " " + r["hospital"]
                ).casefold()
            )
        )

    from decimal import Decimal, InvalidOperation

    def bound(value):
        try:
            d = Decimal(value)
            return d if d.is_finite() else None
        except (InvalidOperation, ValueError):
            return None

    low, high = bound(min_price), bound(max_price)
    filtered = [
        r
        for r in latest
        if matches(r)
        and (low is None or r["price"] is not None and Decimal(r["price"]) >= low)
        and (high is None or r["price"] is not None and Decimal(r["price"]) <= high)
        and (not freshness or r["stale"] == (freshness == "stale"))
        and (not changed or r["change"] is not None and r["change"] != 0)
    ]
    if sort == "clinic":
        filtered.sort(key=lambda r: (r["hospital"].casefold(), r["service"].casefold()))
    elif sort == "service":
        filtered.sort(key=lambda r: (r["service"].casefold(), r["hospital"].casefold()))
    elif sort in ("price_asc", "price_desc"):
        filtered.sort(
            key=lambda r: (
                r["price"] is None,
                (float(r["price"] or 0)) * (1 if sort == "price_asc" else -1),
            )
        )
    runs = market.rows("SELECT * FROM market_run ORDER BY created_at DESC LIMIT 8")
    count = len(filtered)
    page_number = max(1, min(int(page_number), max(1, (count + 99) // 100)))
    table_rows = []
    for r in filtered[(page_number - 1) * 100 : page_number * 100]:
        delta = (
            "—"
            if r["change"] is None
            else f"{r['change']:+.2f} EUR"
            + (f" ({r['change_pct']:+.1f}%)" if r["change_pct"] is not None else "")
        )
        if r["change_max"] is not None:
            delta += f"; upper {r['change_max']:+.2f} EUR"
        table_rows.append(
            Tr(
                Td(COUNTRIES[r["country"]]),
                Td(A(r["hospital"], href="/market/clinics/" + r["hospital_id"])),
                Td(
                    r["service"], Details(Summary(r["original_name"]), P(r["evidence"]))
                ),
                Td(price(r)),
                Td(delta),
                Td(r["retrieved_at"] + (" · stale" if r["stale"] else "")),
                Td(
                    A(
                        "Source",
                        href=r["source_url"],
                        target="_blank",
                        rel="noopener noreferrer",
                    ),
                    P(r["provider"]),
                ),
            )
        )
    charts = []
    if service:
        eligible = [r for r in filtered if r["price"] is not None]
        kinds = {
            "exact": "Exact prices",
            "from": "Starting prices",
            "range": "Published price ranges",
        }
        for kind, title in kinds.items():
            tariffs = [r for r in eligible if r["price_type"] == kind][:30]
            if not tariffs:
                continue
            trace = {
                "type": "bar",
                "x": [r["hospital"] + " · " + r["original_name"] for r in tariffs],
                "y": [float(r["price"]) for r in tariffs],
                "name": title,
            }
            if kind == "range":
                trace["error_y"] = {
                    "type": "data",
                    "symmetric": False,
                    "array": [
                        float(r["price_max"]) - float(r["price"]) for r in tariffs
                    ],
                    "arrayminus": [0] * len(tariffs),
                }
            charts.append(
                chart([trace], title + " for selected service (up to 30 tariffs)")
            )
        visible_keys = {market.comparison_key(r) for r in eligible}
        series = defaultdict(dict)
        for r in sorted(history, key=lambda r: r["retrieved_at"]):
            if market.comparison_key(r) in visible_keys and r["price"] is not None:
                series[
                    (
                        r["hospital"],
                        r["original_name"],
                        r["source_url"],
                        r["price_type"],
                    )
                ][market.week(r["retrieved_at"])] = (
                    float(r["price"]),
                    float(r["price_max"]) if r["price_max"] else None,
                )
        traces = []
        for (name, label, url, kind), points in list(series.items())[:12]:
            start = datetime.fromisoformat(min(points))
            end = datetime.fromisoformat(max(points))
            weeks = []
            while start <= end:
                weeks.append(start.date().isoformat())
                start += timedelta(days=7)
            trace = {
                "type": "scatter",
                "mode": "lines+markers",
                "name": name + " · " + label + " · " + kind,
                "x": weeks,
                "y": [points[w][0] if w in points else None for w in weeks],
                "connectgaps": False,
            }
            if kind == "range":
                trace["error_y"] = {
                    "type": "data",
                    "symmetric": False,
                    "array": [
                        (
                            points[w][1] - points[w][0]
                            if w in points and points[w][1] is not None
                            else None
                        )
                        for w in weeks
                    ],
                    "arrayminus": [0] * len(weeks),
                }
            traces.append(trace)
        if traces:
            charts.append(
                chart(
                    traces,
                    "Weekly price history · price types labelled (up to 12 tariffs)",
                )
            )
    else:
        counts = {
            c: len({r["hospital_id"] for r in filtered if r["country"] == c})
            for c in COUNTRIES
        }
        spec = json.dumps(
            {
                "data": [
                    {
                        "type": "bar",
                        "x": [COUNTRIES[c] for c in counts],
                        "y": list(counts.values()),
                    }
                ],
                "layout": {
                    "title": "Private providers with observed services",
                    "height": 300,
                    "yaxis": {"title": "Providers"},
                },
            }
        )
        charts = [
            plot_div("market-coverage", spec),
            P(
                "Choose a treatment/service to compare prices and see weekly history. Exact prices, starting prices and ranges remain separate."
            ),
        ]
    from urllib.parse import urlencode

    def page_link(n):
        return "/market/competitive-intelligence?" + urlencode(
            dict(
                country=country,
                hospital=hospital,
                service=service,
                price_type=price_type,
                q=q,
                page_number=n,
                sort=sort,
                min_price=min_price,
                max_price=max_price,
                freshness=freshness,
                changed=changed,
            )
        )

    return Div(
        H1("Competitive Intelligence"),
        P(
            "Lithuania · Latvia · Estonia — discovered private hospitals and clinics. Coverage is partial and expands over time. Collection timestamps are UTC; source publication dates do not establish current prices."
        ),
        Form(
            Input(type="hidden", name="csrf", value=csrf),
            Button("Search now", type="submit"),
            action="/market/search",
            method="post",
        ),
        P(
            "Searches run in the background. Reload to see progress. Weekly collection uses Monday–Sunday UTC, with catch-up after downtime."
        ),
        Details(
            Summary("Recent searches"),
            Table(
                Thead(
                    Tr(
                        *[
                            Th(x)
                            for x in ["Started UTC", "Status", "Trigger", "Results"]
                        ]
                    )
                ),
                Tbody(
                    *[
                        Tr(
                            Td(r["created_at"]),
                            Td(r["status"]),
                            Td(r["trigger_kind"]),
                            Td(r["stats"], r["error"] or ""),
                        )
                        for r in runs
                    ]
                ),
            ),
        ),
        Form(
            Label("Country", options("country", COUNTRIES.items(), country)),
            Label(
                "Hospital / clinic",
                options(
                    "hospital",
                    [
                        (h["id"], h["name"])
                        for h in hospitals
                        if not country or h["country"] == country
                    ],
                    hospital,
                ),
            ),
            Label(
                "Treatment / service",
                options("service", [(s["id"], s["name"]) for s in services], service),
            ),
            Label(
                "Price type",
                options(
                    "price_type",
                    [(k, k.title()) for k in ["exact", "from", "range", "unavailable"]],
                    price_type,
                ),
            ),
            Label("Find", Input(name="q", value=q)),
            Label(
                "Minimum EUR",
                Input(
                    type="number", name="min_price", value=min_price, min=0, step="0.01"
                ),
            ),
            Label(
                "Maximum EUR",
                Input(
                    type="number", name="max_price", value=max_price, min=0, step="0.01"
                ),
            ),
            Label(
                "Freshness",
                options(
                    "freshness",
                    [
                        ("current", "Observed this week"),
                        ("stale", "Older observations"),
                    ],
                    freshness,
                ),
            ),
            Label(
                "Weekly changes",
                options("changed", [("yes", "Changed prices only")], changed),
            ),
            Label(
                "Sort by",
                options(
                    "sort",
                    [
                        ("newest", "Most recent"),
                        ("clinic", "Clinic"),
                        ("service", "Service"),
                        ("price_asc", "Price low to high"),
                        ("price_desc", "Price high to low"),
                    ],
                    sort,
                ),
            ),
            Button("Apply filters"),
            action="/market/competitive-intelligence",
            method="get",
        ),
        P(
            f"{count} tariffs · {len({r['hospital_id'] for r in filtered})} providers · {sum(r['price'] is not None for r in filtered)} published prices · {sum(r['change'] is not None for r in filtered)} weekly comparisons"
        ),
        *charts,
        P(
            "Weekly changes compare identical tariffs in consecutive observed weeks. A dash means no comparable baseline. Stale observations are retained and labelled."
        ),
        Div(
            Table(
                Thead(
                    Tr(
                        *[
                            Th(x)
                            for x in [
                                "Country",
                                "Hospital / clinic",
                                "Treatment / service",
                                "Price",
                                "Week-on-week",
                                "Collected UTC",
                                "Evidence",
                            ]
                        ]
                    )
                ),
                Tbody(*table_rows),
            ),
            style="overflow-x:auto",
        ),
        P(f"Page {page_number} of {max(1,(count+99)//100)}"),
        A("Previous", href=page_link(max(1, page_number - 1))),
        " · ",
        A("Next", href=page_link(page_number + 1)),
    )


def configuration(csrf, error=""):
    cfg = market.config()

    def multi(key, label, values):
        selected = cfg[key]
        return Label(
            label,
            Select(
                *[
                    Option(text, value=value, selected=value in selected)
                    for value, text in values
                ],
                name=key,
                multiple=True,
                size=min(10, max(3, len(values))),
            ),
        )

    return Div(
        H1("Market Configuration"),
        P(error),
        P(
            "All includes newly discovered entries on future runs. To restrict coverage, deselect All and select individual entries. Prices are recorded per service; unavailable prices remain visible."
        ),
        Form(
            Input(type="hidden", name="csrf", value=csrf),
            multi("countries", "Countries", list(COUNTRIES.items())),
            multi(
                "hospitals",
                "Hospitals / clinics",
                [("*", "All current and future private providers")]
                + [
                    (h["id"], h["name"])
                    for h in market.rows(
                        "SELECT id,name FROM market_hospital ORDER BY name"
                    )
                ],
            ),
            multi(
                "treatments",
                "Treatments / services",
                [("*", "All current and future services")]
                + [
                    (s["id"], s["name"])
                    for s in market.rows(
                        "SELECT id,name FROM market_service ORDER BY name"
                    )
                ],
            ),
            P(A("Exa provider and API keys", href="/integrations/search-provider")),
            Label(
                Input(
                    type="checkbox", name="weekly", value="yes", checked=cfg["weekly"]
                ),
                "Weekly automatic search (Monday UTC; catches up after downtime)",
            ),
            Label(
                "Maximum queries per run",
                Input(
                    type="number",
                    name="max_queries",
                    min=1,
                    max=200,
                    value=cfg["max_queries"],
                ),
            ),
            Label(
                "Maximum pages per run",
                Input(
                    type="number",
                    name="max_pages",
                    min=1,
                    max=300,
                    value=cfg["max_pages"],
                ),
            ),
            P(
                "Limits bound each run; a maximum of one active search and a five-minute cooldown prevent repeated clicks creating duplicate work. Historical observations are retained when selections change."
            ),
            Button("Save configuration", type="submit"),
            action="/admin/market",
            method="post",
        ),
    )


def map_view(country="", hospital=""):
    from web import market_map
    from fasthtml.common import Link, Script, NotStr
    import os

    locations = market_map.clinics(country)
    if hospital:
        locations = [r for r in locations if r["hospital_id"] == hospital]
    points = [
        {
            k: r[k]
            for k in [
                "name",
                "address",
                "city",
                "country",
                "latitude",
                "longitude",
                "hospital_id",
                "source_url",
            ]
        }
        for r in locations
        if r["geocode_status"] == "located"
    ]
    tile_url = os.getenv(
        "MARKET_MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    )
    attribution = os.getenv("MARKET_MAP_ATTRIBUTION", "© OpenStreetMap contributors")
    data = json.dumps(
        {"points": points, "tiles": tile_url, "attribution": attribution},
        ensure_ascii=False,
    ).replace("<", "\\u003c")
    script = """(function(){
      var config=CONFIG;
      var map=L.map('market-map',{scrollWheelZoom:true}).setView([56.8,24.5],6);
      L.tileLayer(config.tiles,{maxZoom:19,attribution:config.attribution+' · <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(map);
      var bounds=[];
      config.points.forEach(function(p){
        var lat=Number(p.latitude),lon=Number(p.longitude); if(!Number.isFinite(lat)||!Number.isFinite(lon)) return;
        var popup=document.createElement('div');
        var title=document.createElement('strong');title.textContent=p.name;popup.appendChild(title);
        var address=document.createElement('p');address.textContent=p.address+', '+p.city+' ('+p.country+')';popup.appendChild(address);
        var link=document.createElement('a');link.href='/market/clinics/'+encodeURIComponent(p.hospital_id);link.textContent='View clinic and prices';popup.appendChild(link);
        L.marker([lat,lon]).addTo(map).bindPopup(popup);bounds.push([lat,lon]);
      });
      if(bounds.length)map.fitBounds(bounds,{padding:[35,35],maxZoom:13});
      setTimeout(function(){map.invalidateSize();},200);
    })();""".replace(
        "CONFIG", data
    )
    known = market.rows("SELECT id,name,country FROM market_hospital ORDER BY name")
    pending = [
        h
        for h in known
        if (not country or h["country"] == country)
        and (not hospital or h["id"] == hospital)
        and h["id"] not in {r["hospital_id"] for r in locations}
    ]
    return Div(
        H1("Market Map"),
        P(
            "Pan or zoom to explore competing private clinics. Open a pin to view the clinic and its service prices."
        ),
        Form(
            Label("Country", options("country", COUNTRIES.items(), country)),
            Button("Apply filters"),
            method="get",
        ),
        P(
            f"{len(points)} located branches · {len(locations)-len(points)+len(pending)} locations pending"
        ),
        Link(rel="stylesheet", href="/static/vendor/leaflet/leaflet.css"),
        Script(src="/static/vendor/leaflet/leaflet.js"),
        Div(
            id="market-map",
            style="height:560px;width:100%;border-radius:12px;z-index:0",
            role="region",
            aria_label="Interactive competitor clinic map",
        ),
        Script(NotStr(script)),
        Table(
            Thead(Tr(Th("Clinic"), Th("Address"), Th("Location"), Th("Source"))),
            Tbody(
                *[
                    Tr(
                        Td(A(r["name"], href="/market/clinics/" + r["hospital_id"])),
                        Td(r["address"] + ", " + r["city"]),
                        Td(r["geocode_status"]),
                        Td(
                            A(
                                "Address source",
                                href=r["source_url"],
                                target="_blank",
                                rel="noopener noreferrer",
                            )
                        ),
                    )
                    for r in locations
                ],
                *[
                    Tr(
                        Td(A(h["name"], href="/market/clinics/" + h["id"])),
                        Td("Address pending"),
                        Td("pending"),
                        Td("—"),
                    )
                    for h in pending
                ],
            ),
        ),
        P(
            "Addresses are sourced from clinic websites. Pins represent matched street addresses; ambiguous matches remain pending. Map data © OpenStreetMap contributors."
        ),
    )


def clinic_detail(csrf, hospital_id, service="", price_type="", q=""):
    hospital = market.rows("SELECT * FROM market_hospital WHERE id=?", (hospital_id,))
    if not hospital:
        return Div(H1("Clinic not found"))
    h = hospital[0]
    from web import market_map

    locations = [
        r for r in market_map.clinics(h["country"]) if r["hospital_id"] == hospital_id
    ]
    return Div(
        H1(h["name"]),
        P(COUNTRIES[h["country"]]),
        A(
            "Website",
            href="https://" + h["domain"],
            target="_blank",
            rel="noopener noreferrer",
        ),
        " · ",
        A("View on map", href="/market/map?hospital=" + hospital_id),
        " · ",
        A("All competitors", href="/market/competitive-intelligence"),
        P("Private ownership evidence: " + h["evidence"]),
        A(
            "Ownership source",
            href=h["source_url"],
            target="_blank",
            rel="noopener noreferrer",
        ),
        *[
            P(
                r["address"]
                + ", "
                + r["city"]
                + " · "
                + (r["phone"] or "")
                + " · "
                + r["geocode_status"]
            )
            for r in locations
        ],
        workspace(
            csrf, hospital=hospital_id, service=service, price_type=price_type, q=q
        ),
    )


def register(rt, app, require, render):
    def token(session):
        return session.setdefault("market_csrf", secrets.token_urlsafe(32))

    def valid(session, form):
        return bool(session.get("market_csrf")) and secrets.compare_digest(
            str(form.get("csrf", "")), session["market_csrf"]
        )

    @rt("/market/competitive-intelligence", methods=["GET"])
    def market_page(
        session,
        country: str = "",
        hospital: str = "",
        service: str = "",
        price_type: str = "",
        q: str = "",
        page_number: int = 1,
        sort: str = "newest",
        min_price: str = "",
        max_price: str = "",
        freshness: str = "",
        changed: str = "",
    ):
        email, denied = require(session, "market")
        if denied:
            return denied
        return render(
            session,
            "market",
            workspace(
                token(session),
                country,
                hospital,
                service,
                price_type,
                q,
                page_number,
                sort,
                min_price,
                max_price,
                freshness,
                changed,
            ),
        )

    @rt("/market/map", methods=["GET"])
    def market_map_page(session, country: str = "", hospital: str = ""):
        email, denied = require(session, "market-map")
        if denied:
            return denied
        return render(session, "market-map", map_view(country, hospital))

    @rt("/market/clinics/{hospital_id}", methods=["GET"])
    def market_clinic_page(
        session, hospital_id: str, service: str = "", price_type: str = "", q: str = ""
    ):
        email, denied = require(session, "market")
        if denied:
            return denied
        if not market.rows("SELECT id FROM market_hospital WHERE id=?", (hospital_id,)):
            return Response("Clinic not found", status_code=404)
        return render(
            session,
            "market",
            clinic_detail(token(session), hospital_id, service, price_type, q),
        )

    @rt("/market/search", methods=["POST"])
    async def market_search(request, session):
        email, denied = require(session, "market")
        if denied:
            return denied
        form = await request.form()
        if not valid(session, form):
            return Response("Invalid form token", status_code=403)
        market.enqueue(email)
        return RedirectResponse("/market/competitive-intelligence", status_code=303)

    @rt("/admin/market", methods=["GET"])
    def market_config(session):
        email, denied = require(session, "market-config")
        if denied:
            return denied
        return render(session, "market-config", configuration(token(session)))

    @rt("/admin/market", methods=["POST"])
    async def market_config_save(request, session):
        email, denied = require(session, "market-config")
        if denied:
            return denied
        form = await request.form()
        if not valid(session, form):
            return Response("Invalid form token", status_code=403)
        try:
            market.save_config(
                {
                    **{
                        k: form.getlist(k)
                        for k in ["countries", "hospitals", "treatments"]
                    },
                    "providers": ["exa"],
                    "weekly": form.get("weekly") == "yes",
                    "max_queries": int(form.get("max_queries", "24")),
                    "max_pages": int(form.get("max_pages", "30")),
                }
            )
        except ValueError as exc:
            return render(
                session, "market-config", configuration(token(session), str(exc))
            )
        return RedirectResponse("/admin/market", status_code=303)

    from web import search_provider, access

    def integration_form(session, email, message=""):
        own = search_provider.configured(email)
        shared = search_provider.configured(search_provider.SHARED)
        # The route guard already respects role preview for the shared-key control.
        _, admin_denied = require(session, "market-config")
        admin = admin_denied is None
        import os

        return Div(
            H1("search_provider"),
            P(message),
            P(
                "Exa searches public websites for Market intelligence. Your key is used for searches you request. Weekly searches use the shared key. Results contribute to the shared staff Market workspace."
            ),
            P("Personal key: " + ("Configured" if own else "Not configured")),
            P(
                "Shared key: "
                + (
                    "Configured"
                    if shared or os.getenv("EXA_API_KEY")
                    else "Not configured"
                )
            ),
            Form(
                Input(type="hidden", name="csrf", value=token(session)),
                Label(
                    "Search provider",
                    Select(Option("Exa", value="exa"), name="search_provider"),
                ),
                Label(
                    "API key",
                    Input(
                        type="password",
                        name="api_key",
                        autocomplete="new-password",
                        placeholder="Enter a new key to save or replace",
                    ),
                ),
                Select(
                    Option("My searches", value="personal"),
                    *(
                        [Option("Shared / weekly searches", value="shared")]
                        if admin
                        else []
                    ),
                    name="scope",
                ),
                Button("Save key", name="action", value="save"),
                Button("Test connection", name="action", value="test"),
                Button("Remove saved key", name="action", value="remove"),
                action="/integrations/search-provider",
                method="post",
            ),
            P(
                "Saved keys are encrypted and never displayed. Test connection makes one Exa request; enter a key to test it before saving, or leave the field blank to test the saved configuration. Removing a saved key restores the deployment fallback."
            ),
        )

    @rt("/integrations/search-provider", methods=["GET"])
    def integration_page(session):
        email, denied = require(session, "search-provider")
        if denied:
            return denied
        return render(session, "search-provider", integration_form(session, email))

    @rt("/integrations/search-provider", methods=["POST"])
    async def integration_save(request, session):
        import asyncio
        from web.market_search import search

        email, denied = require(session, "search-provider")
        if denied:
            return denied
        form = await request.form()
        if not valid(session, form):
            return Response("Invalid form token", status_code=403)
        owner = email
        if form.get("scope") == "shared":
            _, denied = require(session, "market-config")
            if denied:
                return denied
            owner = search_provider.SHARED
        try:
            if form.get("search_provider") != "exa":
                raise ValueError("Only Exa is enabled")
            action = form.get("action")
            if action == "save":
                search_provider.save(owner, str(form.get("api_key", "")))
                message = "Exa key saved."
            elif action == "remove":
                search_provider.remove(owner)
                message = "Saved key removed."
            elif action == "test":
                key = str(form.get("api_key", "")).strip() or search_provider.resolve(
                    owner
                )
                results = await asyncio.to_thread(
                    search,
                    "exa",
                    "Estonia private clinic official website",
                    1,
                    None,
                    key,
                )
                message = f"Exa connection successful: {len(results)} result(s)."
            else:
                raise ValueError("Unknown action")
        except (ValueError, RuntimeError) as exc:
            message = str(exc)
        return render(
            session, "search-provider", integration_form(session, email, message)
        )

    import os
    import threading

    stop = threading.Event()

    def worker():
        from scripts.seed_market import seed

        try:
            seed()
        except Exception:
            market.log.exception("Market baseline import unavailable")
        while not stop.is_set():
            try:
                market.tick()
            except Exception:
                market.log.exception("Market scheduler unavailable")
            stop.wait(15)

    def start():
        if os.getenv("FASTCLINIC_MARKET_WORKER_ENABLED", "true").lower() == "true":
            stop.clear()
            threading.Thread(target=worker, name="market-worker", daemon=True).start()

    from contextlib import asynccontextmanager

    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application) as state:
            start()
            try:
                yield state
            finally:
                stop.set()

    app.router.lifespan_context = lifespan
