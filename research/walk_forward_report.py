#!/usr/bin/env python3
"""Run a deterministic Phase 9 walk-forward evaluation from JSON config."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.walk_forward import BUILT_IN_PREDICTORS, WalkForwardError, evaluate_walk_forward


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="JSON config (stdin when omitted or '-')")
    parser.add_argument("--output", type=Path, help="write report instead of stdout")
    args = parser.parse_args()
    try:
        if args.input is None or str(args.input) == "-":
            document = json.load(sys.stdin)
        else:
            with args.input.open(encoding="utf-8") as handle:
                document = json.load(handle)
        if not isinstance(document, dict) or not isinstance(document.get("rows"), list):
            raise WalkForwardError("config must contain a rows array")
        predictor = document.get("predictor", {"name": "always_flat"})
        if not isinstance(predictor, dict) or predictor.get("name", predictor.get("type")) not in BUILT_IN_PREDICTORS:
            raise WalkForwardError(f"predictor must be one of {BUILT_IN_PREDICTORS}")
        fold_config = document.get("folds", document.get("walk_forward"))
        if not isinstance(fold_config, dict):
            raise WalkForwardError("config must contain a folds object")
        report = evaluate_walk_forward(document["rows"], predictor, **fold_config)
        rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Walk-forward report error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
