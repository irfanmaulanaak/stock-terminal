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
