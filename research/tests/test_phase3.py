from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.features import build_feature_report, build_features


def bar(day, open_, high, low, close, volume):
    return {"timestamp": f"2026-01-{day:02d}T16:00:00+07:00", "open": open_, "high": high,
            "low": low, "close": close, "volume": volume}


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.bars = [bar(1, 9, 11, 8, 10, 100), bar(2, 11, 13, 10, 12, 200),
                     bar(3, 12, 15, 11, 14, 300)]
        self.quote = {"price": 15, "volume": 400, "observed_at": "2026-01-04T12:00:00+07:00"}

    def test_exact_numeric_results(self):
        result = build_features(self.bars, self.quote, return_horizons=(1, 2, 3), rolling_windows=(2,), atr_window=2)
        self.assertEqual(result["return_1"], 15 / 14 - 1)
        self.assertEqual(result["return_2"], 15 / 12 - 1)
        self.assertEqual(result["return_3"], 0.5)
        self.assertEqual(result["gap"], 0.0)
        self.assertEqual(result["range"], 4 / 14)
        self.assertEqual(result["close_location"], 3 / 4)
        returns = [0.2, 14 / 12 - 1]
        expected_std = abs(returns[0] - returns[1]) / 2
        self.assertAlmostEqual(result["volatility_2"], expected_std)
        self.assertEqual(result["average_true_range_2"], 3.5 / 14)
        self.assertEqual(result["distance_to_high_2"], 0.0)
        self.assertEqual(result["distance_to_low_2"], 0.5)
        self.assertEqual(result["volume_ratio"], 2.0)
        self.assertEqual(result["turnover"], 6000)
        self.assertEqual(result["price_volume_interaction"], (15 / 14 - 1) * 2)

    def test_insufficient_history_is_explicit_null(self):
        result = build_features(self.bars[:1], self.quote)
        self.assertIsNone(result["return_5"])
        self.assertIsNone(result["gap"])
        self.assertIsNone(result["volatility_5"])
        self.assertIsNone(result["average_true_range_14"])
        self.assertIsNone(result["momentum"])

    def test_input_order_does_not_change_features_and_report_order_is_preserved(self):
        reversed_result = build_features(list(reversed(self.bars)), self.quote, return_horizons=(1,), rolling_windows=(2,), atr_window=2)
        normal_result = build_features(self.bars, self.quote, return_horizons=(1,), rolling_windows=(2,), atr_window=2)
        self.assertEqual(reversed_result, normal_result)
        report = build_feature_report([{"symbol": "B", "bars": self.bars, "quote": self.quote},
                                       {"symbol": "A", "bars": self.bars, "quote": self.quote}],
                                      return_horizons=(1,), rolling_windows=(2,), atr_window=2)
        self.assertEqual([item["symbol"] for item in report], ["B", "A"])

    def test_future_mutation_cannot_change_checkpoint_features(self):
        baseline = build_features(self.bars, self.quote, return_horizons=(1,), rolling_windows=(2,), atr_window=2)
        mutated = copy.deepcopy(self.bars)
        mutated.append(bar(5, 1000, 1200, 900, 1100, 999999))
        self.assertEqual(build_features(mutated, self.quote, return_horizons=(1,), rolling_windows=(2,), atr_window=2), baseline)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            path.write_text(json.dumps({"quote": self.quote, "bars": self.bars,
                                        "return_horizons": [1], "rolling_windows": [2], "atr_window": 2}), encoding="utf-8")
            result = subprocess.run([sys.executable, "research/features_report.py", str(path)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["bar_count"], 3)


if __name__ == "__main__":
    unittest.main()
