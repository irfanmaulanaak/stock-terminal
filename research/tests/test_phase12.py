from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.calibration import (FittedCalibrator, calibrate_walk_forward,
                                  calibration_metrics, fit_calibrator,
                                  validate_probabilities)

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def rows(count=30):
    labels = ("UP", "FLAT", "DOWN")
    result = []
    for index in range(count):
        label = labels[index % 3]
        result.append({"id": f"r{index}", "as_of": (BASE + timedelta(hours=index)).isoformat(),
                       "features": {"signal": (1, 0, -1)[index % 3]},
                       "outcome": {"direction": label}, "horizon": "one_hour",
                       "probabilities": {"UP": .8 if label == "UP" else .1,
                                         "FLAT": .8 if label == "FLAT" else .1,
                                         "DOWN": .8 if label == "DOWN" else .1}})
    return result


class CalibrationTests(unittest.TestCase):
    def test_validation_rejects_unsafe_probability_vectors(self):
        self.assertIsNotNone(validate_probabilities({"UP": .2, "FLAT": .3, "DOWN": .5}))
        self.assertIsNone(validate_probabilities({"UP": .2, "FLAT": .3, "DOWN": .4}))
        self.assertIsNone(validate_probabilities({"UP": float("nan"), "FLAT": 0, "DOWN": 1}))
        self.assertIsNone(validate_probabilities({"UP": .5, "FLAT": .5}))

    def test_fit_group_serialize_and_abstain(self):
        calibrator = fit_calibrator(rows(12), temperature_scaling=True, iterations=40)
        output = calibrator.calibrate({"UP": .8, "FLAT": .1, "DOWN": .1}, horizon="one_hour")
        self.assertTrue(output["available"])
        self.assertAlmostEqual(sum(output["probabilities"].values()), 1)
        self.assertEqual(calibrator.to_json(), FittedCalibrator.from_json(calibrator.to_json()).to_json())
        self.assertEqual(calibrator.calibrate({"UP": 2}, horizon="one_hour")["decision"], "ABSTAIN")
        self.assertEqual(calibrator.calibrate({"UP": .8, "FLAT": .1, "DOWN": .1}, horizon="day")["decision"], "ABSTAIN")

    def test_metrics_and_walk_forward_split_boundaries(self):
        metrics = calibration_metrics(rows(9), bins=5)
        self.assertEqual(metrics["evaluated"], 9)
        self.assertLess(metrics["multiclass_log_loss"], 1)
        self.assertEqual(set(metrics["per_class"]), {"UP", "FLAT", "DOWN"})
        report = calibrate_walk_forward(
            rows(), {"name": "multinomial_logistic", "feature_names": ["signal"], "iterations": 30},
            calibrator_config={"iterations": 30}, train_end=(BASE + timedelta(hours=12)).isoformat(),
            validation_seconds=6 * 3600, test_seconds=6 * 3600, fold_count=1)
        fold = report["folds"][0]
        self.assertEqual((fold["source_fit_split"], fold["calibrator_fit_split"], fold["evaluation_split"]),
                         ("train", "validation", "test"))
        self.assertEqual(fold["source_metadata"]["training_row_count"], 12)
        self.assertEqual(fold["calibrator"]["metadata"]["calibration_row_count"], 6)
        self.assertEqual(report["metrics"]["eligible"], 6)
        json.dumps(report)

    def test_cli(self):
        document = {"rows": rows(), "probability_source": {"name": "majority_train"},
                    "calibrator": {"iterations": 20}, "folds": {
                        "train_end": (BASE + timedelta(hours=12)).isoformat(),
                        "validation_seconds": 6 * 3600, "test_seconds": 6 * 3600, "fold_count": 1}}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            result = subprocess.run([sys.executable, "research/calibration_report.py", str(path)],
                                    text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["calibration_version"], "phase12-1.0")


if __name__ == "__main__":
    unittest.main()
