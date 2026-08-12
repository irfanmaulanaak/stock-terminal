#!/usr/bin/env python3
"""Evaluate explicitly paired forecast and next-checkpoint snapshots."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.evaluation import EvaluationError, evaluate_pairs, render_json, render_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", nargs=2, action="append", required=True,
                        metavar=("FORECAST", "CHECKPOINT"), help="explicit forecast and next checkpoint paths; repeatable")
    parser.add_argument("--json-output", type=Path, help="write deterministic JSON report")
    parser.add_argument("--markdown-output", type=Path, help="write deterministic Markdown report")
    parser.add_argument("--format", choices=("json", "markdown"), default="json",
                        help="stdout format (used when no output paths are given)")
    args = parser.parse_args(argv)
    try:
        report = evaluate_pairs(args.pair)
        json_text, markdown_text = render_json(report), render_markdown(report)
        if args.json_output:
            args.json_output.write_text(json_text, encoding="utf-8")
        if args.markdown_output:
            args.markdown_output.write_text(markdown_text, encoding="utf-8")
    except (EvaluationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not args.json_output and not args.markdown_output:
        sys.stdout.write(json_text if args.format == "json" else markdown_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
