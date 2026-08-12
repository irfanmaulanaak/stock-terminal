#!/usr/bin/env python3
"""Create a deterministic Phase 5 Indonesia regime report from JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.indonesia_regime import build_indonesia_regime_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="JSON file (stdin when omitted or '-')")
    parser.add_argument("--output", type=Path, help="write report to this file instead of stdout")
    args = parser.parse_args()
    try:
        if args.input is None or str(args.input) == "-":
            document = json.load(sys.stdin)
        else:
            with args.input.open(encoding="utf-8") as handle:
                document = json.load(handle)
        report = build_indonesia_regime_report(document)
        rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"Indonesia regime report error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
