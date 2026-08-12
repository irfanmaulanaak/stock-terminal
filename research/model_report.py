#!/usr/bin/env python3
"""Run a deterministic Phase 11 model comparison from JSON config."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.models import compare_models
from research.walk_forward import WalkForwardError


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
        report = compare_models(document["rows"], document.get("models"),
                                folds=document.get("folds"),
                                splits=document.get("splits", ("test",)))
        rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Model report error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
