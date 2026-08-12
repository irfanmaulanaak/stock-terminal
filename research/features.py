"""Deterministic, trailing-only features from canonical OHLCV and a quote.

Returns and ratios are decimals (``0.01`` means one percent).  A feature is
``None`` unless its complete trailing window is available.  Bars later than
the checkpoint quote are ignored, which makes archived replays immune to
lookahead when more history is appended later.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

from research.data_quality import normalize_bars, normalize_quote, parse_timestamp

DEFAULT_RETURN_HORIZONS = (1, 5, 20)
DEFAULT_ROLLING_WINDOWS = (5, 20)
DEFAULT_ATR_WINDOW = 14


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _population_stddev(values: Sequence[float]) -> float:
    average = _mean(values)
    return math.sqrt(sum((value - average) ** 2 for value in values) / len(values))


def _windows(values: Iterable[int], name: str) -> tuple[int, ...]:
    result = tuple(values)
    if not result or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in result):
        raise ValueError(f"{name} must contain positive integers")
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def build_features(
    bars: Any,
    quote: Any,
    *,
    return_horizons: Iterable[int] = DEFAULT_RETURN_HORIZONS,
    rolling_windows: Iterable[int] = DEFAULT_ROLLING_WINDOWS,
    atr_window: int = DEFAULT_ATR_WINDOW,
) -> dict[str, Any]:
    """Build a checkpoint feature vector using observations available then.

    Horizon ``n`` compares the quote price with the close ``n`` completed bars
    ago.  Volatility uses population standard deviation of ``n`` consecutive
    close-to-close returns.  Rolling high/low distances require ``n`` completed
    bars.  ATR-like range is the mean true range over completed bars, divided
    by the latest close so instruments remain comparable.
    """
    horizons = _windows(return_horizons, "return_horizons")
    windows = _windows(rolling_windows, "rolling_windows")
    if isinstance(atr_window, bool) or not isinstance(atr_window, int) or atr_window <= 0:
        raise ValueError("atr_window must be a positive integer")

    normalized_quote = normalize_quote(quote)
    quote_price = normalized_quote["price"] if normalized_quote else None
    quote_volume = normalized_quote["volume"] if normalized_quote else None
    quote_time = parse_timestamp(normalized_quote["observed_at"]) if normalized_quote else None
    valid_quote = quote_price is not None and quote_price > 0 and quote_time is not None
    ordered = normalize_bars(bars)
    eligible = [bar for bar in ordered if parse_timestamp(bar["observed_at"]) <= quote_time] if quote_time else []

    features: dict[str, Any] = {
        "as_of": normalized_quote["observed_at"] if normalized_quote else None,
        "bar_count": len(eligible),
        "price": quote_price if valid_quote else None,
    }
    closes = [bar["close"] for bar in eligible]
    close_returns = [closes[index] / closes[index - 1] - 1.0 for index in range(1, len(closes))]

    for horizon in horizons:
        features[f"return_{horizon}"] = quote_price / closes[-horizon] - 1.0 if valid_quote and len(closes) >= horizon else None

    latest = eligible[-1] if eligible else None
    previous = eligible[-2] if len(eligible) >= 2 else None
    features["gap"] = latest["open"] / previous["close"] - 1.0 if previous else None
    features["range"] = (latest["high"] - latest["low"]) / latest["close"] if latest else None
    features["close_location"] = ((latest["close"] - latest["low"]) / (latest["high"] - latest["low"])
                                    if latest and latest["high"] != latest["low"] else None)

    for window in windows:
        features[f"volatility_{window}"] = _population_stddev(close_returns[-window:]) if len(close_returns) >= window else None
        if len(eligible) >= window and valid_quote:
            trailing = eligible[-window:]
            features[f"distance_to_high_{window}"] = quote_price / max(bar["high"] for bar in trailing) - 1.0
            features[f"distance_to_low_{window}"] = quote_price / min(bar["low"] for bar in trailing) - 1.0
        else:
            features[f"distance_to_high_{window}"] = None
            features[f"distance_to_low_{window}"] = None

    true_ranges: list[float] = []
    for index, bar in enumerate(eligible):
        if index == 0:
            continue
        prior_close = eligible[index - 1]["close"]
        true_ranges.append(max(bar["high"] - bar["low"], abs(bar["high"] - prior_close), abs(bar["low"] - prior_close)))
    features[f"average_true_range_{atr_window}"] = (_mean(true_ranges[-atr_window:]) / latest["close"]
                                                     if latest and len(true_ranges) >= atr_window else None)

    momentum = quote_price / closes[-5] - 1.0 if valid_quote and len(closes) >= 5 else None
    one_bar_return = quote_price / closes[-1] - 1.0 if valid_quote and closes else None
    features["momentum"] = momentum
    features["short_term_reversal"] = -one_bar_return if one_bar_return is not None else None
    prior_volumes = [bar["volume"] for bar in eligible if bar["volume"] > 0]
    features["volume_ratio"] = (quote_volume / _mean(prior_volumes)
                                if valid_quote and quote_volume is not None and quote_volume >= 0 and prior_volumes else None)
    features["turnover"] = (quote_price * quote_volume
                            if valid_quote and quote_volume is not None and quote_volume >= 0 else None)
    features["price_volume_interaction"] = (one_bar_return * features["volume_ratio"]
                                             if one_bar_return is not None and features["volume_ratio"] is not None else None)
    return features


def build_feature_report(observations: Any, **options: Any) -> list[dict[str, Any]]:
    """Build symbol-labelled vectors in input order."""
    if not isinstance(observations, (list, tuple)):
        raise ValueError("observations must be an array")
    result = []
    for index, item in enumerate(observations):
        if not isinstance(item, Mapping):
            raise ValueError(f"observations[{index}] must be an object")
        result.append({"symbol": item.get("symbol"), "features": build_features(item.get("bars"), item.get("quote"), **options)})
    return result


calculate_features = build_features
