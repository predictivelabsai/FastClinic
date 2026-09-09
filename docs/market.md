# Market intelligence

The staff navigation has **Market → Competitive Intelligence**, **Market → Watchlist Editor** and **Market → Market Map** directly after Communications. The country selector provides a separate dashboard for every EEA market: the EU 27 plus Iceland, Liechtenstein and Norway. Coverage combines IV infusion, vitamin-drip and longevity competitors with the broader private-clinic and hospital market. It is an accumulating, reviewable evidence base rather than a claim that every national directory is already complete.

## Using the workspace

Competitive Intelligence is a visual-first dashboard: positioning bubbles, collection coverage, a capability heatmap and observed IV/wellness price position sit above the evidence register. The priority watchlist covers SYNC, ID Clinic, AUM, UnaVita, Unomeda, Bendrystės, Northway, Meliva, Affidea, Antėja, Privatus gydytojas and RVL. Compact controls filter each table in place instead of submitting a large page-wide filter form. “From”, range, exact and unavailable prices remain separate. Only regular self-pay prices are intended for comparison; unsupported, conditional and ambiguous tariffs are withheld or shown unavailable. Source links, evidence and collection timestamps support review.

Clinic links open a focused provider drill-down with that clinic's captured branches, address evidence and tariff history; they do not repeat the aggregate dashboard. Use **‹ Back to Dashboard** to return to the provider's country view. Charts stack at narrower cockpit widths, and assistant-streamed scatter charts switch to hover labels in the narrow right rail.

## Discovery, curation and deep scraping

There are three inputs to one evidence pipeline:

1. Exa URL discovery uses 15 country-specific English/local-language queries across major cities and treatment specialties. Every returned lead is retained in the candidate queue before strict clinic, ownership, service and price extraction, so useful domains are not lost when a page lacks a grounded tariff.
2. Authenticated staff curate identified competitors and up to eight official URLs per competitor in **Market → Watchlist Editor**. They can change priority, positioning, locations and competitor model, or pause future monitoring without erasing history.
3. **Import MMG hospital seeds** reads public hospital-profile links from My Medical Gateway. These aggregator links remain unverified candidates until staff identify the provider's official public website.

Candidate states are **Discovered**, **Watchlisted**, **Verified** and **Rejected**. Promotion requires an official public provider URL and immediately queues that watchlist entry for direct deep scraping. Verification is deliberately stricter: FastClinic marks a candidate verified only after its official domain has a grounded provider record and at least one source-backed clinic branch. Rejected candidates remain available for audit and can be reopened.

The **EEA coverage and campaign queue** shows candidate, review, watchlist and verified counts for all 30 countries. **Queue all 30 EEA markets** creates an ordered, persistent campaign targeting 10 verified providers per country. The first pass contains 450 broad discovery queries (15 per country) and allows up to 900 combined discovery and ownership queries. Runs advance one country at a time through the shared worker; markets below target move to **review required** instead of being falsely labelled complete.

Every active watchlist URL is deep-fetched directly over HTTP(S) during a normal collection run, so known URLs do not depend on search recall. **Deep scrape now** creates a watchlist-only queue item with zero Exa searches. Exa-discovered URLs are passed to the same direct deep scraper; retained Exa live-crawl content is used only when a site blocks direct retrieval. Search-discovered and manually curated pages then use the same grounded LLM extraction, source retention, append-only price history and address pipeline. Direct fetching validates public DNS targets and redirects, accepts HTML/text only, and caps responses at 2 MB.

**Deep scrape all active** runs the same direct pipeline for every active curated entry. Address discovery is independent of price extraction: it starts from retained official pages and the provider homepage, follows same-domain contact/location links in European languages, and probes country-specific plus conventional contact paths. xAI structures candidate branches, but a row is stored only when its street address and city occur verbatim in the retained official page. Address-less providers are rotated through a bounded repair queue so one difficult site cannot starve the rest.

Raw clinic service labels are never replaced. A separate versioned taxonomy maps high-confidence labels into a specialty → treatment-family hierarchy. Its initial public-MMG-aligned specialties are orthopaedics, gynaecology, ENT, urology, ophthalmology, general surgery, cardiac care, and cosmetic/corrective surgery; FastClinic extensions cover wellness/longevity, diagnostics, oncology, dental, dermatology, bariatric/metabolic care, rehabilitation, primary care and mental health. Unmatched services remain valid raw observations rather than being forced into the wrong category.

Market Map uses locally bundled Leaflet 1.9.4 and OpenStreetMap tiles. Pan, zoom in/out and open markers to navigate to clinic prices. Each branch has its own database record with provider identity, name, street address, city, country, phone when available, official source, evidence, retrieval timestamp and geocoding status. Unknown or ambiguous addresses do not receive invented coordinates. Several providers may share a building; pins represent street-address matches, not a claim about an entrance.

The AI Assistant shows page-specific questions. On Market pages it has read-only tools for competitor prices, locations and collection status, isolated from the patient/clinical tools and clinical conversation history. It receives current clinic/country/service filters. It cannot launch searches or access credentials. Market answers can also stream deterministic Plotly chart events (landscape, capability, collection and wellness-price views) after the text answer; chart JSON is built from stored data, not authored by the model.

## Search provider and keys

**Integrations → search_provider** currently offers Exa only. Staff can save, replace, remove or test their personal Exa key. Administrators can also maintain the shared key used for scheduled work. Manual runs resolve the requesting user's saved key, then the shared saved key, then `EXA_API_KEY`. Scheduled runs never borrow a user's personal credential. Keys are encrypted with a persistent `MARKET_CREDENTIALS_KEY` (Fernet); no insecure fallback exists. Keys and ciphertext are never put into run configuration or displayed in forms. A supplied test key is not saved unless Save key is used.

Search extraction uses the configured server-side LLM (defaults to xAI, `XAI_API_KEY`, model `grok-4-1-fast-non-reasoning`). An Exa key covers search, not LLM extraction. `MARKET_LLM_BASE_URL`, `MARKET_LLM_MODEL`, and `MARKET_LLM_API_KEY` can override the extraction endpoint. The interactive assistant follows the existing application AI/BYOK configuration separately.

## Scheduling and storage

**ADMIN → Market Configuration** controls countries, hospitals, treatments, weekly collection and per-run query/page limits. Only administrators can edit it. All staff roles can view Market and request a manual search; patients cannot. Role preview permissions apply to routes and actions.

The application's background worker polls a PostgreSQL/SQLite-backed queue every 15 seconds. A shared renewable lease prevents multiple application workers from processing concurrently. Weekly collection is keyed by Monday UTC and catches up on startup after downtime. Manual Search now requests are durable, deduplicated while queued/running, and subject to a five-minute cooldown. Direct watchlist scrapes can queue behind a running discovery job and deduplicate an already-queued identical target, so a review action is not silently swallowed by an unrelated active run. Progress and partial/failure state remain visible; a failed run never erases old observations. Expired worker runs are marked interrupted.

Discovery, official ownership checks and extraction are bounded by configuration. Limits can defer candidates and long-page tails. Broad discovery runs alongside refreshes of known provider domains. All services found in processed content are eligible; no preselected clinical treatment catalogue limits discovery. Service names are translated while retaining original labels and qualifiers. This conservative mapping may leave semantically similar services split between labels rather than falsely merge different tariffs.

Operational tables: `market_config`, `market_run`, `market_lock`, `market_hospital`, `market_service`, `market_source`, `market_observation`, `market_clinic`, `market_geocode_cache`, `market_geocode_gate`, `market_candidate`, `market_candidate_source`, `market_country_campaign`, `market_taxonomy_node`, `market_service_taxonomy`, `market_watchlist`, and `search_provider_credentials`. Tables are created idempotently through the existing operations database adapter and initialized once per process/database instance. Observations retain their original collection dates and source evidence; retrying the same seed/run cannot duplicate identical rows. Removing a configuration selection retains history.

Weekly change compares the latest observation for an identical provider, service/original tariff, price type, currency and URL in consecutive UTC weeks. Missing weeks remain gaps. No historical prices are fabricated or backdated. Current country coverage charts and service-specific price/history charts are built from the same stored observations.

## Deployment and initial data

`data/market/baseline.json` contains the source-backed initial data. The worker imports it idempotently on application startup; this can also be run explicitly:

```bash
.venv/bin/python -m scripts.seed_market
```

The seed was also imported into the configured PostgreSQL database during development. It contains 211 observations, including 201 published prices and 10 unavailable/ambiguous prices, from four providers across three countries. See the evaluation report for limitations.

The EEA campaign can also be managed from the command line. `--dry-run` makes no database or API changes; `--import-mmg` and `--backfill` create review candidates, while `--all` queues every EEA country for the background worker:

```bash
.venv/bin/python scripts/eea_market_campaign.py --all --target 10 --dry-run
.venv/bin/python scripts/eea_market_campaign.py --backfill --import-mmg
.venv/bin/python scripts/eea_market_campaign.py --all --target 10
```

Set `EXA_API_KEY`, the extraction LLM key, and a persistent `MARKET_CREDENTIALS_KEY` in deployment secrets. The local `.env` has a generated credential encryption key; propagate that same secret to any deployment sharing this database so saved keys remain decryptable. `FASTCLINIC_MARKET_WORKER_ENABLED=true` enables the worker; tests disable it. The web process must remain running for scheduled/manual jobs to progress. No separate cron service is required.

## Map service limits

Leaflet is open-source; OpenStreetMap data is open, while public tile/geocoding infrastructure has usage conditions. The map makes ordinary visible tile requests, shows attribution and does not prefetch/offline-download tiles. `MARKET_MAP_TILE_URL` and `MARKET_MAP_ATTRIBUTION` allow another provider or self-hosted tiles without a code change.

Address lookup uses a configurable Nominatim-compatible `MARKET_GEOCODER_URL`. Its default public service is subject to the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/): the implementation caches results, runs server-side only, identifies FastClinic in its User-Agent, and reserves at least 16 seconds between requests in a shared database gate (below four requests/minute). No autocomplete or browser-triggered geocoding is offered. Disable it with an empty URL or use a self-hosted/approved provider for larger recurring imports. Failed transport requests remain pending; ambiguous/empty matches are cached for review. Reusing an unchanged address does not repeat a successful lookup.

References: [European Economic Area](https://www.efta.int/eea), [Exa Search API](https://exa.ai/docs/reference/search), [My Medical Gateway hospital catalogue](https://www.mymedicalgateway.com/hospitals), [Leaflet](https://leafletjs.com/), [OpenStreetMap tile policy](https://operations.osmfoundation.org/policies/tiles/), [search evaluation](market_search_evaluation.md).

## Validation on 8 September 2026

- 71 targeted/regression tests and 38 subtests passed; the three paid Exa tests were skipped in this offline run and passed separately.
- Browser checks verified five pins, zoom level 6 → 7 → 6, panning, pin-to-clinic navigation, 87 tariff rows for the selected Kotka clinic, and four matching Latvian range tariffs with a minimum of EUR 500.
- A live Market assistant question correctly returned four tariffs and Latvia using those page filters.
- All five seeded branch addresses were matched to coordinates: Kotka (Tallinn), Medex (Tallinn and Tartu), GP Clinic (Kaunas), and Puriņa klīnika (Riga).
- The legacy evaluation returned 193/195. Its remaining expectations concern `/api/v1/health` containing version `1.4.0` and `/admin/staff` containing the former `Staff` label. Neither route was changed by this feature.
- Release target: `predictivelabsai/FastClinic`, branch `main`, Coolify application `fastclinic`, canonical URL `https://fastclinic.dev`. The active GitHub push webhook targets `https://coolify.fastsme.com/webhooks/source/github/events/manual`. The configured PostgreSQL database has been prepopulated; deployment must preserve the Exa and encryption secrets described above.
