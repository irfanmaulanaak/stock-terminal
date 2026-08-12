from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.sentiment import build_sentiment_report, canonicalize_url, normalize_title


AS_OF = "2026-08-12T16:01:00+07:00"


def article(title, url, published_at="2026-08-12T10:00:00+07:00", publisher="Wire", **extra):
    return {"title": title, "url": url, "publisher": publisher,
            "published_at": published_at, "fetched_at": "2026-08-12T15:00:00+07:00", **extra}


class SentimentTests(unittest.TestCase):
    def test_url_and_title_canonicalization(self):
        self.assertEqual(canonicalize_url("HTTPS://Example.COM:443/a?b=2&utm_source=x&a=1#top"),
                         "https://example.com/a?a=1&b=2")
        self.assertEqual(normalize_title("  Bank's PROFIT—Rises! "), "bank s profit rises")

    def test_dedupes_by_url_or_title_and_publisher(self):
        one = article("Profit rises", "https://reuters.com/a?utm_campaign=x")
        same_url = article("Different headline", "https://reuters.com/a#section")
        same_story = article("PROFIT   rises!", "https://example.com/elsewhere")
        report = build_sentiment_report({"as_of": AS_OF, "company_articles": [one, same_url, same_story]})
        layer = report["layers"]["company"]
        self.assertEqual(layer["article_count"], 1)
        self.assertEqual(layer["articles"][0]["url"], "https://reuters.com/a")

    def test_future_and_naive_timestamps_are_ineligible(self):
        future = article("Future profit", "https://example.com/future", "2026-08-12T16:02:00+07:00")
        naive = article("Naive", "https://example.com/naive", "2026-08-12T10:00:00")
        report = build_sentiment_report({"as_of": AS_OF, "global_articles": [future, naive]})
        self.assertEqual(report["layers"]["global"]["status"], "unavailable")
        with self.assertRaises(ValueError):
            build_sentiment_report({"as_of": "2026-08-12T16:01:00"})

    def test_source_event_tone_impact_and_novelty(self):
        row = article("Company earnings beat with record profit", "https://www.reuters.com/world/a")
        primary = article("Issuer update", "https://investor.example.co.id/news", event_type="Material Event")
        report = build_sentiment_report({"as_of": AS_OF, "issuer_domains": ["example.co.id"],
                                          "company_articles": [row, primary]})
        items = report["layers"]["company"]["articles"]
        by_title = {item["title"]: item for item in items}
        self.assertEqual(by_title[row["title"]]["source_tier"], "financial")
        self.assertEqual(by_title[row["title"]]["event_type"], "earnings")
        self.assertEqual(by_title[row["title"]]["tone"], "positive")
        self.assertEqual(by_title[row["title"]]["impact"], "high")
        self.assertEqual(by_title[row["title"]]["novelty"], "high")
        self.assertEqual(by_title[primary["title"]]["source_tier"], "primary")
        self.assertEqual(by_title[primary["title"]]["event_type"], "material_event")

    def test_layers_are_independent_and_sector_never_uses_company(self):
        company = article("Company profit rises", "https://company.test/a")
        peer = article("Peer loss falls", "https://peer.test/a")
        report = build_sentiment_report({"as_of": AS_OF, "company_articles": [company],
                                          "peer_articles": [peer]})
        self.assertEqual(report["layers"]["company"]["article_count"], 1)
        self.assertEqual(report["layers"]["sector"]["article_count"], 1)
        self.assertEqual(report["layers"]["sector"]["articles"][0]["title"], peer["title"])
        self.assertEqual(report["layers"]["indonesia_market"]["status"], "unavailable")
        self.assertEqual(report["layers"]["global"]["status"], "unavailable")
        json.dumps(report)

    def test_cli(self):
        payload = {"as_of": AS_OF, "indonesia_market_articles": [
            article("Bank Indonesia rate cut", "https://www.bi.go.id/news")
        ]}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run([sys.executable, "research/sentiment_report.py", str(path)],
                                    text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["layers"]["indonesia_market"]["articles"][0]["source_tier"], "primary")


if __name__ == "__main__":
    unittest.main()
