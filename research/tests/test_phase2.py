from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.contract import ValidationError, validate_snapshot
from research.data_quality import assess_data_quality, normalize_bar, normalize_quote
from research.tests.test_phase0 import valid_snapshot


AS_OF = "2026-08-12T16:01:00+07:00"


def quote(**changes):
    value = {"price": 102, "previous_close": 100, "volume": 500, "observed_at": "2026-08-12T15:59:00+07:00"}
    value.update(changes)
    return value


def bars(last_volume=1000):
    return [
        {"timestamp": "2026-08-11T16:00:00+07:00", "open": 98, "high": 101, "low": 97, "close": 100, "volume": 1000},
        {"timestamp": "2026-08-12T16:00:00+07:00", "open": 100, "high": 103, "low": 99, "close": 102, "volume": last_volume},
    ]


class NormalizationTests(unittest.TestCase):
    def test_common_quote_aliases_and_epoch_milliseconds(self):
        result = normalize_quote({"regularMarketPrice": "12.5", "regularMarketVolume": "20", "regularMarketTime": 1786525140000})
        self.assertEqual(result["price"], 12.5)
        self.assertEqual(result["volume"], 20.0)
        self.assertTrue(result["observed_at"].endswith("+00:00"))

    def test_malformed_bar_is_rejected(self):
        self.assertIsNone(normalize_bar({"timestamp": AS_OF, "open": 10, "high": 8, "low": 9, "close": 10, "volume": 1}))


class QualityTests(unittest.TestCase):
    def test_valid_data(self):
        result = assess_data_quality(quote(), bars(), AS_OF)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["age_seconds"], 120)
        self.assertEqual(result["delay_seconds"], 60)
        self.assertEqual(result["valid_bar_count"], 2)
        self.assertEqual(result["turnover"], 102000)
        self.assertEqual(result["volume_ratio"], 1)
        self.assertAlmostEqual(result["range_percent"], 400 / 102)

    def test_stale_quote_is_partial(self):
        result = assess_data_quality(quote(observed_at="2026-08-12T15:00:00+07:00"), bars(), AS_OF)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["stale"])
        self.assertIn("stale_quote", result["issues"])

    def test_missing_quote_is_unavailable(self):
        result = assess_data_quality(None, [], AS_OF)
        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(result["missing"])
        self.assertFalse(result["invalid"])
        self.assertEqual(result["issues"][:2], ["missing_quote", "missing_bars"])

    def test_malformed_quote_and_bar(self):
        result = assess_data_quality({"price": "oops", "observed_at": "today"}, [bars()[0], {"bad": True}], AS_OF)
        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(result["invalid"])
        self.assertEqual(result["valid_bar_count"], 1)
        self.assertIn("invalid_bars", result["issues"])

    def test_thin_liquidity_and_warnings(self):
        result = assess_data_quality(quote(price=125, corporate_action="split", suspended=True), bars(100), AS_OF)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["thin_liquidity"])
        self.assertTrue(result["corporate_action_warning"])
        self.assertTrue(result["limit_move_warning"])
        self.assertTrue(result["suspension_warning"])

    def test_future_timestamps_clamp_age(self):
        result = assess_data_quality(quote(observed_at="2026-08-12T16:02:00+07:00"), bars(), AS_OF)
        self.assertEqual(result["age_seconds"], 0)


class IntegrationTests(unittest.TestCase):
    def test_phase0_contract_accepts_richer_quality_and_rejects_bad_types(self):
        snapshot = valid_snapshot()
        quality = assess_data_quality(quote(), bars(), AS_OF)
        snapshot["stocks"][0]["data_quality"] = quality
        validate_snapshot(snapshot)
        snapshot["stocks"][0]["data_quality"]["stale"] = "false"
        with self.assertRaises(ValidationError):
            validate_snapshot(snapshot)

    def test_unavailable_quality_can_preserve_null_observation_time(self):
        snapshot = valid_snapshot()
        snapshot["stocks"][0]["data_quality"] = assess_data_quality(None, [], AS_OF)
        validate_snapshot(snapshot)

    def test_cli_single_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            path.write_text(json.dumps({"as_of": AS_OF, "quote": quote(), "bars": bars()}), encoding="utf-8")
            result = subprocess.run([sys.executable, "research/quality_report.py", str(path)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "ok")


if __name__ == "__main__":
    unittest.main()
