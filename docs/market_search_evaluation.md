# Baltic clinic search evaluation — 8 September 2026

Exa is the sole enabled production search provider. Tavily remains an isolated adapter for the original comparison tests; it is not selectable in the application and no fallback calls it.

## What was measured

The same two broad queries per country (one local-language, one English) were sent to each provider, asking for eight results per query: 48 results per provider, 96 total. These are a small convenience sample, not a census or an independent estimate of national recall. Search indexes, ranking, dates and prompts can change the outcome.

We manually labelled whether each returned URL was a provider-owned service/price candidate, excluding public hospital pages, directories, intermediaries, general articles and unrelated results. This is relevance screening, **not independently verified private-ownership precision**. Per-result URLs, timestamps, query text and labels are in `tests/fixtures/market_search_coverage.json`.

| Provider | Estonia candidates / results | Latvia | Lithuania | Total | Distinct candidate domains |
|---|---:|---:|---:|---:|---:|
| Exa | 16 / 16 | 11 / 16 | 13 / 16 | 40 / 48 (83.3%) | 33 |
| Tavily | 6 / 16 | 1 / 16 | 3 / 16 | 10 / 48 (20.8%) | 8 |

Exa found many directly usable price-list pages. Broad Tavily searches often returned public hospital tariffs or healthcare explainers; one Estonia result was Telia's unrelated price list. Tavily's short or empty page extracts also limited usable evidence. This does not establish that Tavily would lose with tuned, domain-targeted queries.

## Price extraction accuracy

Search relevance is not price accuracy. An LLM then proposed structured services and prices from returned text. Local checks require literal ownership/service evidence, numeric price agreement, an official provider domain, one of the three countries, and exclusion of referral/subsidy fees. When necessary, Exa searches official about pages for ownership evidence.

Manual inspection exposed material errors in the first extraction: a referral-based fee was treated as self-pay, slash-separated alternatives were called ranges, and per-unit prices could lose their unit. These now have deterministic rejection or unavailable-price handling and regression fixtures. An apparent private company legal form alone is insufficient ownership evidence. Cancellation fees are also excluded.

`tests/fixtures/market_prices.json` contains 17 reviewed source-text cases across four clinics and all three countries. Sixteen have supported service-price/type pairs; one intentionally ambiguous alternative tariff must remain unavailable. The regression test requires all 17 expected outcomes. This checks the extraction validator on a small reviewed set; **it is not a claim of 100% accuracy on all collected prices**. Currency, qualifiers, stale web content, complex tables and omitted services remain limitations. No independent full service inventory was available, so treatment-level recall is unknown.

Initial source-backed baseline: 211 service/tariff observations at four clinic providers in **three countries**, before location enrichment. The baseline includes exact, from, range and unavailable prices; it is deliberately much smaller than the candidate list because uncertain private ownership and ambiguous prices are not silently accepted. Historical weekly changes are unavailable until subsequent real observations exist.

## Honest recommendation

Use Exa for this first version. Its broad search relevance was substantially better in this sample, and it supplies useful price-list content. Treat the product as an accumulating, evidence-linked competitor monitor, not a complete or guaranteed-current price catalogue. Keep regular self-pay prices separated by price type, show sources and collection dates, and preserve uncertainty. Do not use a single lowest number for decision-making without checking the linked tariff conditions.

## Reproduction

Offline:

```bash
.venv/bin/python -m pytest tests/test_llm_search.py tests/test_market.py tests/test_market_map.py -q
```

Paid Exa connectivity/coverage checks (three countries, eight results each):

```bash
MARKET_LIVE_TESTS=1 .venv/bin/python -m pytest tests/test_llm_search.py -m live_search -s
```

The live test records result count, distinct domains, text availability, URLs and timestamps under `data/market/live-tests/`. It does not assert that every result is a private clinic or has an accurate price. The run on 8 September returned eight results with text for each country; distinct domains were Lithuania 8, Latvia 8 and Estonia 6.

Provider references: [Exa Search](https://exa.ai/docs/reference/search), [Exa Contents](https://exa.ai/docs/reference/get-contents), [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search).
