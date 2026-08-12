from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.relative_strength import (
    benchmark_relative_returns,
    build_relative_strength_report,
    cross_sectional_breadth,
    map_sectors,
    peer_relative_returns,
    sector_breadth,
    sector_returns,
    volume_breadth,
)


START = "2026-08-12T09:01:00+07:00"
END = "2026-08-12T12:01:00+07:00"


def checkpoint(as_of, rows):
    return {"as_of": as_of, "observations": [
        {"symbol": symbol, "price": price, "volume": volume, "observed_at": as_of}
        for symbol, price, volume in rows
    ]}


class RelativeStrengthTests(unittest.TestCase):
    def setUp(self):
        self.start = checkpoint(START, [("IDX", 100, 10), ("A", 100, 20), ("B", 200, 30), ("C", 50, 40)])
        self.end = checkpoint(END, [("IDX", 102, 100), ("A", 110, 300), ("B", 190, 100), ("C", 50, 200)])
        self.sectors = {"IDX": "Benchmark", "A": "Banks", "B": "Banks", "C": "Mining"}

    def test_exact_calculations(self):
        report = build_relative_strength_report(self.start, self.end, "IDX", self.sectors)
        self.assertEqual(set(report["returns"]), {"IDX", "A", "B", "C"})
        self.assertAlmostEqual(report["returns"]["IDX"], .02)
        self.assertAlmostEqual(report["returns"]["A"], .1)
        self.assertAlmostEqual(report["returns"]["B"], -.05)
        self.assertEqual(report["returns"]["C"], 0.0)
        self.assertAlmostEqual(report["benchmark_relative_returns"]["A"], .08)
        self.assertEqual(report["cross_sectional_breadth"],
                         {"advancing": 2, "declining": 1, "unchanged": 1, "available": 4, "breadth": .25})
        self.assertAlmostEqual(report["sector_returns"]["Banks"], .025)
        self.assertAlmostEqual(report["peer_relative_returns"]["A"], .15)
        self.assertAlmostEqual(report["peer_relative_returns"]["B"], -.15)
        self.assertIsNone(report["peer_relative_returns"]["C"])
        self.assertEqual(report["sector_breadth"]["Banks"]["breadth"], 0)
        self.assertEqual(report["volume_breadth"]["breadth"], 300 / 500)

    def test_individual_functions(self):
        returns = {"A": .1, "B": -.05, "C": None}
        self.assertEqual(benchmark_relative_returns(returns, "MISSING"), {"A": None, "B": None, "C": None})
        self.assertEqual(cross_sectional_breadth(returns)["breadth"], 0)
        self.assertEqual(sector_returns(returns, {"A": "X", "B": "X"})["X"], .025)
        self.assertEqual(sector_breadth(returns, {"A": "X", "B": "X"})["X"]["available"], 2)
        self.assertAlmostEqual(peer_relative_returns(returns, {"A": "X", "B": "X"})["A"], .15)
        self.assertEqual(volume_breadth(returns, {"A": 300, "B": 100})["breadth"], .5)

    def test_missing_benchmark_is_null(self):
        report = build_relative_strength_report(self.start, self.end, "NOT_PRESENT", self.sectors)
        self.assertTrue(all(value is None for value in report["benchmark_relative_returns"].values()))

    def test_unknown_sector_is_not_inferred(self):
        mapping = map_sectors(["A", "UNKNOWN"], {"A": "Banks"})
        self.assertEqual(mapping, {"A": "Banks", "UNKNOWN": None})
        report = build_relative_strength_report(self.start, self.end, "IDX", {"A": "Banks", "B": "Banks"})
        self.assertIsNone(report["sectors"]["C"])
        self.assertIsNone(report["peer_relative_returns"]["C"])
        self.assertNotIn("Mining", report["sector_returns"])

    def test_duplicate_symbols_are_rejected(self):
        duplicate = copy.deepcopy(self.start)
        duplicate["observations"].append(copy.deepcopy(duplicate["observations"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate symbol"):
            build_relative_strength_report(duplicate, self.end, "IDX", self.sectors)

    def test_misaligned_and_future_observations_cannot_leak(self):
        baseline = build_relative_strength_report(self.start, self.end, "IDX", self.sectors)
        changed = copy.deepcopy(self.end)
        changed["observations"][1].update(price=10000, observed_at="2026-08-12T12:02:00+07:00")
        result = build_relative_strength_report(self.start, changed, "IDX", self.sectors)
        self.assertIsNone(result["returns"]["A"])
        self.assertNotEqual(result["returns"]["A"], baseline["returns"]["A"])

    def test_cli(self):
        document = {"start": self.start, "end": self.end, "benchmark_symbol": "IDX", "sector_mapping": self.sectors}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            result = subprocess.run([sys.executable, "research/relative_strength_report.py", str(path)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertAlmostEqual(json.loads(result.stdout)["returns"]["A"], .1)


if __name__ == "__main__":
    unittest.main()
