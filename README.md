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

Each snapshot is a one-checkpoint-ahead forecast: close 16:01 → next open 09:01, open 09:01 → break 12:01, and break 12:01 → close 16:01. The verifier compares the forecast baseline to the next checkpoint baseline, reports 3-way/directional accuracy, UP precision/recall, target MAE, confusion matrices, and whether re-analysis improved the next transition.
