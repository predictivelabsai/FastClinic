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


def target_snapshot():
    """Combine editorial targets with observed sources, prices and branch records."""
    prices = market.latest_prices()
    sources = market.rows(
        "SELECT url,retrieved_at,status FROM market_source ORDER BY retrieved_at DESC"
    )
    branches = market_map.clinics("LT")
    from web.market_watchlist import items

    result = []
    for target in items():
        domains = set(target["domains"])
        tariffs = [r for r in prices if r["country"] == "LT" and r["domain"] in domains]
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
    return result


def landscape():
    rows = [r for r in target_snapshot() if r["active"]]
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
    label_positions = ["top left", "bottom right", "top right", "bottom left"]
    for (scope, focus), identifiers in grouped.items():
        spacing = 0.44 if len(identifiers) < 3 else 0.5
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
                "mode": "markers+text",
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
            "Lithuania competitive landscape",
            430,
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
            legend={"orientation": "h", "y": -0.18},
            margin={"l": 62, "r": 28, "t": 54, "b": 78},
        ),
    }


def capability_heatmap():
    rows = [r for r in target_snapshot() if r["active"]]
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


def wellness_prices():
    from web.market_watchlist import items

    by_target = defaultdict(list)
    targets = items(active_only=True)
    for row in market.latest_prices():
        if row["country"] != "LT" or row["price"] is None or not is_wellness_service(row):
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


def collection_coverage():
    rows = [r for r in target_snapshot() if r["active"]]
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
            "Priority competitor collection coverage",
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


def build_chart(name):
    entry = BUILDERS.get(name)
    if not entry:
        return None
    title, builder = entry
    figure = builder()
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
