from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.walk_forward import WalkForwardError, evaluate_walk_forward, generate_folds, prepare_rows


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def rows(count=12):
    labels = ("UP", "DOWN", "FLAT")
    return [{"id": f"r{index}", "as_of": (BASE + timedelta(hours=index)).isoformat(),
             "features": {"momentum": (-1, 0, 1)[index % 3]},
             "outcome": {"direction": labels[index % 3], "target": float(index)},
             "horizon": "one_hour", "horizon_seconds": 1800,
             "regime": "risk_on" if index % 2 else "neutral", "sector": "bank"}
            for index in range(count)]


class WalkForwardTests(unittest.TestCase):
    def test_timezone_sort_and_duplicate_configuration(self):
        data = list(reversed(rows(3)))
        self.assertEqual([row["id"] for row in prepare_rows(data)], ["r0", "r1", "r2"])
        data[1]["as_of"] = data[0]["as_of"]
        with self.assertRaises(WalkForwardError):
            prepare_rows(data, reject_duplicate_timestamps=True)
        data = rows(1)
        data[0]["as_of"] = "2026-01-01T00:00:00"
        with self.assertRaises(WalkForwardError):
            prepare_rows(data)

    def test_expanding_rolling_purge_and_embargo(self):
        data = rows()
        data[3]["horizon_seconds"] = 7200
        folds = generate_folds(data, train_end=(BASE + timedelta(hours=4)).isoformat(),
                               validation_seconds=7200, test_seconds=7200,
                               embargo_seconds=3600, purge_seconds=0, fold_count=1)
        fold = folds[0]
        self.assertNotIn("r3", [row["id"] for row in fold["train"]])
        self.assertEqual([row["id"] for row in fold["validation"]], ["r4", "r5"])
        self.assertEqual([row["id"] for row in fold["test"]], ["r7", "r8"])
        rolling = generate_folds(data, train_end=(BASE + timedelta(hours=6)).isoformat(),
                                 validation_seconds=3600, test_seconds=3600, mode="rolling",
                                 train_seconds=7200, fold_count=1)
        self.assertEqual([row["id"] for row in rolling[0]["train"]], ["r4", "r5"])

    def test_metrics_groups_and_feature_coverage(self):
        report = evaluate_walk_forward(
            rows(), {"name": "feature_sign", "feature": "momentum"},
            train_end=(BASE + timedelta(hours=4)).isoformat(), validation_seconds=7200,
            test_seconds=3000, step_seconds=7200, fold_count=2,
        )
        self.assertEqual(report["predictor"]["feature"], "momentum")
        self.assertIn("confusion_matrix", report["metrics"])
        self.assertIn("horizon", report["grouped_metrics"])
        self.assertIn("regime", report["grouped_metrics"])
        self.assertEqual(report["coverage_pct"], 100.0)
        json.dumps(report)

    def test_callback_and_cli_are_json_friendly(self):
        def callback(train, row, config):
            return {"direction": config["direction"], "target": row["outcome"]["target"]}

        report = evaluate_walk_forward(
            rows(), callback, predictor_config={"name": "test_callback", "direction": "UP"},
            train_end=(BASE + timedelta(hours=4)).isoformat(), validation_seconds=3600,
            test_seconds=3600, fold_count=1,
        )
        self.assertEqual(report["metrics"]["target_mae"], 0.0)
        config = {"rows": rows(), "predictor": {"name": "always_flat"}, "folds": {
            "train_end": (BASE + timedelta(hours=4)).isoformat(),
            "validation_seconds": 3600, "test_seconds": 3600, "fold_count": 1}}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            result = subprocess.run([sys.executable, "research/walk_forward_report.py", str(path)],
                                    text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["predictor"]["name"], "always_flat")


if __name__ == "__main__":
    unittest.main()
