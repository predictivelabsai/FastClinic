"""Plotly figure builders shared by the market dashboard and streamed assistant."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from statistics import median

from web import market, market_map
from web.market_catalog import CAPABILITIES, is_wellness_service
from web.market_search import domain


BLUE = "#1e6fb8"
GREEN = "#1f9d72"
INK = "#1b2733"
MUTED = "#607585"
GRID = "#e5ecef"
ORANGE = "#e98942"


def _layout(title, height=360, **extra):
    layout = {
        "title": {"text": title, "x": 0.02, "xanchor": "left", "font": {"size": 15}},
        "height": height,
        "autosize": True,
        "paper_bgcolor": "#ffffff",
        "plot_bgcolor": "#ffffff",
        "font": {"family": "Inter, system-ui, sans-serif", "color": INK, "size": 11},
        "margin": {"l": 52, "r": 24, "t": 54, "b": 48},
        "hoverlabel": {"bgcolor": "#ffffff"},
    }
    layout.update(extra)
    return layout


def target_snapshot(country="LT"):
    """Combine editorial targets with observed sources, prices and branch records."""
    prices = market.latest_prices()
    sources = market.rows(
        "SELECT url,retrieved_at,status FROM market_source ORDER BY retrieved_at DESC"
    )
    branches = market_map.clinics(country)
    from web.market_watchlist import items

    result = []
    watched = [target for target in items() if target["country"] == country]
    for target in watched:
        domains = set(target["domains"])
        tariffs = [r for r in prices if r["country"] == country and r["domain"] in domains]
        wellness = [r for r in tariffs if is_wellness_service(r)]
        source_rows = [s for s in sources if domain(s["url"]) in domains]
        target_branches = [
            b for b in branches if domain(b.get("website", "")) in domains
        ]
        if not target["active"]:
            status = "Paused"
            coverage = "paused"
        elif wellness:
            status = "Wellness prices captured"
            coverage = "priced"
        elif tariffs:
            status = "Other services captured"
            coverage = "services"
        elif source_rows:
            status = "Official source found"
            coverage = "source"
        else:
            status = "Queued for collection"
            coverage = "queued"
        result.append(
            {
                **target,
                "tariffs": len(tariffs),
                "wellness_tariffs": len(wellness),
                "priced_wellness": sum(r["price"] is not None for r in wellness),
                "sources": len(source_rows),
                "branches": len(target_branches),
                "last_checked": source_rows[0]["retrieved_at"] if source_rows else "",
                "status": status,
                "coverage": coverage,
            }
        )
    if country != "LT":
        watched_domains = {host for target in watched for host in target["domains"]}
        hospitals = market.rows(
            "SELECT * FROM market_hospital WHERE country=? ORDER BY name", (country,)
        )
        for priority, hospital in enumerate(hospitals, len(result) + 1):
            if hospital["domain"] in watched_domains:
                continue
            tariffs = [r for r in prices if r["country"] == country and r["domain"] == hospital["domain"]]
            wellness = [r for r in tariffs if is_wellness_service(r)]
            source_rows = [s for s in sources if domain(s["url"]) == hospital["domain"]]
            target_branches = [b for b in branches if b["hospital_id"] == hospital["id"]]
            service_text = " ".join(r["service"] + " " + r["original_name"] for r in tariffs)
            capabilities = []
            if wellness:
                capabilities.append("iv_therapy")
            if re.search(r"longevity|anti[ -]?aging|ilgaamž", service_text, re.I):
                capabilities.append("longevity")
            if re.search(r"family|general practice|primary|perearst|ģimenes|medicină de familie", service_text, re.I):
                capabilities.append("primary_care")
            if re.search(r"diagnostic|imaging|laborator|ultrasound|radiolog", service_text, re.I):
                capabilities.append("diagnostics")
            if len({r["service"] for r in tariffs}) >= 5:
                capabilities.append("multi_specialty")
            scope = min(5, max(1, 1 + round(math.log2(max(1, len(tariffs))))))
            iv_focus = min(5, max(1, round(1 + 4 * len(wellness) / max(1, len(tariffs)))))
            segment = "IV / longevity specialist" if wellness and len(wellness) * 2 >= len(tariffs) else "Multi-specialty clinic"
            if wellness:
                status, coverage = "Wellness prices captured", "priced"
            elif tariffs:
                status, coverage = "Other services captured", "services"
            elif source_rows:
                status, coverage = "Official source found", "source"
            else:
                status, coverage = "Queued for collection", "queued"
            result.append(
                {
                    "id": hospital["id"], "name": hospital["name"], "country": country,
                    "domains": (hospital["domain"],), "segment": segment,
                    "cities": tuple(sorted({b["city"] for b in target_branches})) or ("Location pending",),
                    "positioning": "Observed competitor from collected official sources",
                    "capabilities": tuple(capabilities), "scope": scope, "iv_focus": iv_focus,
                    "urls": (hospital["source_url"],), "service_url": hospital["source_url"],
                    "active": True, "priority": priority, "origin": "observed",
                    "tariffs": len(tariffs), "wellness_tariffs": len(wellness),
                    "priced_wellness": sum(r["price"] is not None for r in wellness),
                    "sources": len(source_rows), "branches": len(target_branches),
                    "last_checked": source_rows[0]["retrieved_at"] if source_rows else "",
                    "status": status, "coverage": coverage,
                }
            )
    return result


def _empty(title, message, height=320):
    return {
        "data": [],
        "layout": _layout(
            title,
            height,
            xaxis={"visible": False},
            yaxis={"visible": False},
            annotations=[{"text": message, "showarrow": False, "font": {"color": MUTED, "size": 13}}],
        ),
    }


def landscape(country="LT", targets=None):
    rows = [
        r
        for r in (targets if targets is not None else target_snapshot(country))
        if r["active"]
    ]
    if not rows:
        return _empty("Competitive landscape", "Run discovery to build this country dashboard.", 360)
    colors = {
        "IV / longevity specialist": GREEN,
        "Multi-specialty clinic": BLUE,
    }
    short_labels = {
        "SYNC Longevity Clinic": "SYNC",
        "ID Clinic": "ID Clinic",
        "AUM Wellness Clinic": "AUM",
        "UnaVita Private Clinic": "UnaVita",
        "Unomeda Klinika": "Unomeda",
        "Bendrystės klinika": "Bendrystės",
        "Affidea Lietuva": "Affidea",
        "Privatus gydytojas": "Privatus gydytojas",
        "RVL klinika": "RVL",
    }
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["scope"], row["iv_focus"])].append(row["id"])
    coordinates = {}
    show_labels = len(rows) <= 12 and max(map(len, grouped.values()), default=0) <= 4
    label_positions = ["top left", "bottom right", "top right", "bottom left"]
    for (scope, focus), identifiers in grouped.items():
        spacing = min(0.5, 1.2 / max(1, len(identifiers) - 1))
        midpoint = (len(identifiers) - 1) / 2
        for index, identifier in enumerate(identifiers):
            x = scope + (index - midpoint) * spacing
            position = label_positions[index % len(label_positions)]
            if x >= 4.8:
                position = "top left" if index % 2 == 0 else "bottom left"
            coordinates[identifier] = (
                x,
                focus + (0.05 if index % 2 == 0 else -0.05),
                position,
            )
    traces = []
    for segment in colors:
        selected = [r for r in rows if r["segment"] == segment]
        traces.append(
            {
                "type": "scatter",
                "mode": "markers+text" if show_labels else "markers",
                "name": segment,
                "x": [coordinates[r["id"]][0] for r in selected],
                "y": [coordinates[r["id"]][1] for r in selected],
                "text": [short_labels.get(r["name"], r["name"]) for r in selected],
                "textposition": [coordinates[r["id"]][2] for r in selected],
                "textfont": {"size": 9},
                "customdata": [
                    [r["name"], r["positioning"], r["wellness_tariffs"], r["status"]]
                    for r in selected
                ],
                "marker": {
                    "color": colors[segment],
                    "size": [16 + min(18, 5 * math.log1p(r["tariffs"])) for r in selected],
                    "opacity": 0.82,
                    "line": {"color": "#ffffff", "width": 1.5},
                },
                "hovertemplate": (
                    "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>Wellness tariffs: "
                    "%{customdata[2]}<br>%{customdata[3]}<extra></extra>"
                ),
            }
        )
    return {
        "data": traces,
        "layout": _layout(
            "Competitive landscape",
            455,
            xaxis={
                "title": "Breadth of clinic offering →",
                "range": [0.35, 5.8],
                "dtick": 1,
                "gridcolor": GRID,
                "zeroline": False,
            },
            yaxis={
                "title": "IV / wellness specialisation →",
                "range": [0.5, 5.55],
                "dtick": 1,
                "gridcolor": GRID,
                "zeroline": False,
            },
            legend={"orientation": "h", "x": 0, "y": -0.31},
            margin={"l": 62, "r": 28, "t": 54, "b": 118},
        ),
    }


def capability_heatmap(country="LT", targets=None):
    rows = [
        r
        for r in (targets if targets is not None else target_snapshot(country))
        if r["active"]
    ]
    if not rows:
        return _empty("Capability coverage", "No collected competitors yet.", 300)
    keys = [key for key, _ in CAPABILITIES]
    labels = [label for _, label in CAPABILITIES]
    return {
        "data": [
            {
                "type": "heatmap",
                "x": labels,
                "y": [r["name"] for r in rows],
                "z": [[1 if key in r["capabilities"] else 0 for key in keys] for r in rows],
                "colorscale": [[0, "#edf2f4"], [1, GREEN]],
                "showscale": False,
                "xgap": 3,
                "ygap": 3,
                "hovertemplate": "%{y}<br>%{x}: %{z}<extra></extra>",
            }
        ],
        "layout": _layout(
            "Capability coverage",
            440,
            xaxis={"side": "top", "tickangle": -20},
            yaxis={"autorange": "reversed", "automargin": True},
            margin={"l": 154, "r": 18, "t": 90, "b": 20},
        ),
    }


def wellness_prices(country="LT", targets=None, prices=None):
    by_target = defaultdict(list)
    targets = [
        r
        for r in (targets if targets is not None else target_snapshot(country))
        if r["active"]
    ]
    for row in prices if prices is not None else market.latest_prices():
        if row["country"] != country or row["price"] is None or not is_wellness_service(row):
            continue
        for target in targets:
            if row["domain"] in target["domains"]:
                by_target[target["name"]].append(float(row["price"]))
                break
    names = sorted(by_target, key=lambda name: median(by_target[name]))
    if not names:
        return None
    return {
        "data": [
            {
                "type": "bar",
                "orientation": "h",
                "y": names,
                "x": [median(by_target[name]) for name in names],
                "customdata": [len(by_target[name]) for name in names],
                "marker": {"color": GREEN},
                "hovertemplate": "<b>%{y}</b><br>Median starting/exact price: €%{x:.0f}<br>Observed tariffs: %{customdata}<extra></extra>",
            }
        ],
        "layout": _layout(
            "Observed IV & wellness price position",
            max(300, 74 + 42 * len(names)),
            xaxis={"title": "Median observed EUR", "gridcolor": GRID},
            yaxis={"automargin": True},
            margin={"l": 145, "r": 24, "t": 54, "b": 48},
        ),
    }


def collection_coverage(country="LT", targets=None):
    rows = [
        r
        for r in (targets if targets is not None else target_snapshot(country))
        if r["active"]
    ]
    if not rows:
        return _empty("Collection coverage", "No competitors collected yet.", 300)
    counts = Counter(r["coverage"] for r in rows)
    labels = ["Wellness prices", "Other services", "Official source", "Queued"]
    keys = ["priced", "services", "source", "queued"]
    present = [(label, counts[key], color) for label, key, color in zip(
        labels, keys, [GREEN, BLUE, ORANGE, "#dce5e8"]
    ) if counts[key]]
    return {
        "data": [
            {
                "type": "pie",
                "labels": [row[0] for row in present],
                "values": [row[1] for row in present],
                "hole": 0.62,
                "sort": False,
                "marker": {"colors": [row[2] for row in present]},
                "textinfo": "label+value",
                "textposition": "inside",
                "insidetextorientation": "horizontal",
                "hovertemplate": "%{label}: %{value}<extra></extra>",
            }
        ],
        "layout": _layout(
            "Collection coverage",
            340,
            showlegend=False,
            margin={"l": 20, "r": 20, "t": 54, "b": 20},
        ),
    }


BUILDERS = {
    "landscape": ("Competitive landscape", landscape),
    "capabilities": ("Capability coverage", capability_heatmap),
    "wellness-prices": ("IV & wellness price position", wellness_prices),
    "collection": ("Collection coverage", collection_coverage),
}


def build_chart(name, country="LT", targets=None, prices=None):
    entry = BUILDERS.get(name)
    if not entry:
        return None
    title, builder = entry
    if name == "wellness-prices":
        figure = builder(country, targets, prices)
    else:
        figure = builder(country, targets)
    return {"name": name, "title": title, "figure": figure} if figure else None


PATTERNS = [
    ("wellness-prices", r"price|cost|cheapest|expensive|kain|eur"),
    ("capabilities", r"capabil|service mix|offer|heatmap|coverage gap"),
    ("collection", r"collect|source|crawl|scrap|monitor|data coverage|status"),
    ("landscape", r"landscape|position|compet|market map|closest|alternative"),
]


def detect_charts(message):
    text = (message or "").casefold()
    found = [name for name, pattern in PATTERNS if re.search(pattern, text)]
    if not found and re.search(r"wellness|infusion|intraven|laš|iv therap|longevity", text):
        found = ["landscape"]
    return list(dict.fromkeys(found))[:2]
