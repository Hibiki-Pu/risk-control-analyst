# Market data sources

The Market Data Adapter (`services/api/app/market/`) is the only way market data
enters the product. Two hard rules:

1. **Fixture mode is always visible.** Without `FRED_API_KEY` (or when FRED cannot
   be reached) the adapter serves the local fixture set and every response carries
   `is_fixture: true`, `source_name: "Local demo fixture"` and a note in
   `license_note`. It never presents a fixture as a live observation.
2. **No blind alignment.** Series keep their native frequency. Nothing is
   forward-filled across frequencies; `alignment_note` states this on every
   response and the UI shows the latest observation date next to the value.

## Supported series

| series_id | Title | Units | Frequency | Country | Why it is used |
| --- | --- | --- | --- | --- | --- |
| `DFF` | Federal Funds Effective Rate | Percent | daily | US | Benchmark for the floating-rate part of group debt; drives `RC-14` and the interest-rate sensitivity. |
| `DGS10` | 10-Year Treasury Constant Maturity Rate | Percent | daily | US | Long-end reference for refinancing discussions. |
| `CPIAUCSL` | Consumer Price Index (All Urban Consumers) | Index 1982-1984=100 | monthly | US | Demand-side price environment for pricing-power discussions. |
| `PPIACO` | Producer Price Index, All Commodities | Index 1982=100 | monthly | US | Input-cost proxy behind the material-cost driver. |
| `DTWEXBGS` | Nominal Broad U.S. Dollar Index | Index Jan 2006=100 | daily | US | Broad USD strength; moves the translated value of non-USD revenue. |
| `DEXTHUS` | Thai Baht to One U.S. Dollar | THB per USD | daily | TH | Translation exposure of the Thailand business. |
| `DEXSIUS` | Singapore Dollars to One U.S. Dollar | SGD per USD | daily | SG | Translation exposure of the Singapore business and HQ cost base. |

Source: **FRED, Federal Reserve Bank of St. Louis** —
`https://fred.stlouisfed.org/series/<series_id>`. FRED terms of use apply to the
metadata and to any live observation.

There is **no** series for the Vietnamese dong in the catalogue: the VND leg of
the demo is an internal assumption, not a market quote. Stating this is cheaper
than inventing a source.

## Live mode

```bash
# .env   (never commit a real key)
FRED_API_KEY=<your-free-key>    # https://fredaccount.stlouisfed.org/apikeys
FRED_BASE_URL=https://api.stlouisfed.org/fred
FRED_TIMEOUT_SECONDS=8
FRED_MAX_RETRIES=2
FRED_CACHE_TTL_SECONDS=3600
FRED_MIN_REQUEST_INTERVAL_SECONDS=0.5
```

Behaviour:

* `GET {base}/series/observations?series_id=…&file_type=json&sort_order=desc&limit=N`
* **Cache:** `<runtime>/market_cache/<series_id>.json` with `fetched_at`; a fresh
  entry (< TTL) is served without a network call. A corrupt cache file is ignored
  rather than fatal.
* **Timeout:** `FRED_TIMEOUT_SECONDS` per request.
* **Retry:** up to `FRED_MAX_RETRIES` additional attempts with exponential backoff
  (0.5s, 1s, 2s, capped at 4s) on network errors and 5xx responses. A 4xx is not
  retried.
* **Rate limit:** a minimum interval of `FRED_MIN_REQUEST_INTERVAL_SECONDS`
  between calls to the FRED host.
* **Failure:** the adapter falls back to the fixture set and sets `error` to
  `"Live FRED request failed (<ExceptionType>: <message>). Serving the local demo
  fixture instead — these are NOT live values."` The UI shows that text.
* **Staleness:** a live series whose latest observation is older than
  `RCA_STALE_MARKET_DATA_DAYS` (default 120) is flagged `is_stale: true`; fixtures
  are never marked stale because they are not live data to begin with.

Missing observations in a FRED payload (`"."`) are stored as `value: null` and
excluded from `latest_value`, `previous_value` and `change`.

## How market data is used

* **`RC-14`** compares the latest policy rate with the value twelve months earlier.
  When the series is a fixture the signal text says so explicitly.
* **Report section 4** prints the latest value, observation date, frequency and
  provenance for every requested series, and the pre-export verification adds a
  `V-07` warning whenever a fixture was used.
* **Scenario sensitivities** are model outputs, not market quotes; they are cited
  as `model:driver-based-forecast@v1`.
* The **AI analyst** can only read the market series through the
  `get_market_series` tool, and any fixture value it quotes is labelled as a demo
  fixture in the same finding.

## SEC EDGAR — designed interface, deliberately not used in v1

The brief asks for the EDGAR interface to be **designed without forcing a first
release integration**. It is implemented that way:

* `services/api/app/market/edgar.py` defines the data contract (`EdgarFiling`,
  `EdgarFact`), the endpoints and the access policy.
* **Nothing is fetched.** `IMPLEMENTED = False`, every method raises
  `EdgarNotEnabled` with a message pointing at this document, and
  `EdgarMisconfigured` guards the missing-User-Agent case for the future
  implementation.
* `GET /api/v1/market/edgar/status` publishes the design, so a reviewer can check
  it without reading the source, and no caller can mistake an unfinished
  integration for data.
* The connector is **not** exposed as an agent tool, so the AI analyst cannot
  reach it either.

| Designed endpoint | Purpose |
| --- | --- |
| `GET https://www.sec.gov/files/company_tickers.json` | Ticker → zero-padded CIK resolution (never guessed) |
| `GET https://data.sec.gov/submissions/CIK{cik:010d}.json` | Entity data + recent filing index (up to 1000 filings) |
| `GET https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json` | One XBRL concept as a time series (preferred: small payload) |
| `GET https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json` | All XBRL facts (large; needs a size guard) |
| `GET https://www.sec.gov/cgi-bin/browse-edgar?...type={form}&output=atom` | Filing index as Atom, for filings the JSON index misses |

Access policy the implementation must honour: a descriptive `User-Agent` with
contact details on every request, fewer than 10 requests per second
(`EDGAR_MIN_REQUEST_INTERVAL_SECONDS=0.2` → 5/s), aggressive caching
(`EDGAR_CACHE_TTL_SECONDS=86400`), an absent tag reported as `missing` rather
than zero, and full attribution (accession number, filing date, source URL) in
the UI and in the report exactly as the FRED adapter does today.

Work item: `docs/roadmap.md` P2-1.
