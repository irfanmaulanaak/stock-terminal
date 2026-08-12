from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.models import FittedModel, compare_models, fit_model, serialize_model


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def rows(count=12):
    result = []
    for index in range(count):
        value = float(index - 5)
        result.append({"id": f"r{index}",
                       "as_of": (BASE + timedelta(hours=index)).isoformat(),
                       "features": {"signal": value, "constant": 4.0},
                       "outcome": {"direction": "UP" if value > 0 else
                                   "DOWN" if value < 0 else "FLAT",
                                   "target": value / 100},
                       "horizon_seconds": 0})
    return result


FOLDS = {"train_end": (BASE + timedelta(hours=7)).isoformat(),
         "validation_seconds": 3600, "test_seconds": 3600,
         "step_seconds": 3600, "fold_count": 3}


class ModelTests(unittest.TestCase):
    def test_baselines_sign_and_missing_are_explicit(self):
        flat = fit_model(reversed(rows(4)), "always_flat")
        self.assertEqual(flat.predict(rows(1)[0])["direction"], "FLAT")
        majority = fit_model(rows(5), "majority_train")
        self.assertEqual(majority.predict(rows(1)[0])["direction"], "DOWN")
        sign = fit_model(rows(4), {"name": "feature_sign", "features": ["signal"]})
        prediction = sign.predict({"features": {}})
        self.assertFalse(prediction["available"])
        self.assertIsNone(prediction["direction"])

    def test_logistic_metadata_probabilities_and_serialization(self):
        model = fit_model(rows(11), {"name": "multinomial_logistic",
                                    "features": ["signal", "constant"],
                                    "regularization": 0.02, "iterations": 300,
                                    "learning_rate": 0.1})
        metadata = model.metadata
        self.assertEqual(metadata["feature_names"], ["signal", "constant"])
        self.assertEqual(metadata["scales"][1], 1.0)
        self.assertEqual(metadata["iterations"], 300)
        prediction = model.predict({"features": {"signal": 8, "constant": 4}})
        self.assertEqual(prediction["direction"], "UP")
        self.assertAlmostEqual(sum(prediction["probabilities"].values()), 1.0)
        encoded = serialize_model(model)
        self.assertEqual(encoded, serialize_model(model))
        restored = FittedModel.from_json(encoded)
        self.assertEqual(restored.predict({"features": {"signal": 8, "constant": 4}}), prediction)

    def test_ridge_target_and_complete_training_rows(self):
        data = rows(8)
        del data[2]["features"]["signal"]
        model = fit_model(data, {"name": "ridge", "features": ["signal"],
                                 "regularization": 0.001})
        self.assertEqual(model.metadata["training_row_count"], 8)
        self.assertEqual(model.metadata["fitted_row_count"], 7)
        prediction = model.predict({"features": {"signal": 10}})
        self.assertGreater(prediction["target"], 0)
        self.assertEqual(prediction["direction"], "UP")
        alternate = rows(5)
        for row in alternate:
            row["target_return"] = row["outcome"].pop("target")
        self.assertEqual(fit_model(alternate, {"name": "ridge", "features": ["signal"]}).metadata[
            "fitted_row_count"], 5)

    def test_comparison_fits_each_fold_on_train_only(self):
        data = rows()
        data[8]["features"]["signal"] = 10000.0
        report = compare_models(data, ["always_flat", {"name": "ridge", "features": ["signal"]}],
                                folds=FOLDS)
        self.assertEqual(report["phase"], 11)
        ridge = report["models"][1]
        self.assertEqual(len(ridge["fit_metadata_by_fold"]), 3)
        self.assertEqual([item["fold"] for item in ridge["fit_metadata_by_fold"]], [0, 1, 2])
        self.assertEqual(ridge["fit_metadata_by_fold"][0]["training_row_count"], 7)
        self.assertLess(ridge["fit_metadata_by_fold"][0]["means"][0], 0)
        json.dumps(report)

    def test_cli(self):
        config = {"rows": rows(), "models": ["always_flat", {
            "name": "multinomial_logistic", "features": ["signal"], "iterations": 20}],
            "folds": FOLDS}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "models.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            result = subprocess.run([sys.executable, "research/model_report.py", str(path)],
                                    text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["phase"], 11)


if __name__ == "__main__":
    unittest.main()
