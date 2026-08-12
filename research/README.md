# Local research core

This directory contains versioned, stdlib-only contracts and deterministic tools for the IDX forecast experiment. It is application code only: generated forecasts, raw research observations, manifests, and verification outputs stay under `/opt/data` and are excluded from Git.

## Phase 0 contract

A checkpoint snapshot must preserve:

- immutable archive metadata: schema version, snapshot ID, trading date, slot, horizon, timezone, source, and immutability flag;
- archive-level Indonesia and global market context;
- per-stock symbol, four sentiment-layer summaries, conflict flag, named forecast modifier, and sentiment summary;
- per-stock data-quality status, issue list, and timezone-aware observation timestamp.

Supported slots are `open`, `break`, and `close` at the 09:01, 12:01, and 16:01 WIB checkpoints. The calendar helper intentionally accepts an explicit holiday set; it does not pretend that weekdays alone are a complete IDX trading calendar.

## Validate a snapshot

```sh
python3 research/validate_snapshot.py /path/to/snapshot.json
python3 -m unittest discover -s research/tests -v
```

`research.archive.atomic_write_json` writes deterministic JSON through a temporary file, fsync, and atomic replacement. `generate_manifest` and `validate_manifest` provide SHA-256 integrity checks for a local archive directory without storing generated archives in the repository.

## Phase 1 evaluation

`research.evaluation` evaluates one-checkpoint-ahead forecasts using only Python's standard library. It accepts Phase 0 snapshots (slot and snapshot ID under `archive_metadata`) and legacy dashboard snapshots (`snapshot_slot`, `as_of`, `actual_threshold_pct`). Both formats use the dashboard stock fields `symbol`, `baseline`, `forecast`, and `target_return_pct`. The forecast snapshot's threshold classifies realized returns strictly above the threshold as `UP`, strictly below its negative as `DOWN`, and boundary/in-range values as `FLAT`.

Pairs are always explicit. The evaluator never guesses a counterpart from filenames or dates, and it verifies the slot transitions `open → break`, `break → close`, and `close → next open`. Symbols absent from the checkpoint remain pending and reduce coverage; malformed matched observations are listed as invalid. The optional market-direction baseline is reported only when both snapshots contain the same benchmark symbol and usable baseline prices.

```sh
python3 research/evaluate_snapshots.py \
  --pair /path/open.json /path/break.json \
  --pair /path/break.json /path/close.json \
  --json-output /path/evaluation.json \
  --markdown-output /path/evaluation.md
```

With no output path, deterministic JSON is written to stdout; pass `--format markdown` for Markdown. Reports include accuracy, balanced accuracy, macro-F1, per-class precision/recall, UP precision/recall, target MAE in percentage points, confusion matrix, coverage, observation details, always-FLAT metrics, and market-direction metrics when available. No wall-clock timestamp is embedded, and ordering follows the explicit pair order with symbols sorted inside each pair.

## Phase 2 data quality

`research.data_quality` normalizes quote and OHLCV observations, measures quote age and bar delay, and reports liquidity and market-event warnings with a deterministic `ok`, `partial`, or `unavailable` status. Callers provide `as_of`; the module never reads the wall clock. Input timestamps may be timezone-aware ISO-8601 strings or Unix seconds/milliseconds.

The CLI accepts either one `{as_of, quote, bars}` object or `{as_of, observations: [{symbol, quote, bars}]}` and writes sorted JSON:

```sh
python3 research/quality_report.py /path/to/observations.json
python3 research/quality_report.py - --output /path/to/report.json
```

## Phase 3 features

`research.features` builds deterministic checkpoint feature vectors from canonical OHLCV bars and a checkpoint quote. It includes configurable multi-horizon decimal returns; opening gap; normalized range and rolling return volatility; ATR-like average true range; close location; distance to rolling highs and lows; five-bar momentum and one-bar reversal; volume ratio; turnover; and price/volume interaction.

All calculations are trailing-only. Bars are normalized and sorted, and any bar later than the quote timestamp is excluded. A rolling value is `null` until its entire history window is present; the builder never shortens a requested window. Volatility is population standard deviation, ATR-like range is normalized by the latest completed close, and quote volume is compared with the positive-volume completed-bar average.

The CLI accepts either `{quote, bars}` or `{observations: [{symbol, quote, bars}]}`. Optional top-level `return_horizons`, `rolling_windows`, and `atr_window` values override the defaults:

```sh
python3 research/features_report.py /path/to/observations.json
python3 research/features_report.py - --output /path/to/features.json
```
