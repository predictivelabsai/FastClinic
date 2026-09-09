"""Market workspace and administrator configuration using the existing FastHTML shell."""

from __future__ import annotations

import json
import secrets
from datetime import timezone

from fasthtml.common import (
    A,
    Button,
    Div,
    Form,
    H1,
    H2,
    H3,
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
    Script,
    NotStr,
    Textarea,
)
from starlette.responses import RedirectResponse, Response

from web import market
from web.layout import plot_div
from web.market_search import COUNTRIES


MARKET_CSS = """
.market-shell {max-width:1500px;margin:auto;color:#1b2733}
.market-shell h1 {margin:0 0 8px;font-size:28px}
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
.market-hero {display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:18px}
.market-hero p {max-width:850px;margin:0}
.market-shell .market-search-action {margin:0;padding:0;background:transparent;border:0;flex:0 0 auto}
.market-kpis {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}
.market-kpi {background:linear-gradient(145deg,#fff,#f7fbfc);border:1px solid #dbe6e6;border-radius:12px;padding:16px}
.market-kpi strong {display:block;font-size:25px;color:#1b2733;margin-bottom:3px}
.market-kpi span {font-size:12px;color:#607585}
.market-chart-grid {display:grid;grid-template-columns:minmax(0,1.45fr) minmax(280px,.75fr);gap:14px;align-items:stretch}
.market-chart-card {background:#fff;border:1px solid #dbe6e6;border-radius:12px;overflow:hidden;min-width:0}
.market-chart-card .plot {border:0;margin:0}
.market-section-head {display:flex;align-items:end;justify-content:space-between;gap:18px;margin:26px 0 10px}
.market-section-head h2 {margin:0}.market-section-head p {margin:0;font-size:12px}
.market-table-tools {display:grid;grid-template-columns:minmax(180px,1.4fr) repeat(3,minmax(130px,.7fr));gap:8px;padding:10px;background:#f6fafb;border:1px solid #dbe6e6;border-bottom:0;border-radius:10px 10px 0 0}
.market-table-tools input,.market-table-tools select {padding:8px!important;font-size:12px}
.market-table-wrap {overflow-x:auto;border:1px solid #dbe6e6;border-radius:0 0 10px 10px}
.market-table-wrap table {border-radius:0}
.market-table-wrap tbody tr:hover {background:#f5faf9}
.market-segment {display:inline-block;padding:3px 8px;border-radius:999px;background:#e8f5f0;color:#187c5c;font-size:11px;font-weight:700}
.market-segment.multi {background:#eaf2f7;color:#1e6fb8}
.market-status {font-weight:700;font-size:12px;color:#526576}
.market-status.priced {color:#187c5c}.market-status.queued {color:#9a632e}
.market-view-toggle {display:flex;gap:8px;margin:14px 0}
.market-view-toggle a {padding:7px 11px;border:1px solid #ccdada;border-radius:999px;text-decoration:none;font-size:12px;color:#28516c;background:#fff}
.market-view-toggle a.active {background:#1e6fb8;color:#fff;border-color:#1e6fb8}
@media(max-width:900px){.market-kpis{grid-template-columns:repeat(2,1fr)}.market-chart-grid{grid-template-columns:1fr}.market-table-tools{grid-template-columns:1fr 1fr}.market-hero{flex-direction:column}}
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


def market_plot(payload):
    if not payload:
        return None
    spec = json.dumps(payload["figure"], ensure_ascii=False).replace("<", "\\u003c")
    return Div(
        *plot_div("market-" + secrets.token_hex(6), spec), cls="market-chart-card"
    )


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
    focus="wellness",
    segment="",
    city="",
):
    from web.market_catalog import is_wellness_service
    from web.market_charts import build_chart, target_snapshot

    history = market.observations()
    latest = market.latest_prices(history)
    targets = target_snapshot()
    hospitals = market.rows("SELECT id,name,country,domain FROM market_hospital ORDER BY name")
    observed_by_domain = {h["domain"]: h for h in hospitals}
    effective_focus = "" if hospital or service else focus

    def matches(r):
        return (
            (not country or r["country"] == country)
            and (not hospital or r["hospital_id"] == hospital)
            and (not service or r["service_id"] == service)
            and (not price_type or r["price_type"] == price_type)
            and (effective_focus != "wellness" or is_wellness_service(r))
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
    runs = market.rows("SELECT * FROM market_run ORDER BY created_at DESC LIMIT 6")
    count = len(filtered)
    table_rows = []
    for r in filtered[:500]:
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
                data_search=(r["hospital"] + " " + r["service"] + " " + r["original_name"]).casefold(),
                data_clinic=r["hospital"],
                data_service=r["service"],
                data_price_type=r["price_type"],
            )
        )

    target_rows = []
    for target in targets:
        observed = next(
            (observed_by_domain[d] for d in target["domains"] if d in observed_by_domain),
            None,
        )
        target_rows.append(
            Tr(
                Td(
                    A(target["name"], href=("/market/clinics/" + observed["id"]) if observed else target["service_url"], target="_blank" if not observed else None),
                    P(target["positioning"]),
                ),
                Td(
                    Div(
                        target["segment"],
                        cls="market-segment" + (" multi" if target["segment"].startswith("Multi") else ""),
                    )
                ),
                Td(", ".join(target["cities"])),
                Td(f"{target['wellness_tariffs']} wellness · {target['tariffs']} total"),
                Td(target["status"], cls="market-status " + target["coverage"]),
                Td(
                    A("Official service page", href=target["service_url"], target="_blank", rel="noopener noreferrer"),
                    P(target["last_checked"] or "Awaiting first run"),
                ),
                data_search=(target["name"] + " " + target["positioning"] + " " + " ".join(target["cities"])).casefold(),
                data_segment=target["segment"],
                data_city=" ".join(target["cities"]),
                data_coverage=target["coverage"],
            )
        )

    active_targets = [t for t in targets if t["active"]]
    priced_targets = sum(t["wellness_tariffs"] > 0 for t in active_targets)
    sourced_targets = sum(t["sources"] > 0 or t["tariffs"] > 0 for t in active_targets)
    specialists = sum(t["segment"].startswith("IV") for t in active_targets)
    cities = sorted({c for t in targets for c in t["cities"]})
    clinic_values = sorted({r["hospital"] for r in filtered})
    service_values = sorted({r["service"] for r in filtered})

    filter_script = """(function(){
      function wire(tableId,prefix,fields){
        var table=document.getElementById(tableId); if(!table)return;
        var inputs=fields.map(function(f){return document.getElementById(prefix+'-'+f);});
        var count=document.getElementById(prefix+'-count');
        function run(){var visible=0;
          table.querySelectorAll('tbody tr').forEach(function(row){
            var ok=fields.every(function(f,i){var value=(inputs[i]&&inputs[i].value||'').toLowerCase();
              if(!value)return true; var actual=(f==='search'?row.dataset.search:row.dataset[f]||'').toLowerCase();
              return actual.indexOf(value)!==-1;});
            row.hidden=!ok;if(ok)visible++;
          }); if(count)count.textContent=visible+' rows';
        }
        inputs.forEach(function(input){if(input){input.addEventListener('input',run);input.addEventListener('change',run);}});run();
      }
      wire('priority-competitors','target',['search','segment','city','coverage']);
      wire('market-tariffs','tariff',['search','clinic','service','priceType']);
    })();"""

    return Div(
        Div(
            Div(
                H1("Lithuania Wellness Competition"),
                P("A focused view of IV infusion, vitamin-drip and longevity clinics, with broader multi-specialty competitors tracked alongside source-backed prices."),
            ),
            Form(Input(type="hidden", name="csrf", value=csrf), Button("Refresh with Exa", type="submit"), action="/market/search", method="post", cls="market-search-action"),
            cls="market-hero",
        ),
        Div(
            Div(NotStr(f"<strong>{len(active_targets)}</strong><span>active priority competitors</span>"), cls="market-kpi"),
            Div(NotStr(f"<strong>{specialists}</strong><span>IV / longevity specialists</span>"), cls="market-kpi"),
            Div(NotStr(f"<strong>{sourced_targets}</strong><span>competitors with collected sources</span>"), cls="market-kpi"),
            Div(NotStr(f"<strong>{priced_targets}</strong><span>with wellness tariffs captured</span>"), cls="market-kpi"),
            cls="market-kpis",
        ),
        Div(
            market_plot(build_chart("landscape")),
            market_plot(build_chart("collection")),
            cls="market-chart-grid",
        ),
        market_plot(build_chart("capabilities")),
        market_plot(build_chart("wellness-prices")),
        Div(H2("Priority competitor watchlist"), P("Filter directly above the table; no page-wide filter form."), cls="market-section-head"),
        Div(
            Input(id="target-search", placeholder="Search clinic or positioning"),
            Select(Option("All models", value=""), Option("IV / longevity specialist"), Option("Multi-specialty clinic"), id="target-segment"),
            Select(Option("All locations", value=""), *[Option(c) for c in cities], id="target-city"),
            Select(Option("All coverage", value=""), Option("Wellness prices", value="priced"), Option("Other services", value="services"), Option("Official source", value="source"), Option("Queued", value="queued"), Option("Paused", value="paused"), id="target-coverage"),
            cls="market-table-tools",
        ),
        Div(Table(Thead(Tr(*[Th(x) for x in ["Competitor", "Model", "Locations", "Observed tariffs", "Coverage", "Evidence"]])), Tbody(*target_rows), id="priority-competitors"), cls="market-table-wrap"),
        P(f"{len(targets)} curated competitors. Positioning and capability tags are editorial classifications; prices, addresses and collection status remain source-backed observations."),
        Div(H2("Source-backed tariff evidence"), P(f"{count} matching tariffs · showing up to 500", id="tariff-count"), cls="market-section-head"),
        Div(
            A("Wellness & IV", href="/market/competitive-intelligence?focus=wellness", cls="active" if effective_focus == "wellness" else ""),
            A("All collected services", href="/market/competitive-intelligence?focus=", cls="active" if not effective_focus else ""),
            cls="market-view-toggle",
        ),
        Div(
            Input(id="tariff-search", placeholder="Search evidence"),
            Select(Option("All clinics", value=""), *[Option(v) for v in clinic_values], id="tariff-clinic"),
            Select(Option("All services", value=""), *[Option(v) for v in service_values], id="tariff-service"),
            Select(Option("All price types", value=""), *[Option(v.title(), value=v) for v in ["exact", "from", "range", "unavailable"]], id="tariff-priceType"),
            cls="market-table-tools",
        ),
        Div(Table(Thead(Tr(*[Th(x) for x in ["Country", "Clinic", "Service", "Price", "Week-on-week", "Collected UTC", "Evidence"]])), Tbody(*table_rows), id="market-tariffs"), cls="market-table-wrap"),
        P("Exact, starting, range and unavailable prices stay separate. Weekly comparisons require the identical tariff in consecutive observed weeks."),
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
        Script(NotStr(filter_script)),
    )


def watchlist_editor(csrf, edit_id="", message=""):
    from web import market_watchlist

    entries = market_watchlist.items()
    current = market_watchlist.get(edit_id) if edit_id else None
    return Div(
        Div(
            Div(
                H1("Watchlist Editor"),
                P("Curate identified competitor URLs without an Exa search. Active URLs are deep-scraped alongside discovered pages; the same evidence checks and price history apply to both."),
            ),
            A("Back to dashboard", href="/market/competitive-intelligence", cls="btn"),
            cls="market-hero",
        ),
        P(message, cls="market-status") if message else None,
        Form(
            Input(type="hidden", name="csrf", value=csrf),
            Input(type="hidden", name="id", value=current["id"] if current else ""),
            Label("Clinic name", Input(name="name", value=current["name"] if current else "", required=True)),
            Label("Country", Select(*[Option(label, value=key, selected=current and current["country"] == key) for key, label in COUNTRIES.items()], name="country")),
            Label("Competitor model", Select(*[Option(value, selected=current and current["segment"] == value) for value in ("IV / longevity specialist", "Multi-specialty clinic")], name="segment")),
            Label("Cities (comma separated)", Input(name="cities", value=", ".join(current["cities"]) if current else "Vilnius", required=True)),
            Label("Priority", Input(type="number", name="priority", min=1, max=999, value=current["priority"] if current else len(entries) + 1)),
            Label("Positioning", Input(name="positioning", value=current["positioning"] if current else "")),
            Label("Official URLs — one per line", Textarea("\n".join(current["urls"]) if current else "", name="urls", rows=5, required=True), style="flex-basis:100%"),
            Label(Input(type="checkbox", name="active", value="yes", checked=current["active"] if current else True), "Active — include in discovery and deep scraping"),
            Button("Save competitor", type="submit"),
            A("Cancel edit", href="/market/watchlist", cls="btn") if current else None,
            action="/market/watchlist",
            method="post",
        ),
        Div(H2("Curated competitors"), P(f"{len(entries)} entries · paused entries remain available for audit"), cls="market-section-head"),
        Div(
            Table(
                Thead(Tr(*[Th(x) for x in ["Priority", "Competitor", "Model", "URLs", "State", "Actions"]])),
                Tbody(
                    *[
                        Tr(
                            Td(item["priority"]),
                            Td(item["name"], P(", ".join(item["cities"]))),
                            Td(item["segment"]),
                            Td(*[P(A(url, href=url, target="_blank", rel="noopener noreferrer")) for url in item["urls"]]),
                            Td("Active" if item["active"] else "Paused", cls="market-status " + ("priced" if item["active"] else "queued")),
                            Td(
                                A("Edit", href="/market/watchlist?edit=" + item["id"], cls="btn"),
                                Form(
                                    Input(type="hidden", name="csrf", value=csrf),
                                    Button("Deep scrape now", type="submit"),
                                    action="/market/watchlist/" + item["id"] + "/scrape",
                                    method="post",
                                    cls="market-search-action",
                                ) if item["active"] else None,
                            ),
                        )
                        for item in entries
                    ]
                ),
            ),
            cls="market-table-wrap",
        ),
        P("Pausing stops future collection but does not erase historical sources, prices or audit context."),
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
        P("Evidence: " + h["evidence"]),
        A(
            "Official service page",
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
        focus: str = "wellness",
        segment: str = "",
        city: str = "",
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
                focus,
                segment,
                city,
            ),
        )

    @rt("/market/map", methods=["GET"])
    def market_map_page(session, country: str = "", hospital: str = ""):
        email, denied = require(session, "market-map")
        if denied:
            return denied
        return render(session, "market-map", map_view(country, hospital))

    @rt("/market/watchlist", methods=["GET"])
    def market_watchlist_page(session, edit: str = ""):
        email, denied = require(session, "market-watchlist")
        if denied:
            return denied
        return render(session, "market-watchlist", watchlist_editor(token(session), edit))

    @rt("/market/watchlist", methods=["POST"])
    async def market_watchlist_save(request, session):
        from web import market_watchlist

        email, denied = require(session, "market-watchlist")
        if denied:
            return denied
        form = await request.form()
        if not valid(session, form):
            return Response("Invalid form token", status_code=403)
        try:
            ident = market_watchlist.save(
                str(form.get("id", "")),
                name=form.get("name", ""),
                country=form.get("country", ""),
                segment=form.get("segment", ""),
                cities=form.get("cities", ""),
                positioning=form.get("positioning", ""),
                urls=form.get("urls", ""),
                priority=form.get("priority", "999"),
                active=form.get("active") == "yes",
                actor=email,
            )
        except ValueError as exc:
            return render(session, "market-watchlist", watchlist_editor(token(session), str(form.get("id", "")), str(exc)))
        return RedirectResponse("/market/watchlist?edit=" + ident, status_code=303)

    @rt("/market/watchlist/{watchlist_id}/scrape", methods=["POST"])
    async def market_watchlist_scrape(request, session, watchlist_id: str):
        from web import market_watchlist

        email, denied = require(session, "market-watchlist")
        if denied:
            return denied
        form = await request.form()
        if not valid(session, form):
            return Response("Invalid form token", status_code=403)
        item = market_watchlist.get(watchlist_id)
        if not item or not item["active"]:
            return Response("Watchlist entry not found", status_code=404)
        market.enqueue(
            email,
            trigger="watchlist",
            config_override={
                "mode": "direct",
                "watchlist_ids": [watchlist_id],
                "countries": [item["country"]],
                "max_pages": len(item["urls"]),
            },
        )
        return RedirectResponse("/market/watchlist?edit=" + watchlist_id, status_code=303)

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
