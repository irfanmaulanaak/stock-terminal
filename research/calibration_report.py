#!/usr/bin/env python3
"""Run a deterministic Phase 12 walk-forward calibration report from JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.calibration import calibrate_walk_forward
from research.walk_forward import WalkForwardError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="JSON config (stdin when omitted or '-')")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        with (args.input.open(encoding="utf-8") if args.input and str(args.input) != "-" else sys.stdin) as handle:
            document = json.load(handle)
        if not isinstance(document, dict) or not isinstance(document.get("rows"), list):
            raise WalkForwardError("config must contain a rows array")
        source = document.get("probability_source", document.get("model"))
        folds = document.get("folds")
        if not isinstance(source, dict) or not isinstance(folds, dict):
            raise WalkForwardError("config must contain probability_source and folds objects")
        report = calibrate_walk_forward(document["rows"], source,
                                        calibrator_config=document.get("calibrator"),
                                        bins=document.get("bins", 10), **folds)
        rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Calibration report error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
