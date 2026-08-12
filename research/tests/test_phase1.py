from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.evaluation import EvaluationError, classify, evaluate_pairs, render_json, render_markdown


def snapshot(slot, prices, forecasts=None, *, legacy=False, benchmark=1000.0, threshold=1.0):
    forecasts = forecasts or {}
    stocks = []
    for symbol, price in prices.items():
        stock = {"symbol": symbol, "baseline": price}
        if symbol in forecasts:
            stock.update(forecasts[symbol])
        stocks.append(stock)
    if legacy:
        names = {"open": "open_0901_wib", "break": "break_1201_wib", "close": "close_1601_wib"}
        return {
            "as_of": f"legacy-{slot}", "snapshot_slot": names[slot], "actual_threshold_pct": threshold,
            "benchmark": {"symbol": "^JKSE", "baseline": benchmark}, "stocks": stocks,
        }
    horizons = {"open": "open_to_break", "break": "break_to_close", "close": "close_to_next_open"}
    return {
        "archive_metadata": {"snapshot_id": f"phase0-{slot}", "slot": slot, "horizon": horizons[slot],
                             "actual_threshold_pct": threshold},
        "benchmark": {"symbol": "^JKSE", "baseline": benchmark}, "stocks": stocks,
    }


def forecast_rows(predictions):
    targets = {"A": 2.0, "B": 0.0, "C": -2.0}
    return {symbol: {"forecast": prediction, "target_return_pct": targets[symbol]}
            for symbol, prediction in zip(("A", "B", "C"), predictions)}


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, document):
        path = self.root / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_all_horizons_metrics_baselines_and_pending_coverage(self):
        paths = []
        # Actual A/B/C directions are UP/FLAT/DOWN at a 1% threshold.
        prices = {"A": 103.0, "B": 100.5, "C": 97.0}
        paths.append((self.write("open.json", snapshot("open", {"A": 100, "B": 100, "C": 100},
                                                            forecast_rows(("UP", "UP", "DOWN")), legacy=True)),
                      self.write("break.json", snapshot("break", prices, benchmark=1020))))
        paths.append((self.write("break-f.json", snapshot("break", {"A": 100, "B": 100, "C": 100},
                                                               forecast_rows(("UP", "FLAT", "DOWN")))),
                      self.write("close.json", snapshot("close", prices, legacy=True, benchmark=980))))
        paths.append((self.write("close-f.json", snapshot("close", {"A": 100, "B": 100, "C": 100},
                                                               forecast_rows(("UP", "FLAT", "DOWN")))),
                      self.write("next-open.json", snapshot("open", {"A": 103, "B": 100.5}, benchmark=1010))))

        report = evaluate_pairs(paths)
        metrics = report["metrics"]
        self.assertEqual(metrics["evaluated"], 8)
        self.assertEqual(metrics["total_forecasts"], 9)
        self.assertEqual(metrics["coverage_pct"], 88.888889)
        self.assertEqual(metrics["accuracy_pct"], 87.5)
        self.assertEqual(metrics["confusion_matrix"]["FLAT"]["UP"], 1)
        self.assertAlmostEqual(metrics["target_mae_pct"], 0.8125)
        self.assertEqual([item["horizon"] for item in report["pairs"]],
                         ["open_to_break", "break_to_close", "close_to_next_open"])
        self.assertEqual(report["pairs"][2]["status"], "pending")
        self.assertEqual(report["pairs"][2]["missing_symbols"], ["C"])
        self.assertEqual(report["baselines"]["always_flat"]["accuracy_pct"], 37.5)
        self.assertIsNotNone(report["baselines"]["market_direction"])

    def test_threshold_boundaries_are_flat(self):
        self.assertEqual(classify(1.0, 1.0), "FLAT")
        self.assertEqual(classify(-1.0, 1.0), "FLAT")

    def test_market_baseline_unavailable_and_wrong_pair_rejected(self):
        forecast = snapshot("open", {"A": 100}, {"A": {"forecast": "UP", "target_return_pct": 2}})
        forecast.pop("benchmark")
        first = self.write("f.json", forecast)
        checkpoint = self.write("c.json", snapshot("break", {"A": 103}))
        self.assertIsNone(evaluate_pairs([(first, checkpoint)])["baselines"]["market_direction"])
        wrong = self.write("wrong.json", snapshot("close", {"A": 103}))
        with self.assertRaises(EvaluationError):
            evaluate_pairs([(first, wrong)])

    def test_cli_writes_deterministic_json_and_markdown(self):
        first = self.write("f.json", snapshot("open", {"A": 100},
                                              {"A": {"forecast": "UP", "target_return_pct": 2}}, legacy=True))
        second = self.write("c.json", snapshot("break", {"A": 103}, benchmark=1020))
        json_path, md_path = self.root / "report.json", self.root / "report.md"
        command = [sys.executable, "research/evaluate_snapshots.py", "--pair", str(first), str(second),
                   "--json-output", str(json_path), "--markdown-output", str(md_path)]
        result = subprocess.run(command, cwd=Path(__file__).parents[2], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = evaluate_pairs([(first, second)])
        self.assertEqual(json_path.read_text(), render_json(report))
        self.assertEqual(md_path.read_text(), render_markdown(report))


if __name__ == "__main__":
    unittest.main()
