#!/usr/bin/env python3
"""Validate a snapshot JSON document and, optionally, its archive manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.archive import validate_manifest
from research.contract import ValidationError, validate_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="snapshot JSON file")
    parser.add_argument("--manifest", type=Path, help="manifest JSON file to verify")
    args = parser.parse_args(argv)
    try:
        with args.snapshot.open(encoding="utf-8") as handle:
            validate_snapshot(json.load(handle))
        if args.manifest:
            with args.manifest.open(encoding="utf-8") as handle:
                validate_manifest(args.manifest.parent, json.load(handle))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    print(f"VALID: {args.snapshot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
