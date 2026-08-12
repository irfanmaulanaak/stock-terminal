"""Deterministic, point-in-time article sentiment for Phase 7.

The module performs no I/O and uses only the Python standard library.  All
timestamps in its public output are normalized timezone-aware ISO-8601 strings.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid",
    "vero_conv", "vero_id", "oly_anon_id", "oly_enc_id", "ref_src",
}
SOURCE_TIERS = {"primary", "financial", "discovery", "unknown"}
FINANCIAL_HOSTS = ("reuters.com", "bloomberg.com", "cnbc.com", "ft.com", "wsj.com", "nikkei.com")
DISCOVERY_HOSTS = ("news.google.com", "google.com")
PRIMARY_HOSTS = ("idx.co.id", "bi.go.id")

EVENT_KEYWORDS = (
    ("earnings", ("earnings", "profit", "revenue", "net income", "quarterly result", "financial result", "laba", "pendapatan")),
    ("dividend", ("dividend", "dividen")),
    ("corporate_action", ("rights issue", "stock split", "share buyback", "buyback", "merger", "acquisition", "akuisisi", "ipo")),
    ("management", ("chief executive", " ceo ", "director", "direktur", "management", "manajemen")),
    ("regulatory", ("regulator", "regulation", "regulatory", "sanction", "probe", "investigation", "ojk", "peraturan")),
    ("monetary_policy", ("interest rate", "rate cut", "rate hike", "bank indonesia", "central bank", "suku bunga")),
    ("macro", ("inflation", "gdp", "trade balance", "unemployment", "inflasi", "rupiah")),
    ("analyst", ("upgrade", "downgrade", "price target", "rating")),
    ("operations", ("production", "shipment", "contract", "project", "operasi", "produksi")),
)
POSITIVE = ("beat", "beats", "growth", "grew", "rise", "rises", "surge", "record", "profit", "upgrade", "gain", "wins", "dividend", "buyback", "strong", "naik", "tumbuh", "laba")
NEGATIVE = ("miss", "falls", "fall", "drop", "decline", "loss", "downgrade", "default", "fraud", "probe", "sanction", "weak", "cut", "layoff", "turun", "rugi")
HIGH_IMPACT = ("bankruptcy", "default", "fraud", "merger", "acquisition", "rights issue", "earnings", "financial result", "rate cut", "rate hike", "sanction")
MEDIUM_IMPACT = ("dividend", "buyback", "contract", "project", "production", "management", "director", "upgrade", "downgrade", "inflation", "gdp")


def parse_timestamp(value: Any, name: str = "timestamp") -> datetime:
    """Parse a timezone-aware ISO-8601 timestamp, rejecting naive values."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a timezone-aware timestamp")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{name} must be a timezone-aware timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware timestamp")
    return result


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def canonicalize_url(value: Any) -> str | None:
    """Remove fragments and known tracking parameters from an HTTP(S) URL."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").rstrip(".").lower()
    if scheme not in {"http", "https"} or not host:
        return None
    userinfo = ""
    if parts.username is not None:
        userinfo = parts.username
        if parts.password is not None:
            userinfo += ":" + parts.password
        userinfo += "@"
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = userinfo + host + (f":{port}" if port is not None and not default_port else "")
    query = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS]
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query)), ""))


def normalize_title(value: Any) -> str | None:
    """Return a case-folded, punctuation-insensitive title for matching."""
    if not isinstance(value, str):
        return None
    text = unicodedata.normalize("NFKC", value).casefold()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    text = " ".join(text.split())
    return text or None


def _hostname(url: str | None) -> str:
    return (urlsplit(url).hostname or "").lower() if url else ""


def _domain_matches(host: str, domain: str) -> bool:
    domain = domain.strip().lower().lstrip(".")
    return bool(domain) and (host == domain or host.endswith("." + domain))


def assign_source_tier(article: Mapping[str, Any], issuer_domains: Sequence[str] = ()) -> str:
    explicit = article.get("source_tier")
    if isinstance(explicit, str) and explicit.strip().lower() in SOURCE_TIERS:
        return explicit.strip().lower()
    url = canonicalize_url(article.get("url"))
    host = _hostname(url)
    if any(_domain_matches(host, domain) for domain in (*PRIMARY_HOSTS, *issuer_domains)):
        return "primary"
    if any(_domain_matches(host, domain) for domain in FINANCIAL_HOSTS):
        return "financial"
    if any(_domain_matches(host, domain) for domain in DISCOVERY_HOSTS):
        return "discovery"
    return "unknown"


def _haystack(article: Mapping[str, Any]) -> str:
    values = (article.get("title"), article.get("summary"), article.get("description"))
    return " " + " ".join(str(value).casefold() for value in values if isinstance(value, str)) + " "


def assign_event_type(article: Mapping[str, Any]) -> str:
    explicit = article.get("event_type")
    if isinstance(explicit, str) and explicit.strip():
        return re.sub(r"[^a-z0-9]+", "_", explicit.strip().casefold()).strip("_") or "other"
    text = _haystack(article)
    for event_type, keywords in EVENT_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return event_type
    return "other"


def assign_tone(article: Mapping[str, Any]) -> str:
    text = _haystack(article)
    score = sum(keyword in text for keyword in POSITIVE) - sum(keyword in text for keyword in NEGATIVE)
    return "positive" if score > 0 else "negative" if score < 0 else "neutral"


def assign_impact(article: Mapping[str, Any]) -> str:
    text = _haystack(article)
    if any(keyword in text for keyword in HIGH_IMPACT):
        return "high"
    if any(keyword in text for keyword in MEDIUM_IMPACT):
        return "medium"
    return "low"


def assign_novelty(published_at: datetime, as_of: datetime) -> str:
    age_hours = (as_of - published_at).total_seconds() / 3600
    if age_hours <= 24:
        return "high"
    if age_hours <= 72:
        return "medium"
    return "low"


def normalize_article(article: Any, as_of: datetime, issuer_domains: Sequence[str] = ()) -> dict[str, Any] | None:
    """Normalize one article; malformed, incomplete, or future rows are ineligible."""
    if not isinstance(article, Mapping):
        return None
    title = article.get("title")
    normalized_title = normalize_title(title)
    url = canonicalize_url(article.get("url"))
    publisher = article.get("publisher")
    publisher = " ".join(publisher.split()) if isinstance(publisher, str) and publisher.strip() else _hostname(url)
    try:
        published_at = parse_timestamp(article.get("published_at"), "published_at")
        fetched_at = parse_timestamp(article.get("fetched_at"), "fetched_at")
    except ValueError:
        return None
    if published_at > as_of or not normalized_title or not publisher:
        return None
    normalized: dict[str, Any] = {
        "title": " ".join(str(title).split()),
        "normalized_title": normalized_title,
        "publisher": publisher,
        "url": url,
        "published_at": _iso(published_at),
        "fetched_at": _iso(fetched_at),
        "source_tier": assign_source_tier(article, issuer_domains),
        "event_type": assign_event_type(article),
        "tone": assign_tone(article),
        "impact": assign_impact(article),
        "novelty": assign_novelty(published_at, as_of),
    }
    for field in ("summary", "description"):
        value = article.get(field)
        if isinstance(value, str) and value.strip():
            normalized[field] = " ".join(value.split())
    return normalized


def dedupe_articles(articles: Sequence[Any], as_of: datetime, issuer_domains: Sequence[str] = ()) -> list[dict[str, Any]]:
    """Deduplicate by canonical URL OR normalized title and publisher."""
    if isinstance(articles, (str, bytes)) or not isinstance(articles, Sequence):
        raise ValueError("article input must be an array")
    result: list[dict[str, Any]] = []
    urls: set[str] = set()
    title_publishers: set[tuple[str, str]] = set()
    for article in articles:
        normalized = normalize_article(article, as_of, issuer_domains)
        if normalized is None:
            continue
        url = normalized["url"]
        title_publisher = (normalized["normalized_title"], normalize_title(normalized["publisher"]) or "")
        if (url is not None and url in urls) or title_publisher in title_publishers:
            continue
        result.append(normalized)
        if url is not None:
            urls.add(url)
        title_publishers.add(title_publisher)
    return sorted(result, key=lambda row: (row["published_at"], row["normalized_title"], row["publisher"]), reverse=True)


def _aggregate_layer(name: str, articles: Sequence[Any], as_of: datetime,
                     issuer_domains: Sequence[str]) -> dict[str, Any]:
    items = dedupe_articles(articles, as_of, issuer_domains)
    if not items:
        return {"name": name, "status": "unavailable", "available": False,
                "article_count": 0, "tone": None, "impact": None, "novelty": None,
                "event_types": {}, "source_tiers": {}, "articles": []}
    tones = {key: sum(row["tone"] == key for row in items) for key in ("positive", "negative", "neutral")}
    tone_score = tones["positive"] - tones["negative"]
    impact_rank = {"low": 0, "medium": 1, "high": 2}
    novelty_rank = {"low": 0, "medium": 1, "high": 2}
    events = {key: sum(row["event_type"] == key for row in items) for key in sorted({row["event_type"] for row in items})}
    tiers = {key: sum(row["source_tier"] == key for row in items) for key in sorted({row["source_tier"] for row in items})}
    return {"name": name, "status": "available", "available": True,
            "article_count": len(items),
            "tone": "positive" if tone_score > 0 else "negative" if tone_score < 0 else "neutral",
            "impact": max((row["impact"] for row in items), key=impact_rank.__getitem__),
            "novelty": max((row["novelty"] for row in items), key=novelty_rank.__getitem__),
            "tone_counts": tones, "event_types": events, "source_tiers": tiers, "articles": items}


def build_sentiment_report(document: Any) -> dict[str, Any]:
    """Build four independent Phase 7 layers from explicitly supplied arrays."""
    if not isinstance(document, Mapping):
        raise ValueError("input root must be an object")
    as_of = parse_timestamp(document.get("as_of"), "as_of")
    issuer_domains = document.get("issuer_domains", ())
    if isinstance(issuer_domains, (str, bytes)) or not isinstance(issuer_domains, Sequence) or not all(isinstance(x, str) for x in issuer_domains):
        raise ValueError("issuer_domains must be an array of strings")
    arrays: dict[str, Sequence[Any]] = {}
    for name in ("company_articles", "sector_articles", "peer_articles", "indonesia_market_articles", "global_articles"):
        value = document.get(name, [])
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ValueError(f"{name} must be an array")
        arrays[name] = value
    return {
        "as_of": _iso(as_of),
        "layers": {
            "company": _aggregate_layer("company", arrays["company_articles"], as_of, issuer_domains),
            "sector": _aggregate_layer("sector", [*arrays["sector_articles"], *arrays["peer_articles"]], as_of, issuer_domains),
            "indonesia_market": _aggregate_layer("indonesia_market", arrays["indonesia_market_articles"], as_of, issuer_domains),
            "global": _aggregate_layer("global", arrays["global_articles"], as_of, issuer_domains),
        },
    }


calculate_sentiment = build_sentiment_report
