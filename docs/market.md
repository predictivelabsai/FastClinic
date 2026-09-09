# Market intelligence

The staff navigation has **Market → Competitive Intelligence**, **Market → Watchlist Editor** and **Market → Market Map** directly after Communications. The dashboard now focuses on Lithuania's IV infusion, vitamin-drip, longevity and wellness market while retaining broader Baltic source history. This is accumulating coverage, not a complete national directory.

## Using the workspace

Competitive Intelligence is a visual-first dashboard: positioning bubbles, collection coverage, a capability heatmap and observed IV/wellness price position sit above the evidence register. The priority watchlist covers SYNC, ID Clinic, AUM, UnaVita, Unomeda, Bendrystės, Northway, Meliva, Affidea, Antėja, Privatus gydytojas and RVL. Compact controls filter each table in place instead of submitting a large page-wide filter form. “From”, range, exact and unavailable prices remain separate. Only regular self-pay prices are intended for comparison; unsupported, conditional and ambiguous tariffs are withheld or shown unavailable. Source links, evidence and collection timestamps support review.

## Discovery, curation and deep scraping

There are two inputs to one evidence pipeline:

1. Exa URL discovery searches the open web and known domains for promising clinic, service and price pages.
2. Authenticated staff curate identified competitors and up to eight official URLs per competitor in **Market → Watchlist Editor**. They can change priority, positioning, locations and competitor model, or pause future monitoring without erasing history.

Every active watchlist URL is deep-fetched directly over HTTP(S) during a normal collection run, so known URLs do not depend on search recall. **Deep scrape now** creates a watchlist-only queue item with zero Exa searches. Exa-discovered URLs are passed to the same direct deep scraper; retained Exa live-crawl content is used only when a site blocks direct retrieval. Search-discovered and manually curated pages then use the same grounded LLM extraction, source retention, append-only price history and address pipeline. Direct fetching validates public DNS targets and redirects, accepts HTML/text only, and caps responses at 2 MB.

Market Map uses locally bundled Leaflet 1.9.4 and OpenStreetMap tiles. Pan, zoom in/out and open markers to navigate to clinic prices. Each branch has its own database record with provider identity, name, street address, city, country, phone when available, official source, evidence, retrieval timestamp and geocoding status. Unknown or ambiguous addresses do not receive invented coordinates. Several providers may share a building; pins represent street-address matches, not a claim about an entrance.

The AI Assistant shows page-specific questions. On Market pages it has read-only tools for competitor prices, locations and collection status, isolated from the patient/clinical tools and clinical conversation history. It receives current clinic/country/service filters. It cannot launch searches or access credentials. Market answers can also stream deterministic Plotly chart events (landscape, capability, collection and wellness-price views) after the text answer; chart JSON is built from stored data, not authored by the model.

## Search provider and keys

**Integrations → search_provider** currently offers Exa only. Staff can save, replace, remove or test their personal Exa key. Administrators can also maintain the shared key used for scheduled work. Manual runs resolve the requesting user's saved key, then the shared saved key, then `EXA_API_KEY`. Scheduled runs never borrow a user's personal credential. Keys are encrypted with a persistent `MARKET_CREDENTIALS_KEY` (Fernet); no insecure fallback exists. Keys and ciphertext are never put into run configuration or displayed in forms. A supplied test key is not saved unless Save key is used.

Search extraction uses the configured server-side LLM (defaults to xAI, `XAI_API_KEY`, model `grok-4-1-fast-non-reasoning`). An Exa key covers search, not LLM extraction. `MARKET_LLM_BASE_URL`, `MARKET_LLM_MODEL`, and `MARKET_LLM_API_KEY` can override the extraction endpoint. The interactive assistant follows the existing application AI/BYOK configuration separately.

## Scheduling and storage

**ADMIN → Market Configuration** controls countries, hospitals, treatments, weekly collection and per-run query/page limits. Only administrators can edit it. All staff roles can view Market and request a manual search; patients cannot. Role preview permissions apply to routes and actions.

The application's background worker polls a PostgreSQL/SQLite-backed queue every 15 seconds. A shared renewable lease prevents multiple application workers from processing concurrently. Weekly collection is keyed by Monday UTC and catches up on startup after downtime. Manual Search now requests are durable, deduplicated while queued/running, and subject to a five-minute cooldown. Progress and partial/failure state remain visible; a failed run never erases old observations. Expired worker runs are marked interrupted.

Discovery, official ownership checks and extraction are bounded by configuration. Limits can defer candidates and long-page tails. Broad discovery runs alongside refreshes of known provider domains. All services found in processed content are eligible; no preselected clinical treatment catalogue limits discovery. Service names are translated while retaining original labels and qualifiers. This conservative mapping may leave semantically similar services split between labels rather than falsely merge different tariffs.

Operational tables: `market_config`, `market_run`, `market_lock`, `market_hospital`, `market_service`, `market_source`, `market_observation`, `market_clinic`, `market_geocode_cache`, `market_geocode_gate`, `search_provider_credentials`. Tables are created idempotently through the existing operations database adapter. Observations retain their original collection dates and source evidence; retrying the same seed/run cannot duplicate identical rows. Removing a configuration selection retains history.

Weekly change compares the latest observation for an identical provider, service/original tariff, price type, currency and URL in consecutive UTC weeks. Missing weeks remain gaps. No historical prices are fabricated or backdated. Current country coverage charts and service-specific price/history charts are built from the same stored observations.

## Deployment and initial data

`data/market/baseline.json` contains the source-backed initial data. The worker imports it idempotently on application startup; this can also be run explicitly:

```bash
.venv/bin/python -m scripts.seed_market
```

The seed was also imported into the configured PostgreSQL database during development. It contains 211 observations, including 201 published prices and 10 unavailable/ambiguous prices, from four providers across three countries. See the evaluation report for limitations.

Set `EXA_API_KEY`, the extraction LLM key, and a persistent `MARKET_CREDENTIALS_KEY` in deployment secrets. The local `.env` has a generated credential encryption key; propagate that same secret to any deployment sharing this database so saved keys remain decryptable. `FASTCLINIC_MARKET_WORKER_ENABLED=true` enables the worker; tests disable it. The web process must remain running for scheduled/manual jobs to progress. No separate cron service is required.

## Map service limits

Leaflet is open-source; OpenStreetMap data is open, while public tile/geocoding infrastructure has usage conditions. The map makes ordinary visible tile requests, shows attribution and does not prefetch/offline-download tiles. `MARKET_MAP_TILE_URL` and `MARKET_MAP_ATTRIBUTION` allow another provider or self-hosted tiles without a code change.

Address lookup uses a configurable Nominatim-compatible `MARKET_GEOCODER_URL`. Its default public service is subject to the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/): the implementation caches results, runs server-side only, identifies FastClinic in its User-Agent, and reserves at least 16 seconds between requests in a shared database gate (below four requests/minute). No autocomplete or browser-triggered geocoding is offered. Disable it with an empty URL or use a self-hosted/approved provider for larger recurring imports. Failed transport requests remain pending; ambiguous/empty matches are cached for review. Reusing an unchanged address does not repeat a successful lookup.

References: [Leaflet](https://leafletjs.com/), [OpenStreetMap tile policy](https://operations.osmfoundation.org/policies/tiles/), [search evaluation](market_search_evaluation.md).

## Validation on 8 September 2026

- 71 targeted/regression tests and 38 subtests passed; the three paid Exa tests were skipped in this offline run and passed separately.
- Browser checks verified five pins, zoom level 6 → 7 → 6, panning, pin-to-clinic navigation, 87 tariff rows for the selected Kotka clinic, and four matching Latvian range tariffs with a minimum of EUR 500.
- A live Market assistant question correctly returned four tariffs and Latvia using those page filters.
- All five seeded branch addresses were matched to coordinates: Kotka (Tallinn), Medex (Tallinn and Tartu), GP Clinic (Kaunas), and Puriņa klīnika (Riga).
- The legacy evaluation returned 193/195. Its remaining expectations concern `/api/v1/health` containing version `1.4.0` and `/admin/staff` containing the former `Staff` label. Neither route was changed by this feature.
- Release target: `predictivelabsai/FastClinic`, branch `main`, Coolify application `fastclinic`, canonical URL `https://fastclinic.dev`. The active GitHub push webhook targets `https://coolify.fastsme.com/webhooks/source/github/events/manual`. The configured PostgreSQL database has been prepopulated; deployment must preserve the Exa and encryption secrets described above.
