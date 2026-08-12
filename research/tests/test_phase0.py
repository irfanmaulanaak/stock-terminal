from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.archive import atomic_write_json, generate_manifest, validate_manifest
from research.contract import HORIZONS, ValidationError, is_trading_day, next_trading_day, validate_snapshot


def valid_snapshot():
    return {
        "archive_metadata": {
            "schema_version": "1.0", "snapshot_id": "20260812-close", "created_at": "2026-08-12T16:01:00+07:00",
            "trading_date": "2026-08-12", "slot": "close", "horizon": HORIZONS["close"],
            "timezone": "Asia/Jakarta", "source": "local-research", "immutable": True,
        },
        "market_context": {"indonesia_market": "mixed", "global": "risk-off"},
        "stocks": [{
            "symbol": "BBCA.JK", "sentiment_context": {"company": "neutral", "sector": "mixed", "indonesia_market": "mixed", "global": "risk-off"},
            "sentiment_conflict": True, "forecast_modifier": "reduced_conviction", "sentiment_summary": "Conflicting inputs.",
            "data_quality": {"status": "partial", "issues": ["delayed headline"], "observed_at": "2026-08-12T15:58:00+07:00"},
        }],
    }


class TradingDayTests(unittest.TestCase):
    def test_weekend_and_holiday(self):
        self.assertTrue(is_trading_day("2026-08-12"))
        self.assertFalse(is_trading_day("2026-08-15"))
        self.assertEqual(next_trading_day("2026-08-14"), date(2026, 8, 17))
        self.assertEqual(next_trading_day("2026-08-14", {"2026-08-17"}), date(2026, 8, 18))


class ContractTests(unittest.TestCase):
    def test_valid_snapshot(self):
        self.assertIsNone(validate_snapshot(valid_snapshot()))

    def test_reports_multiple_errors(self):
        snapshot = valid_snapshot()
        snapshot["archive_metadata"]["horizon"] = "wrong"
        del snapshot["stocks"][0]["data_quality"]
        with self.assertRaises(ValidationError) as caught:
            validate_snapshot(snapshot)
        self.assertGreaterEqual(len(caught.exception.errors), 2)


class ArchiveTests(unittest.TestCase):
    def test_atomic_json_and_manifest_tamper_detection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot_path = root / "snapshot.json"
            atomic_write_json(snapshot_path, valid_snapshot())
            self.assertEqual(json.loads(snapshot_path.read_text()), valid_snapshot())
            manifest = generate_manifest(root)
            validate_manifest(root, manifest)
            snapshot_path.write_text("{}\n")
            with self.assertRaises(ValueError):
                validate_manifest(root, manifest)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "checkpoint.json"
            atomic_write_json(path, valid_snapshot())
            result = subprocess.run([sys.executable, "research/validate_snapshot.py", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
