# Stock Analytics Dashboard

A small, read-only Vite + React + TypeScript dashboard for an Indonesian `.JK` watchlist and a four-position portfolio. Hermes refreshes the stable forecast snapshot at `/opt/data/watchlist_forecast_latest.json` three times on IDX weekdays (09:01, 12:01, and 16:01 WIB). The native Node server reads that latest snapshot, optionally reads a verification report, and proxies live Yahoo Finance chart quotes so the browser does not need external API access.

## Run on a host

From this directory:

```sh
npm install
npm run build
npm start
```

The server binds to `0.0.0.0:4173`. Open `http://localhost:4173` locally or `http://<host-address>:4173` from another machine. The forecast file must exist at `/opt/data/watchlist_forecast_latest.json` unless `FORECAST_FILE` is set. An optional report is detected at `/opt/data/watchlist_verification_2026-08-12.md` or the corresponding `.json` path; set `VERIFICATION_FILE` to use another mounted report.

For frontend development, run the API on port 4174 and Vite on port 5173 in separate terminals:

```sh
PORT=4174 npm run api
npm run dev
```

## Docker

Build and run with the forecast mounted read-only:

```sh
docker build -t stock-analytics-dashboard .
docker run --rm --name stock-analytics-dashboard -p 4173:4173 \
  -v /opt/data/watchlist_forecast_latest.json:/opt/data/watchlist_forecast_latest.json:ro \
  -v /opt/data/watchlist_verification_2026-08-12.md:/opt/data/watchlist_verification_2026-08-12.md:ro \
  stock-analytics-dashboard
```

The second volume is optional; omit it when the verification report has not been generated. The container exposes the same host URL, `http://localhost:4173`.

## API

- `GET /api/health` — local service check.
- `GET /api/dashboard` — forecast data plus normalized optional verification metrics.
- `GET /api/quotes` — read-only quotes for every forecast symbol using Yahoo Finance's chart endpoint. Pass `?symbols=BBCA,BNBR,ELTY,PRDL` to request valid IDX tickers outside the forecast universe; the optional `.JK` suffix is accepted. Malformed symbols are rejected with HTTP 400. Results are briefly cached per symbol to avoid unnecessary refresh bursts.
- `GET /api/chart?symbol=BBCA&range=3mo&interval=1d` — normalized OHLCV history for the expandable chart. Supported ranges are `1d`, `5d`, `1mo`, `3mo`, and `1y`; supported intervals are `5m`, `15m`, `1h`, and `1d`. Ticker, range, and interval values are strictly validated and the response includes Yahoo source and fetch metadata.
- `GET /api/research?symbol=BBCA` — runtime-only research context for one strictly validated IDX ticker. It normalizes company headlines discovered through Google News RSS plus Indonesia/global market context from public Yahoo Finance chart data into four analytical layers (Global, Indonesia market, Sector, and Company). Responses include source status, fetch time, freshness, observation counts, and explicit unavailable states. Results are cached in server memory for five minutes and are never written to disk.

Research coverage is best-effort and depends on unauthenticated public endpoints that can be delayed, incomplete, rate-limited, or unavailable. Headline-derived tone is a small transparent keyword heuristic, not a recommendation, calibrated model, or substitute for primary filings. Sector context falls back to ticker-specific discovery because no durable no-key IDX classification source is assumed; when reliable observations are absent, the API labels the layer unavailable instead of generating current claims or placeholder headlines. Article links come only from the fixed server-side news discovery request; clients cannot supply an upstream URL.

Official checkpoint forecast archives are designed to preserve the sentiment inputs used at forecast time. Each stock can carry immutable `sentiment_context` for `company`, `sector`, `indonesia_market`, and `global`, plus `sentiment_conflict`, `forecast_modifier`, and `sentiment_summary`; the archive-level `market_context` records the global and Indonesia-market summaries. These curated archives remain local under `/opt/data` and must never be committed or pushed. Positive company news does not automatically override an adverse Indonesia or global market regime.

Each snapshot is a one-checkpoint-ahead forecast: close 16:01 → next trading-day open 09:01, open 09:01 → break 12:01, and break 12:01 → close 16:01. The verifier compares the forecast baseline to the next checkpoint baseline, reports 3-way/directional accuracy, UP precision/recall, target MAE, confusion matrices, and whether re-analysis improved the next transition.

## Local research core

`research/` is a Python standard-library-only contract package for immutable IDX checkpoint archives. It defines the `open`, `break`, and `close` slots and their one-checkpoint horizons, weekday/explicit-holiday calendar helpers, snapshot schema validation, atomic deterministic JSON writes, and SHA-256 archive manifests. The contract requires provenance and immutable archive metadata, archive-level Indonesia/global context, and preserved sentiment plus data-quality observations for every stock. Unknown fields remain allowed for forward-compatible producers.

The calendar helper intentionally does not embed an IDX holiday calendar: callers must pass their authoritative holiday dates. Generated data belongs outside the repository (normally under `/opt/data`); local `research/data`, `research/archives`, `research/output`, and `research/cache` paths are also ignored.

Phase 4 adds standard-library-only relative-strength research: benchmark-relative returns, market and sector breadth, explicit sector and peer comparisons, and directional volume breadth. Its CLI, `research/relative_strength_report.py`, consumes two explicitly timestamp-aligned checkpoints. Unknown sectors and missing benchmarks produce `null` values and duplicate symbols are rejected; the module never infers classifications or selects later observations.

Phase 5 adds a standard-library-only Indonesia regime report covering multi-horizon IHSG trend and volatility, breadth, foreign flow and acceleration, USD/IDR, BI-rate changes, macro-event freshness, and a transparent risk-on/neutral/risk-off score. Its CLI, `research/indonesia_regime_report.py`, requires a timezone-aware checkpoint and timestamp on every observation. Future inputs are excluded, while missing or invalid inputs remain `null` with availability metadata.

Phase 6 adds a standard-library-only global regime report for global equities, VIX, DXY, US 2-year/10-year yields, and seven explicitly named commodities. It calculates timestamp-gated multi-horizon changes and volatility and applies only explicit symbol or sector USD/risk/commodity exposures. Its CLI is `research/global_regime_report.py`; future observations are excluded and unknown sources, mappings, and sensitivities remain `null`.

Validate a checkpoint and optionally its manifest with:

```sh
python3 research/validate_snapshot.py /path/to/checkpoint.json
python3 research/validate_snapshot.py /path/to/checkpoint.json --manifest /path/to/manifest.json
python3 -m unittest research.tests.test_phase0
```
