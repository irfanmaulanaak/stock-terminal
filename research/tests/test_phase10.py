from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.ablation import run_ablation_experiments
from research.walk_forward import WalkForwardError


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def rows():
    values = (-2, 2, -2, 2, -2, 2, -2, 2, -2, 2)
    return [{"id": f"r{i}", "as_of": (BASE + timedelta(hours=i)).isoformat(),
             "features": {"momentum": value, "noise": -value},
             "outcome": {"direction": "UP" if value > 0 else "DOWN"},
             "horizon": "hour", "regime": "odd" if i % 2 else "even"}
            for i, value in enumerate(values)]


FOLDS = {"train_end": (BASE + timedelta(hours=4)).isoformat(),
         "validation_seconds": 3600, "test_seconds": 3600,
         "step_seconds": 3600, "fold_count": 5}


class AblationTests(unittest.TestCase):
    def test_order_winner_groups_and_missing_feature_abstention(self):
        data = rows()
        del data[7]["features"]["momentum"]
        specs = [
            {"name": "noise", "feature_groups": {"noise": ["noise"]},
             "predictor": "feature_sign"},
            {"name": "signal", "feature_groups": {"technical": ["momentum"]},
             "predictor": {"name": "feature_sign"}, "thresholds": {"momentum": 0.5}},
        ]
        report = run_ablation_experiments(data, specs, folds=FOLDS,
                                          baseline_predictor="always_flat")
        self.assertEqual(report["metadata"]["experiment_order"], ["noise", "signal"])
        self.assertEqual(report["winner"]["name"], "signal")
        signal = report["experiments"][1]
        self.assertEqual(signal["metrics"]["eligible"], 5)
        self.assertEqual(signal["metrics"]["evaluated"], 4)
        self.assertEqual(signal["coverage_pct"], 80.0)
        self.assertIn("regime", signal["grouped_metrics"])
        self.assertEqual([item["group"] for item in report["feature_group_contribution_summary"]],
                         ["noise", "technical"])
        json.dumps(report)

    def test_no_winner_without_strict_oos_improvement_and_validation(self):
        report = run_ablation_experiments(
            rows(), [{"name": "flat", "feature_groups": {"technical": ["momentum"]},
                      "predictor": "always_flat"}], folds=FOLDS,
            baseline_predictor="always_flat")
        self.assertIsNone(report["winner"])
        with self.assertRaises(WalkForwardError):
            run_ablation_experiments(rows(), [
                {"name": "bad", "feature_groups": {"a": ["momentum"], "b": ["momentum"]},
                 "predictor": "feature_sign"}], folds=FOLDS)

    def test_cli(self):
        config = {"rows": rows(), "experiments": [
            {"name": "signal", "feature_groups": {"technical": ["momentum"]},
             "predictor": "feature_sign"}], "folds": FOLDS,
             "baseline_predictor": "always_flat"}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ablation.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            result = subprocess.run([sys.executable, "research/ablation_report.py", str(path)],
                                    text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["phase"], 10)


if __name__ == "__main__":
    unittest.main()
