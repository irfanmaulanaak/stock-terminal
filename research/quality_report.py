#!/usr/bin/env python3
"""Create deterministic Phase 2 data-quality reports from JSON input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.data_quality import assess_data_quality


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
        if not isinstance(document, dict):
            raise ValueError("input root must be an object")
        common = {key: document[key] for key in ("stale_after_seconds", "thin_volume_ratio", "limit_move_percent") if key in document}
        if "observations" in document:
            if not isinstance(document["observations"], list):
                raise ValueError("observations must be an array")
            report = {"as_of": document.get("as_of"), "observations": [
                {"symbol": item.get("symbol"), "data_quality": assess_data_quality(item.get("quote"), item.get("bars"), document.get("as_of"), **common)}
                for item in document["observations"] if isinstance(item, dict)
            ]}
        else:
            report = assess_data_quality(document.get("quote"), document.get("bars"), document.get("as_of"), **common)
        rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"quality report error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
