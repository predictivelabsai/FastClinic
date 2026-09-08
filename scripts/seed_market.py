"""Import the reviewed public market baseline into configured operations storage.

Run: .venv/bin/python -m scripts.seed_market
Repeatable by seed ID. Never creates fabricated historical weeks.
"""

import json
from pathlib import Path
from dotenv import load_dotenv


def seed(path=None):
    from web import market, market_map

    path = Path(
        path or Path(__file__).resolve().parents[1] / "data/market/baseline.json"
    )
    if not path.exists():
        return 0
    data = json.loads(path.read_text())
    run_id = data["id"]
    with market.connect() as c:
        c.execute(
            """INSERT INTO market_run (id,status,trigger_kind,actor,created_at,finished_at,config,stats)
            VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING""",
            (
                run_id,
                "completed",
                "seed",
                "public-source-baseline",
                data["collected_at"],
                data["collected_at"],
                json.dumps(market.DEFAULT_CONFIG),
                json.dumps({"observations": len(data["observations"]), "seed": True}),
            ),
        )
        c.commit()
    market.ingest(run_id, data["observations"])
    hospitals = {h["id"]: h for h in market.rows("SELECT * FROM market_hospital")}
    for loc in data.get("clinics", []):
        h = hospitals[loc["hospital_id"]]
        market_map.save_clinics(h, [loc])
        if loc.get("geocode_status") == "located":
            with market_map.connect() as c:
                c.execute(
                    "UPDATE market_clinic SET latitude=?,longitude=?,geocode_status=?,geocode_source=?,geocoded_at=? WHERE id=?",
                    (
                        loc["latitude"],
                        loc["longitude"],
                        "located",
                        loc["geocode_source"],
                        loc["geocoded_at"],
                        loc["id"],
                    ),
                )
                c.commit()
    return len(data["observations"])


if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    print(f"Imported {seed()} source-backed market observations (repeatable baseline).")
