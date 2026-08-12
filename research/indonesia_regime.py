"""Deterministic, point-in-time Indonesia market regime indicators.

All changes are decimals and volatility is population standard deviation of
close-to-close decimal returns.  Every observation must have an explicit,
timezone-aware ``observed_at`` (``released_at`` for macro events).  Invalid or
post-checkpoint observations never participate in a calculation.
"""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Iterable, Mapping, Sequence

from research.data_quality import parse_timestamp

DEFAULT_HORIZONS = (1, 5, 20)
DEFAULT_VOLATILITY_WINDOWS = (5, 20)
DEFAULT_MACRO_FRESH_SECONDS = 7 * 24 * 60 * 60
REGIME_MIN_SIGNALS = 3
REGIME_SCORE_THRESHOLD = 2


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _windows(values: Iterable[int], name: str) -> tuple[int, ...]:
    result = tuple(values)
    if not result or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in result):
        raise ValueError(f"{name} must contain positive integers")
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _series(source: Any, as_of: datetime, value_names: Sequence[str], name: str,
            *, positive: bool = False) -> tuple[list[tuple[datetime, float]], dict[str, Any]]:
    raw = source if isinstance(source, (list, tuple)) else []
    valid: list[tuple[datetime, float]] = []
    future = invalid = 0
    for row in raw:
        if not isinstance(row, Mapping):
            invalid += 1
            continue
        observed = parse_timestamp(row.get("observed_at"))
        value = next((_number(row.get(key)) for key in value_names if row.get(key) is not None), None)
        if observed is None or value is None or (positive and value <= 0):
            invalid += 1
        elif observed > as_of:
            future += 1
        else:
            valid.append((observed, value))
    valid.sort(key=lambda item: item[0])
    metadata = {
        "status": "available" if valid else "unavailable",
        "available": bool(valid),
        "eligible_count": len(valid),
        "excluded_future_count": future,
        "invalid_count": invalid,
        "latest_observed_at": _iso(valid[-1][0]) if valid else None,
    }
    return valid, metadata


def _changes(values: Sequence[float], horizons: Sequence[int]) -> dict[str, float | None]:
    return {str(window): (values[-1] / values[-window - 1] - 1.0 if len(values) > window else None)
            for window in horizons}


def _volatilities(values: Sequence[float], windows: Sequence[int]) -> dict[str, float | None]:
    returns = [values[index] / values[index - 1] - 1.0 for index in range(1, len(values))]
    result: dict[str, float | None] = {}
    for window in windows:
        if len(returns) < window:
            result[str(window)] = None
            continue
        sample = returns[-window:]
        mean = sum(sample) / window
        result[str(window)] = math.sqrt(sum((value - mean) ** 2 for value in sample) / window)
    return result


def _latest_breadth(source: Any, as_of: datetime) -> dict[str, Any]:
    raw = source if isinstance(source, (list, tuple)) else []
    valid: list[tuple[datetime, dict[str, Any]]] = []
    future = invalid = 0
    for row in raw:
        observed = parse_timestamp(row.get("observed_at")) if isinstance(row, Mapping) else None
        advancing = _number(row.get("advancing")) if isinstance(row, Mapping) else None
        declining = _number(row.get("declining")) if isinstance(row, Mapping) else None
        unchanged = _number(row.get("unchanged", 0)) if isinstance(row, Mapping) else None
        if (observed is None or advancing is None or declining is None or unchanged is None
                or min(advancing, declining, unchanged) < 0):
            invalid += 1
        elif observed > as_of:
            future += 1
        else:
            total = advancing + declining + unchanged
            if total <= 0:
                invalid += 1
            else:
                valid.append((observed, {"advancing": advancing, "declining": declining,
                                         "unchanged": unchanged, "available": total,
                                         "breadth": (advancing - declining) / total}))
    valid.sort(key=lambda item: item[0])
    latest = valid[-1] if valid else None
    return {
        "value": latest[1] if latest else None,
        "availability": {
            "status": "available" if latest else "unavailable", "available": bool(latest),
            "eligible_count": len(valid), "excluded_future_count": future, "invalid_count": invalid,
            "latest_observed_at": _iso(latest[0]) if latest else None,
        },
    }


def _macro_events(source: Any, as_of: datetime, fresh_seconds: float) -> dict[str, Any]:
    raw = source if isinstance(source, (list, tuple)) else []
    events: list[tuple[datetime, dict[str, Any]]] = []
    future = invalid = 0
    for row in raw:
        released = parse_timestamp(row.get("released_at")) if isinstance(row, Mapping) else None
        if released is None:
            invalid += 1
        elif released > as_of:
            future += 1
        else:
            age = (as_of - released).total_seconds()
            events.append((released, {"name": row.get("name"), "released_at": _iso(released),
                                      "age_seconds": age, "fresh": age <= fresh_seconds,
                                      "value": row.get("value")}))
    events.sort(key=lambda item: item[0])
    ordered = [item[1] for item in reversed(events)]
    fresh_count = sum(bool(item["fresh"]) for item in ordered)
    return {
        "events": ordered,
        "fresh_count": fresh_count,
        "availability": {
            "status": "available" if ordered else "unavailable", "available": bool(ordered),
            "eligible_count": len(ordered), "excluded_future_count": future, "invalid_count": invalid,
            "latest_released_at": ordered[0]["released_at"] if ordered else None,
            "latest_age_seconds": ordered[0]["age_seconds"] if ordered else None,
            "latest_fresh": ordered[0]["fresh"] if ordered else None,
        },
    }


def classify_risk_regime(signals: Mapping[str, Any], *, min_signals: int = REGIME_MIN_SIGNALS,
                         score_threshold: int = REGIME_SCORE_THRESHOLD) -> dict[str, Any]:
    """Classify signed signals (-1, 0, +1) with an explicit coverage gate."""
    if not isinstance(signals, Mapping):
        raise ValueError("signals must be an object")
    if min_signals <= 0 or score_threshold <= 0:
        raise ValueError("regime thresholds must be positive")
    normalized = {str(name): (int(value) if value in (-1, 0, 1) and not isinstance(value, bool) else None)
                  for name, value in signals.items()}
    available = [value for value in normalized.values() if value is not None]
    score = sum(available) if available else None
    if len(available) < min_signals:
        regime = None
    elif score >= score_threshold:
        regime = "risk_on"
    elif score <= -score_threshold:
        regime = "risk_off"
    else:
        regime = "neutral"
    return {"regime": regime, "score": score, "available_signals": len(available),
            "required_signals": min_signals, "score_threshold": score_threshold, "signals": normalized,
            "availability": {"status": "available" if regime is not None else "unavailable",
                             "available": regime is not None}}


def _sign(value: float | None, *, inverse: bool = False, nonpositive_positive: bool = False) -> int | None:
    if value is None:
        return None
    if nonpositive_positive:
        return 1 if value <= 0 else -1
    sign = 1 if value > 0 else (-1 if value < 0 else 0)
    return -sign if inverse else sign


def build_indonesia_regime_report(document: Any) -> dict[str, Any]:
    """Build Phase 5 indicators from an explicitly timestamped input object."""
    if not isinstance(document, Mapping):
        raise ValueError("input root must be an object")
    as_of = parse_timestamp(document.get("as_of"))
    if as_of is None:
        raise ValueError("as_of must be a timezone-aware timestamp")
    horizons = _windows(document.get("horizons", DEFAULT_HORIZONS), "horizons")
    vol_windows = _windows(document.get("volatility_windows", DEFAULT_VOLATILITY_WINDOWS), "volatility_windows")
    fresh_seconds = _number(document.get("macro_fresh_seconds", DEFAULT_MACRO_FRESH_SECONDS))
    if fresh_seconds is None or fresh_seconds < 0:
        raise ValueError("macro_fresh_seconds must be non-negative")

    ihsg_rows, ihsg_availability = _series(document.get("ihsg"), as_of, ("close", "value", "price"), "ihsg", positive=True)
    ihsg_values = [value for _, value in ihsg_rows]
    ihsg = {"latest": ihsg_values[-1] if ihsg_values else None,
            "trend": _changes(ihsg_values, horizons),
            "volatility": _volatilities(ihsg_values, vol_windows),
            "availability": ihsg_availability}

    breadth = _latest_breadth(document.get("breadth"), as_of)
    flow_rows, flow_availability = _series(document.get("foreign_net_flow"), as_of,
                                            ("value", "net_flow", "amount"), "foreign_net_flow")
    flows = [value for _, value in flow_rows]
    flow = {"latest": flows[-1] if flows else None,
            "acceleration": flows[-1] - flows[-2] if len(flows) >= 2 else None,
            "availability": flow_availability}

    fx_rows, fx_availability = _series(document.get("usd_idr"), as_of, ("value", "rate", "close"), "usd_idr", positive=True)
    fx_values = [value for _, value in fx_rows]
    usd_idr = {"latest": fx_values[-1] if fx_values else None, "changes": _changes(fx_values, horizons),
               "availability": fx_availability}

    rate_rows, rate_availability = _series(document.get("bi_rate"), as_of, ("value", "rate"), "bi_rate")
    rates = [value for _, value in rate_rows]
    rate_change = rates[-1] - rates[-2] if len(rates) >= 2 else None
    bi_rate = {"latest": rates[-1] if rates else None, "change": rate_change,
               "change_bps": rate_change * 100.0 if rate_change is not None else None,
               "availability": rate_availability}
    macro = _macro_events(document.get("macro_events"), as_of, fresh_seconds)

    trend_key = "20" if "20" in ihsg["trend"] else str(horizons[-1])
    fx_key = "5" if "5" in usd_idr["changes"] else str(horizons[-1])
    breadth_value = breadth["value"]["breadth"] if breadth["value"] else None
    signals = {
        "ihsg_trend": _sign(ihsg["trend"][trend_key]),
        "breadth": _sign(breadth_value),
        "foreign_flow": _sign(flow["latest"]),
        "flow_acceleration": _sign(flow["acceleration"]),
        "rupiah": _sign(usd_idr["changes"][fx_key], inverse=True),
        "bi_rate": _sign(rate_change, nonpositive_positive=True),
    }
    regime = classify_risk_regime(signals)
    return {"as_of": _iso(as_of), "horizons": list(horizons), "volatility_windows": list(vol_windows),
            "ihsg": ihsg, "breadth": breadth, "foreign_net_flow": flow, "usd_idr": usd_idr,
            "bi_rate": bi_rate, "macro_events": macro, "risk_regime": regime}


calculate_indonesia_regime = build_indonesia_regime_report
