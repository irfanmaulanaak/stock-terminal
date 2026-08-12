#!/usr/bin/env python3
"""Print a deterministic Phase 14 operations health report."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.operations import operations_health


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast", type=Path)
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--archive-dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--now", type=datetime.fromisoformat, help="timezone-aware ISO-8601 time")
    parser.add_argument("--forecast-max-age", type=int, default=18 * 60 * 60)
    parser.add_argument("--verification-max-age", type=int, default=48 * 60 * 60)
    parser.add_argument("--quote-max-age", type=int, default=15 * 60)
    args = parser.parse_args(argv)
    try:
        report = operations_health(forecast_path=args.forecast, verification_path=args.verification,
            archive_dir=args.archive_dir, manifest_path=args.manifest, now=args.now,
            forecast_max_age_seconds=args.forecast_max_age, verification_max_age_seconds=args.verification_max_age,
            quote_max_age_seconds=args.quote_max_age)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 1 if report["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
