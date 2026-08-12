from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.archive import atomic_write_json, generate_manifest
from research.contract import HORIZONS
from research.operations import operations_health

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def checkpoint(slot: str) -> dict:
    return {"archive_metadata": {"schema_version": "1.0", "snapshot_id": f"20260812-{slot}", "created_at": "2026-08-12T11:00:00+00:00", "trading_date": "2026-08-12", "slot": slot, "horizon": HORIZONS[slot], "timezone": "Asia/Jakarta", "source": "test", "immutable": True}, "market_context": {"indonesia_market": "neutral", "global": "neutral"}, "stocks": [{"symbol": "BBCA.JK", "sentiment_context": {"company": "neutral", "sector": "neutral", "indonesia_market": "neutral", "global": "neutral"}, "sentiment_conflict": False, "forecast_modifier": "neutral", "sentiment_summary": "No conflict.", "data_quality": {"status": "ok", "issues": [], "observed_at": "2026-08-12T11:00:00+00:00"}}]}


class Phase14OperationsTests(unittest.TestCase):
    def test_missing_state_has_explicit_codes(self):
        report = operations_health(now=NOW)
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["forecastSource"]["status"], "unavailable")
        self.assertIn("FORECAST_MISSING", {item["code"] for item in report["warnings"]})
        self.assertIn("VERIFICATION_MISSING", {item["code"] for item in report["warnings"]})
        self.assertEqual(report["researchUpstream"]["status"], "not_checked")

    def test_stale_and_inconsistent_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            atomic_write_json(root / "forecast.json", {"as_of": "2026-08-01T00:00:00Z", "snapshot_slot": "close_1601_wib", "universe_count": 2, "stocks": [{"symbol": "BBCA", "quote_freshness_seconds": 901}]})
            atomic_write_json(root / "verification.json", {"generated_at": "2026-08-01T00:00:00Z", "metrics": {"evaluated": 0}})
            report = operations_health(forecast_path=root / "forecast.json", verification_path=root / "verification.json", now=NOW)
            codes = {item["code"] for item in report["warnings"]}
            self.assertTrue({"FORECAST_STALE", "UNIVERSE_COUNT_MISMATCH", "STALE_QUOTES", "VERIFICATION_STALE", "VERIFICATION_PENDING"} <= codes)
            self.assertEqual(report["dataQuality"]["staleQuoteCount"], 1)

    def test_healthy_archive_manifest_sources_and_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            archive.mkdir()
            for slot in ("open", "break", "close"):
                atomic_write_json(archive / f"{slot}.json", checkpoint(slot))
            manifest_path = archive / "manifest.json"
            atomic_write_json(manifest_path, generate_manifest(archive))
            forecast = root / "forecast.json"
            verification = root / "verification.json"
            atomic_write_json(forecast, {"as_of": "2026-08-12T11:30:00Z", "snapshot_slot": "close_1601_wib", "universe_count": 1, "stocks": [{"symbol": "BBCA", "quote_freshness_seconds": 30}]})
            atomic_write_json(verification, {"generated_at": "2026-08-12T11:45:00Z", "metrics": {"evaluated": 3}})
            report = operations_health(forecast_path=forecast, verification_path=verification, archive_dir=archive, manifest_path=manifest_path, now=NOW, research_sources={"news": True, "market": True})
            self.assertEqual(report["status"], "healthy")
            self.assertEqual(report["archive"]["availableSlots"], ["break", "close", "open"])
            self.assertTrue(report["archive"]["manifestValid"])
            result = subprocess.run([sys.executable, "research/operations_report.py", "--forecast", str(forecast), "--verification", str(verification), "--archive-dir", str(archive), "--manifest", str(manifest_path), "--now", NOW.isoformat()], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "healthy")


if __name__ == "__main__":
    unittest.main()
