#!/usr/bin/env python3
"""Seed candidates and queue bounded Exa discovery across EEA markets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from web import market_candidates  # noqa: E402
from web.market_countries import CAMPAIGN_ORDER, COUNTRIES, discovery_queries  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", action="append", choices=COUNTRIES)
    parser.add_argument("--all", action="store_true", help="queue every EEA country")
    parser.add_argument("--target", type=int, default=10)
    parser.add_argument("--actor", default="eea-campaign")
    parser.add_argument("--import-mmg", action="store_true")
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    countries = list(CAMPAIGN_ORDER) if args.all else list(args.country or [])
    if not countries and not (args.import_mmg or args.backfill):
        parser.error("choose --all, --country, --import-mmg or --backfill")
    target = max(1, min(100, args.target))
    plan = {
        "countries": countries,
        "country_count": len(countries),
        "target_per_country": target,
        "discovery_queries": sum(len(discovery_queries(code)) for code in countries),
        "maximum_search_and_ownership_queries": 30 * len(countries),
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    output = {"plan": plan}
    if args.backfill:
        output["backfill"] = market_candidates.backfill_market_sources()
    if args.import_mmg:
        output["mmg"] = market_candidates.import_mmg()
    if countries:
        output["queued"] = market_candidates.queue_campaign(countries, args.actor, target)
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
