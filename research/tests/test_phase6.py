from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.global_regime import build_global_regime_report, map_exposures


AS_OF = "2026-08-12T16:01:00+07:00"


def observations(values):
    return [{"value": value, "observed_at": f"2026-07-{index + 1:02d}T16:00:00+07:00"}
            for index, value in enumerate(values)]


def fixture():
    return {
        "as_of": AS_OF,
        "horizons": [1, 2],
        "volatility_windows": [2],
        "global_equities": {"sp500": observations([100, 110, 121])},
        "vix": observations([20, 19, 18]),
        "dxy": observations([100, 102, 104]),
        "us_2y": observations([4.0, 4.1, 4.25]),
        "us_10y": observations([4.2, 4.25, 4.3]),
        "commodities": {"oil": observations([70, 77, 84.7]), "gold": observations([2000, 2020, 2040])},
        "symbols": ["OIL.JK", "BANK.JK", "UNKNOWN.JK"],
        "sector_mapping": {"OIL.JK": "Energy", "BANK.JK": "Financials"},
        "symbol_exposures": {"BANK.JK": {"usd": -0.5, "risk": 1}},
        "sector_exposures": {"Energy": {"usd": 0.25, "risk": 0.5,
                                           "commodities": {"oil": 1}}},
    }


class GlobalRegimeTests(unittest.TestCase):
    def test_exact_changes_volatility_and_yields(self):
        report = build_global_regime_report(fixture())
        equity = report["global_equities"]["sp500"]
        self.assertAlmostEqual(equity["changes"]["1"], .1)
        self.assertAlmostEqual(equity["changes"]["2"], .21)
        self.assertAlmostEqual(equity["volatility"]["2"], 0.0)
        self.assertAlmostEqual(report["dxy"]["changes"]["2"], .04)
        self.assertAlmostEqual(report["us_yields"]["us_2y"]["changes"]["2"], .25)
        self.assertAlmostEqual(report["us_yields"]["us_2y"]["changes_bps"]["2"], 25)
        self.assertAlmostEqual(report["commodities"]["oil"]["changes"]["2"], .21)

    def test_future_data_is_excluded_everywhere(self):
        baseline = build_global_regime_report(fixture())
        changed = copy.deepcopy(fixture())
        future = {"value": 1, "observed_at": "2026-08-12T16:02:00+07:00"}
        changed["global_equities"]["sp500"].append(future)
        changed["dxy"].append(future)
        changed["commodities"]["oil"].append(future)
        report = build_global_regime_report(changed)
        self.assertEqual(report["global_equities"]["sp500"]["changes"],
                         baseline["global_equities"]["sp500"]["changes"])
        self.assertEqual(report["dxy"]["latest"], baseline["dxy"]["latest"])
        self.assertEqual(report["commodities"]["oil"]["latest"], 84.7)
        self.assertEqual(report["global_equities"]["sp500"]["availability"]["excluded_future_count"], 1)

    def test_missing_sources_and_unstamped_rows_stay_null(self):
        report = build_global_regime_report({"as_of": AS_OF, "dxy": [{"value": 100}]})
        self.assertIsNone(report["dxy"]["latest"])
        self.assertEqual(report["dxy"]["availability"]["invalid_count"], 1)
        self.assertIsNone(report["vix"]["changes"]["5"])
        self.assertIsNone(report["us_yields"]["us_10y"]["latest"])
        self.assertIsNone(report["commodities"]["tin"]["latest"])
        self.assertIsNone(report["regime_signals"]["risk"])

    def test_explicit_exposure_mapping_and_unknowns(self):
        mapped = map_exposures(["A", "B", "C"], {"A": "Energy", "B": "Unknown"},
                               {"B": {"usd": -1}}, {"Energy": {"risk": 1}})
        self.assertEqual(mapped["A"]["source"], "sector")
        self.assertEqual(mapped["A"]["exposure"]["risk"], 1)
        self.assertEqual(mapped["B"]["source"], "symbol")
        self.assertIsNone(mapped["B"]["exposure"]["risk"])
        self.assertIsNone(mapped["C"]["sector"])
        self.assertIsNone(mapped["C"]["exposure"])

    def test_usd_risk_and_commodity_interactions(self):
        report = build_global_regime_report(fixture())
        self.assertEqual(report["regime_signals"]["usd"], 1)
        self.assertEqual(report["regime_signals"]["risk"], 1)
        self.assertEqual(report["regime_signals"]["commodities"]["oil"], 1)
        oil = report["exposures"]["OIL.JK"]
        self.assertEqual(oil["exposure_source"], "sector")
        self.assertEqual(oil["signals"]["usd"], .25)
        self.assertEqual(oil["signals"]["risk"], .5)
        self.assertEqual(oil["signals"]["commodities"]["oil"], 1)
        self.assertIsNone(oil["signals"]["commodities"]["coal"])
        self.assertIsNone(report["exposures"]["UNKNOWN.JK"]["signals"])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            result = subprocess.run([sys.executable, "research/global_regime_report.py", str(path)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["regime_signals"]["risk"], 1)


if __name__ == "__main__":
    unittest.main()
