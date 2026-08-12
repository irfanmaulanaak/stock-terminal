from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.indonesia_regime import build_indonesia_regime_report, classify_risk_regime


AS_OF = "2026-08-12T16:01:00+07:00"


def observations(values, key="value"):
    return [{key: value, "observed_at": f"2026-07-{index + 1:02d}T16:00:00+07:00"}
            for index, value in enumerate(values)]


def fixture():
    closes = [100, 102, 101, 104, 106, 108]
    return {
        "as_of": AS_OF, "horizons": [1, 5], "volatility_windows": [2, 5],
        "ihsg": observations(closes, "close"),
        "breadth": [{"advancing": 7, "declining": 2, "unchanged": 1,
                     "observed_at": "2026-08-12T15:55:00+07:00"}],
        "foreign_net_flow": observations([10, 25]),
        "usd_idr": observations([16000, 15800, 15600]),
        "bi_rate": observations([5.75, 5.5]),
        "macro_events": [{"name": "BI decision", "value": 5.5,
                          "released_at": "2026-08-10T14:00:00+07:00"}],
    }


class IndonesiaRegimeTests(unittest.TestCase):
    def test_exact_calculations_and_breadth_integration(self):
        report = build_indonesia_regime_report(fixture())
        closes = [100, 102, 101, 104, 106, 108]
        self.assertEqual(report["ihsg"]["trend"]["1"], 108 / 106 - 1)
        self.assertAlmostEqual(report["ihsg"]["trend"]["5"], .08)
        returns = [106 / 104 - 1, 108 / 106 - 1]
        mean = sum(returns) / 2
        expected = (sum((value - mean) ** 2 for value in returns) / 2) ** .5
        self.assertAlmostEqual(report["ihsg"]["volatility"]["2"], expected)
        self.assertAlmostEqual(report["breadth"]["value"]["breadth"], .5)
        self.assertEqual(report["foreign_net_flow"]["latest"], 25)
        self.assertEqual(report["foreign_net_flow"]["acceleration"], 15)
        self.assertEqual(report["usd_idr"]["changes"]["1"], 15600 / 15800 - 1)
        self.assertEqual(report["bi_rate"]["change"], -.25)
        self.assertEqual(report["bi_rate"]["change_bps"], -25)
        self.assertTrue(report["macro_events"]["events"][0]["fresh"])
        self.assertEqual(report["risk_regime"]["regime"], "risk_on")

    def test_timestamp_gating_and_no_lookahead(self):
        baseline = build_indonesia_regime_report(fixture())
        changed = copy.deepcopy(fixture())
        changed["ihsg"].append({"close": 1, "observed_at": "2026-08-12T16:02:00+07:00"})
        changed["foreign_net_flow"].append({"value": -9999, "observed_at": "2026-08-13T09:00:00+07:00"})
        changed["macro_events"].append({"name": "future", "released_at": "2026-08-13T00:00:00+07:00"})
        result = build_indonesia_regime_report(changed)
        self.assertEqual(result["ihsg"]["trend"], baseline["ihsg"]["trend"])
        self.assertEqual(result["foreign_net_flow"]["latest"], baseline["foreign_net_flow"]["latest"])
        self.assertEqual(result["macro_events"]["events"], baseline["macro_events"]["events"])
        self.assertEqual(result["ihsg"]["availability"]["excluded_future_count"], 1)
        self.assertEqual(result["foreign_net_flow"]["availability"]["excluded_future_count"], 1)
        self.assertEqual(result["macro_events"]["availability"]["excluded_future_count"], 1)

    def test_missing_and_unstamped_values_stay_unavailable(self):
        report = build_indonesia_regime_report({"as_of": AS_OF, "ihsg": [{"close": 9000}]})
        self.assertIsNone(report["ihsg"]["latest"])
        self.assertEqual(report["ihsg"]["availability"]["status"], "unavailable")
        self.assertEqual(report["ihsg"]["availability"]["invalid_count"], 1)
        self.assertIsNone(report["breadth"]["value"])
        self.assertIsNone(report["foreign_net_flow"]["latest"])
        self.assertIsNone(report["usd_idr"]["changes"]["5"])
        self.assertIsNone(report["bi_rate"]["change"])
        self.assertIsNone(report["macro_events"]["availability"]["latest_fresh"])
        self.assertIsNone(report["risk_regime"]["regime"])

    def test_timezone_is_required_for_checkpoint_and_inputs(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            build_indonesia_regime_report({"as_of": "2026-08-12T16:01:00"})
        report = build_indonesia_regime_report({"as_of": AS_OF,
                                                "usd_idr": [{"value": 16000, "observed_at": "2026-08-12T15:00:00"}]})
        self.assertEqual(report["usd_idr"]["availability"]["invalid_count"], 1)

    def test_risk_regimes_and_coverage_gate(self):
        positive = {name: 1 for name in ("trend", "breadth", "flow")}
        negative = {name: -1 for name in ("trend", "breadth", "flow")}
        mixed = {"trend": 1, "breadth": -1, "flow": 0}
        self.assertEqual(classify_risk_regime(positive)["regime"], "risk_on")
        self.assertEqual(classify_risk_regime(negative)["regime"], "risk_off")
        self.assertEqual(classify_risk_regime(mixed)["regime"], "neutral")
        self.assertIsNone(classify_risk_regime({"trend": 1, "breadth": None})["regime"])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            result = subprocess.run([sys.executable, "research/indonesia_regime_report.py", str(path)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["risk_regime"]["regime"], "risk_on")


if __name__ == "__main__":
    unittest.main()
