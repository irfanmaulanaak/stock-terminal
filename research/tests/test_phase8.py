from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.abstention import apply_abstention_policy
from research.contract import ValidationError, validate_snapshot
from research.tests.test_phase0 import valid_snapshot


def actionable(**changes):
    values = {
        "forecast_direction": "UP", "confidence": 0.8,
        "probabilities": {"UP": 0.7, "FLAT": 0.2, "DOWN": 0.1},
        "data_quality": {"status": "ok", "missing": False, "stale": False, "invalid": False},
        "required_context_available": {"market": True, "company": True},
        "liquidity": 10.0, "suspension": False, "limit_move": False,
        "corporate_action": False, "history_count": 30, "signal_conflict": 0.2,
    }
    values.update(changes)
    return values


class AbstentionTests(unittest.TestCase):
    def test_actionable_decision_and_json_serialization(self):
        result = apply_abstention_policy(**actionable())
        self.assertEqual(result["decision"], "UP")
        self.assertEqual(result["status"], "actionable")
        self.assertEqual(result["reason_codes"], [])
        self.assertEqual(result["coverage"], 1.0)
        json.dumps(result)

    def test_all_safety_gates_abstain_in_stable_order(self):
        result = apply_abstention_policy(**actionable(
            data_quality={"status": "unavailable", "missing": True, "stale": True, "invalid": True},
            required_context_available={"market": True, "company": False}, liquidity=0,
            suspension=True, limit_move=True, corporate_action=True, history_count=3,
            signal_conflict=0.7,
        ))
        self.assertEqual(result["decision"], "ABSTAIN")
        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(result["coverage"], 0.5)
        for code in ("unavailable_data", "missing_data", "stale_data", "invalid_data",
                     "required_context_unavailable", "inadequate_liquidity", "inadequate_history",
                     "suspension", "limit_move", "corporate_action", "signal_conflict"):
            self.assertIn(code, result["reason_codes"])

    def test_missing_inputs_are_not_coerced(self):
        result = apply_abstention_policy("DOWN", None)
        self.assertEqual(result["decision"], "ABSTAIN")
        self.assertIn("missing_confidence", result["reason_codes"])
        self.assertIn("missing_data_quality", result["reason_codes"])
        self.assertIn("missing_liquidity", result["reason_codes"])
        self.assertIsNone(result["confidence"])
        self.assertIsNone(result["audit_inputs"]["liquidity"])

    def test_data_quality_warning_flags_cannot_be_overridden(self):
        result = apply_abstention_policy(**actionable(
            data_quality={"status": "partial", "thin_liquidity": True,
                          "suspension_warning": True}
        ))
        self.assertEqual(result["decision"], "ABSTAIN")
        self.assertIn("inadequate_liquidity", result["reason_codes"])
        self.assertIn("suspension", result["reason_codes"])

    def test_conflict_threshold_is_strict_and_probabilities_validate(self):
        self.assertEqual(apply_abstention_policy(**actionable(signal_conflict=0.5))["decision"], "UP")
        invalid = apply_abstention_policy(**actionable(probabilities={"UP": 1.2, "FLAT": 0, "DOWN": 0}))
        self.assertEqual(invalid["decision"], "ABSTAIN")
        self.assertIn("invalid_probabilities", invalid["reason_codes"])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            path.write_text(json.dumps(actionable()), encoding="utf-8")
            result = subprocess.run([sys.executable, "research/abstention_report.py", str(path)],
                                    text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["decision"], "UP")


class Phase8ContractTests(unittest.TestCase):
    def test_abstain_and_optional_probabilities_are_valid(self):
        snapshot = valid_snapshot()
        snapshot["stocks"][0].update({"forecast": "ABSTAIN", "probability_up": 0.2,
                                      "probability_flat": 0.5, "probability_down": 0.3})
        self.assertIsNone(validate_snapshot(snapshot))

    def test_legacy_snapshot_without_forecast_or_probabilities_remains_valid(self):
        self.assertIsNone(validate_snapshot(valid_snapshot()))

    def test_invalid_forecast_and_probability_are_rejected(self):
        snapshot = valid_snapshot()
        snapshot["stocks"][0].update({"forecast": "BUY", "probability_up": 1.1})
        with self.assertRaises(ValidationError) as caught:
            validate_snapshot(snapshot)
        self.assertEqual(len(caught.exception.errors), 2)


if __name__ == "__main__":
    unittest.main()
