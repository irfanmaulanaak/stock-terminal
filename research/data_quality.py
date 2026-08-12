"""Normalize market observations and produce deterministic quality assessments.

The module is deliberately dependency-free.  Callers must supply ``as_of`` so
that replaying an archived observation always produces the same report.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Iterable, Mapping

QUALITY_STATUSES = ("ok", "partial", "unavailable")
DEFAULT_STALE_AFTER_SECONDS = 15 * 60
DEFAULT_THIN_VOLUME_RATIO = 0.25
DEFAULT_LIMIT_MOVE_PERCENT = 20.0


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _first(source: Mapping[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in source and source[name] is not None:
            return source[name]
    return None


def parse_timestamp(value: Any) -> datetime | None:
    """Parse a timezone-aware ISO timestamp or Unix seconds/milliseconds."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        stamp = float(value)
        if not math.isfinite(stamp):
            return None
        if abs(stamp) >= 100_000_000_000:
            stamp /= 1000.0
        try:
            return datetime.fromtimestamp(stamp, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def normalize_quote(observation: Any) -> dict[str, Any] | None:
    """Return a canonical quote, or ``None`` for a non-object observation."""
    if not isinstance(observation, Mapping):
        return None
    price = _number(_first(observation, ("price", "last", "regularMarketPrice", "close")))
    volume = _number(_first(observation, ("volume", "regularMarketVolume")))
    observed = parse_timestamp(_first(observation, ("observed_at", "timestamp", "time", "regularMarketTime")))
    previous = _number(_first(observation, ("previous_close", "previousClose", "regularMarketPreviousClose")))
    return {
        "price": price,
        "volume": volume,
        "observed_at": _iso(observed) if observed else None,
        "previous_close": previous,
    }


def normalize_bar(bar: Any) -> dict[str, Any] | None:
    """Return a canonical OHLCV bar, or ``None`` for malformed input."""
    if not isinstance(bar, Mapping):
        return None
    observed = parse_timestamp(_first(bar, ("observed_at", "timestamp", "time", "date")))
    values = {name: _number(bar.get(name)) for name in ("open", "high", "low", "close", "volume")}
    if observed is None or any(values[name] is None for name in ("open", "high", "low", "close")):
        return None
    if any(values[name] <= 0 for name in ("open", "high", "low", "close")):
        return None
    if values["volume"] is None:
        values["volume"] = 0.0
    if values["volume"] < 0 or values["high"] < max(values["open"], values["close"], values["low"]) or values["low"] > min(values["open"], values["close"], values["high"]):
        return None
    return {"observed_at": _iso(observed), **values}


def normalize_bars(bars: Any) -> list[dict[str, Any]]:
    """Normalize valid bars and sort them chronologically."""
    if not isinstance(bars, (list, tuple)):
        return []
    valid = [normalized for item in bars if (normalized := normalize_bar(item)) is not None]
    return sorted(valid, key=lambda item: item["observed_at"])


def assess_data_quality(
    quote: Any,
    bars: Any,
    as_of: Any,
    *,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    thin_volume_ratio: float = DEFAULT_THIN_VOLUME_RATIO,
    limit_move_percent: float = DEFAULT_LIMIT_MOVE_PERCENT,
) -> dict[str, Any]:
    """Assess a quote and its OHLCV history.

    ``status`` is unavailable for a missing/invalid quote, partial for any other
    warning or incomplete history, and ok otherwise.  This precedence makes the
    result independent of input dictionary ordering.
    """
    reference = parse_timestamp(as_of)
    if reference is None:
        raise ValueError("as_of must be a timezone-aware ISO timestamp or Unix time")
    if stale_after_seconds < 0 or thin_volume_ratio < 0 or limit_move_percent < 0:
        raise ValueError("quality thresholds must be non-negative")

    normalized_quote = normalize_quote(quote)
    raw_bars = bars if isinstance(bars, (list, tuple)) else []
    normalized_bars = normalize_bars(raw_bars)
    missing = quote is None or not isinstance(quote, Mapping)
    invalid = not missing and (normalized_quote is None or normalized_quote["price"] is None or normalized_quote["price"] <= 0 or normalized_quote["observed_at"] is None)

    quote_time = parse_timestamp(normalized_quote["observed_at"]) if normalized_quote else None
    age = max(0.0, (reference - quote_time).total_seconds()) if quote_time else None
    stale = age is not None and age > stale_after_seconds
    last_bar_time = parse_timestamp(normalized_bars[-1]["observed_at"]) if normalized_bars else None
    delay = max(0.0, (reference - last_bar_time).total_seconds()) if last_bar_time else None

    latest = normalized_bars[-1] if normalized_bars else None
    turnover = latest["close"] * latest["volume"] if latest else None
    prior_volumes = [item["volume"] for item in normalized_bars[:-1] if item["volume"] > 0]
    volume_ratio = (latest["volume"] / (sum(prior_volumes) / len(prior_volumes))) if latest and prior_volumes else None
    range_percent = ((latest["high"] - latest["low"]) / latest["close"] * 100.0) if latest else None
    thin_liquidity = bool(latest and (latest["volume"] <= 0 or (volume_ratio is not None and volume_ratio < thin_volume_ratio)))

    previous = normalized_quote["previous_close"] if normalized_quote else None
    price = normalized_quote["price"] if normalized_quote else None
    move_percent = ((price - previous) / previous * 100.0) if price and previous and previous > 0 else None
    corporate_action = bool(isinstance(quote, Mapping) and _first(quote, ("corporate_action", "corporateAction", "split", "dividend")))
    limit_move = move_percent is not None and abs(move_percent) >= limit_move_percent
    suspension = bool(isinstance(quote, Mapping) and _first(quote, ("suspended", "suspension"))) or bool(latest and latest["volume"] == 0 and price == previous)

    partial = (not invalid and not missing) and (not normalized_bars or len(normalized_bars) != len(raw_bars) or stale or thin_liquidity or corporate_action or limit_move or suspension)
    issues: list[str] = []
    for condition, label in (
        (missing, "missing_quote"), (invalid, "invalid_quote"),
        (not normalized_bars, "missing_bars"),
        (bool(raw_bars) and len(normalized_bars) != len(raw_bars), "invalid_bars"),
        (stale, "stale_quote"), (thin_liquidity, "thin_liquidity"),
        (corporate_action, "corporate_action"), (limit_move, "limit_move"),
        (suspension, "possible_suspension"),
    ):
        if condition:
            issues.append(label)
    status = "unavailable" if missing or invalid else ("partial" if partial else "ok")
    return {
        "status": status,
        "issues": issues,
        "observed_at": normalized_quote["observed_at"] if normalized_quote else None,
        "age_seconds": age,
        "delay_seconds": delay,
        "stale": stale,
        "missing": missing,
        "partial": partial,
        "invalid": invalid,
        "thin_liquidity": thin_liquidity,
        "valid_bar_count": len(normalized_bars),
        "turnover": turnover,
        "volume_ratio": volume_ratio,
        "range_percent": range_percent,
        "corporate_action_warning": corporate_action,
        "limit_move_warning": limit_move,
        "suspension_warning": suspension,
        "move_percent": move_percent,
        "normalized_quote": normalized_quote,
        "normalized_bars": normalized_bars,
    }


calculate_data_quality = assess_data_quality

