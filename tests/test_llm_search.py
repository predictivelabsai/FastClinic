"""Search accuracy/coverage checks. Live Exa checks are opt-in and spend API credits.

MARKET_LIVE_TESTS=1 .venv/bin/python -m pytest tests/test_llm_search.py -m live_search -s
Raw comparison evidence and its limitations are documented in docs/market_search_evaluation.md.
"""

import json
import os
from pathlib import Path

import pytest
from web import market_search as search


@pytest.mark.parametrize("provider", ["exa", "tavily"])
def test_search_normalizes_sources_and_timestamps(monkeypatch, provider):
    calls = []

    def post(url, key, payload, header="Authorization"):
        calls.append((url, payload))
        return {
            "results": [
                {
                    "url": "https://clinic.example/prices#fees",
                    "title": "Prices",
                    "text": "Consultation 90 EUR",
                    "raw_content": "Consultation 90 EUR",
                    "publishedDate": "2026-01-01",
                },
                {"url": "javascript:alert(1)", "text": "invalid"},
            ]
        }

    monkeypatch.setattr(search, "_post", post)
    rows = search.search(provider, "private clinic prices", limit=8)
    assert len(rows) == 1
    assert rows[0]["url"] == "https://clinic.example/prices"
    assert rows[0]["provider"] == provider
    assert rows[0]["published_at"] == "2026-01-01"
    assert rows[0]["retrieved_at"].endswith("+00:00")
    assert rows[0]["text"] == "Consultation 90 EUR"
    assert calls[0][1]["query"] == "private clinic prices"


def sample():
    r = {
        "text": "Private clinic in Estonia. Consultation 90,00 EUR. Surgery from 1 200 EUR.",
        "url": "https://clinic.example/prices",
        "provider": "exa",
        "retrieved_at": "2026-09-08T10:00:00+00:00",
    }
    d = {
        "clinic": {
            "name": "Clinic",
            "country": "EE",
            "ownership": "private",
            "official_source": True,
            "evidence": "Private clinic in Estonia.",
        },
        "services": [
            {
                "name": "Consultation",
                "original_name": "Consultation",
                "price": "90.00",
                "price_type": "exact",
                "currency": "EUR",
                "evidence": "Consultation 90,00 EUR.",
            }
        ],
    }
    return r, d


def test_prices_require_literal_source_evidence_and_numeric_match():
    r, d = sample()
    assert search.grounded_rows(r, d)[0]["price"] == "90.00"
    d["services"][0]["price"] = "900"
    assert search.grounded_rows(r, d) == []
    d["services"][0]["price"] = "90"
    d["services"][0]["evidence"] = "Consultation 90 EUR."
    assert search.grounded_rows(r, d) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("ownership", "public"),
        ("ownership", "unknown"),
        ("official_source", False),
        ("country", "UK"),
        ("evidence", "Invented evidence"),
    ],
)
def test_public_unknown_wrong_country_and_aggregators_are_rejected(field, value):
    r, d = sample()
    d["clinic"][field] = value
    assert search.grounded_rows(r, d) == []


def test_missing_prices_are_not_zero_and_ranges_need_both_bounds():
    r, d = sample()
    d["services"][0].update(price_type="unavailable", price=None)
    assert search.grounded_rows(r, d)[0]["price"] is None
    d["services"][0].update(price_type="range", price="90", price_max="100")
    assert search.grounded_rows(r, d) == []


def test_referral_fees_are_excluded():
    r, d = sample()
    r["text"] += " Esmane visiit saatekirjaga 20 EUR"
    d["services"] = [
        dict(
            name="Initial visit",
            original_name="Esmane visiit saatekirjaga",
            price="20",
            price_type="exact",
            currency="EUR",
            evidence="Esmane visiit saatekirjaga 20 EUR",
        )
    ]
    assert search.grounded_rows(r, d) == []


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "http://127.0.0.1/a",
        "http://localhost/a",
        "https://user:pass@clinic.example/a",
        "file:///etc/passwd",
    ],
)
def test_unsafe_source_urls(url):
    assert search.safe_url(url) == ""


@pytest.mark.live_search
@pytest.mark.parametrize("country", list(search.COUNTRIES))
def test_live_exa_search_coverage(country):
    if os.getenv("MARKET_LIVE_TESTS") != "1":
        pytest.skip("Set MARKET_LIVE_TESTS=1 to spend Exa credits")
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    assert os.getenv("EXA_API_KEY"), "EXA_API_KEY is required for live evaluation"
    results = search.search("exa", search.QUERIES[country][0])
    assert results
    assert all(
        r["url"] and r["retrieved_at"] and r["provider"] == "exa" for r in results
    )
    report = {
        "country": country,
        "queries": 1,
        "results": len(results),
        "unique_domains": len({search.domain(r["url"]) for r in results}),
        "results_with_text": sum(bool(r["text"]) for r in results),
        "sources": results,
    }
    output = Path(os.getenv("MARKET_EVAL_DIR", "data/market/live-tests"))
    output.mkdir(parents=True, exist_ok=True)
    (output / f"exa_{country}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    print({k: v for k, v in report.items() if k != "sources"})


def test_reviewed_price_fixture_matches_source():
    path = Path(__file__).parent / "fixtures/market_prices.json"
    if not path.exists():
        pytest.fail("Reviewed price fixture missing")
    fixture = json.loads(path.read_text())
    for case in fixture:
        result = search.grounded_rows(case["source"], case["extraction"])
        assert [(r["original_name"], r["price"], r["price_type"]) for r in result] == [
            tuple(x) for x in case["expected"]
        ]


def test_matched_search_benchmark_reports_reviewed_candidate_coverage():
    rows = json.loads(
        (Path(__file__).parent / "fixtures/market_search_coverage.json").read_text()
    )
    metrics = {}
    for provider in ("exa", "tavily"):
        selected = [r for r in rows if r["provider"] == provider]
        assert len(selected) == 48
        # This frozen matched-provider benchmark is intentionally Baltic-only;
        # new live country coverage has its own parametrized smoke evaluation.
        assert {r["country"] for r in selected} == {"EE", "LT", "LV"}
        hits = [r for r in selected if r["provider_page_candidate"]]
        metrics[provider] = {
            "candidate_results": len(hits),
            "results": len(selected),
            "candidate_domains": len({search.domain(r["url"]) for r in hits}),
        }
    assert {r["query"] for r in rows if r["provider"] == "exa"} == {
        r["query"] for r in rows if r["provider"] == "tavily"
    }
    print("Reviewed candidate-page relevance, not national recall:", metrics)
