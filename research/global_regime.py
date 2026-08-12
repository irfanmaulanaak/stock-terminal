"""Deterministic, point-in-time global market regime calculations.

Returns and price/index changes are decimals. Yield changes are percentage-point
differences (with a basis-point companion). All observations require an explicit
timezone-aware ``observed_at`` and observations after ``as_of`` are excluded.
Exposure data is used only when explicitly supplied; this module never guesses a
symbol's sector or economic sensitivity.
"""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Iterable, Mapping, Sequence

from research.data_quality import parse_timestamp


DEFAULT_HORIZONS = (1, 5, 20)
DEFAULT_VOLATILITY_WINDOWS = (5, 20)
COMMODITIES = ("oil", "coal", "nickel", "copper", "gold", "palm_oil", "tin")


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
    if (not result or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0
                          for value in result)):
        raise ValueError(f"{name} must contain positive integers")
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _series(source: Any, as_of: datetime) -> tuple[list[float], dict[str, Any]]:
    raw = source if isinstance(source, (list, tuple)) else []
    eligible: list[tuple[datetime, float]] = []
    future = invalid = 0
    for row in raw:
        observed = parse_timestamp(row.get("observed_at")) if isinstance(row, Mapping) else None
        value = None
        if isinstance(row, Mapping):
            value = next((_number(row.get(key)) for key in ("close", "value", "price", "yield", "rate")
                          if row.get(key) is not None), None)
        if observed is None or value is None or value <= 0:
            invalid += 1
        elif observed > as_of:
            future += 1
        else:
            eligible.append((observed, value))
    eligible.sort(key=lambda item: item[0])
    return [value for _, value in eligible], {
        "status": "available" if eligible else "unavailable",
        "available": bool(eligible),
        "eligible_count": len(eligible),
        "excluded_future_count": future,
        "invalid_count": invalid,
        "latest_observed_at": _iso(eligible[-1][0]) if eligible else None,
    }


def multi_horizon_changes(values: Sequence[float], horizons: Sequence[int],
                          *, difference: bool = False) -> dict[str, float | None]:
    """Calculate trailing changes, requiring exactly n+1 eligible values."""
    return {str(window): ((values[-1] - values[-window - 1]) if difference
                          else (values[-1] / values[-window - 1] - 1.0))
            if len(values) > window else None for window in horizons}


def rolling_volatility(values: Sequence[float], windows: Sequence[int]) -> dict[str, float | None]:
    """Population standard deviation of trailing close-to-close decimal returns."""
    returns = [values[index] / values[index - 1] - 1.0 for index in range(1, len(values))]
    result: dict[str, float | None] = {}
    for window in windows:
        if len(returns) < window:
            result[str(window)] = None
        else:
            sample = returns[-window:]
            mean = sum(sample) / window
            result[str(window)] = math.sqrt(sum((value - mean) ** 2 for value in sample) / window)
    return result


def _market(source: Any, as_of: datetime, horizons: Sequence[int], windows: Sequence[int],
            *, yield_series: bool = False) -> dict[str, Any]:
    values, availability = _series(source, as_of)
    changes = multi_horizon_changes(values, horizons, difference=yield_series)
    result: dict[str, Any] = {
        "latest": values[-1] if values else None,
        "changes": changes,
        "volatility": rolling_volatility(values, windows),
        "availability": availability,
    }
    if yield_series:
        result["changes_bps"] = {key: value * 100.0 if value is not None else None
                                 for key, value in changes.items()}
    return result


def _exposure(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    usd = _number(value.get("usd"))
    risk = _number(value.get("risk"))
    raw_commodities = value.get("commodities")
    commodities = ({name: _number(raw_commodities.get(name)) for name in COMMODITIES}
                   if isinstance(raw_commodities, Mapping) else {name: None for name in COMMODITIES})
    return {"usd": usd, "risk": risk, "commodities": commodities}


def map_exposures(symbols: Sequence[str], sector_mapping: Mapping[str, Any],
                  symbol_exposures: Mapping[str, Any], sector_exposures: Mapping[str, Any]) -> dict[str, Any]:
    """Map explicit symbol exposure, falling back only to an explicitly mapped sector."""
    if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence):
        raise ValueError("symbols must be an array")
    for value, name in ((sector_mapping, "sector_mapping"), (symbol_exposures, "symbol_exposures"),
                        (sector_exposures, "sector_exposures")):
        if not isinstance(value, Mapping):
            raise ValueError(f"{name} must be an object")
    result: dict[str, Any] = {}
    for raw_symbol in symbols:
        symbol = str(raw_symbol)
        if symbol in result:
            raise ValueError(f"duplicate symbol: {symbol}")
        sector = sector_mapping.get(symbol)
        sector = sector.strip() if isinstance(sector, str) and sector.strip() else None
        direct = _exposure(symbol_exposures.get(symbol))
        inherited = _exposure(sector_exposures.get(sector)) if sector is not None else None
        result[symbol] = {"sector": sector, "source": "symbol" if direct else ("sector" if inherited else None),
                          "exposure": direct if direct is not None else inherited}
    return result


def _sign(value: float | None, *, inverse: bool = False) -> int | None:
    if value is None:
        return None
    sign = 1 if value > 0 else (-1 if value < 0 else 0)
    return -sign if inverse else sign


def _interaction(exposure: float | None, signal: int | None) -> float | None:
    return exposure * signal if exposure is not None and signal is not None else None


def build_global_regime_report(document: Any) -> dict[str, Any]:
    """Build Phase 6 global indicators and explicit exposure interactions."""
    if not isinstance(document, Mapping):
        raise ValueError("input root must be an object")
    as_of = parse_timestamp(document.get("as_of"))
    if as_of is None:
        raise ValueError("as_of must be a timezone-aware timestamp")
    horizons = _windows(document.get("horizons", DEFAULT_HORIZONS), "horizons")
    windows = _windows(document.get("volatility_windows", DEFAULT_VOLATILITY_WINDOWS), "volatility_windows")
    signal_horizon = str(document.get("signal_horizon", horizons[-1]))
    if signal_horizon not in {str(value) for value in horizons}:
        raise ValueError("signal_horizon must be one of horizons")

    raw_equities = document.get("global_equities")
    raw_equities = raw_equities if isinstance(raw_equities, Mapping) else {}
    equities = {str(name): _market(source, as_of, horizons, windows)
                for name, source in sorted(raw_equities.items(), key=lambda item: str(item[0]))}
    vix = _market(document.get("vix"), as_of, horizons, windows)
    dxy = _market(document.get("dxy"), as_of, horizons, windows)
    yields = {name: _market(document.get(name), as_of, horizons, windows, yield_series=True)
              for name in ("us_2y", "us_10y")}
    raw_commodities = document.get("commodities")
    raw_commodities = raw_commodities if isinstance(raw_commodities, Mapping) else {}
    commodities = {name: _market(raw_commodities.get(name), as_of, horizons, windows)
                   for name in COMMODITIES}

    equity_signs = [_sign(value["changes"][signal_horizon]) for value in equities.values()]
    risk_components = [value for value in equity_signs if value is not None]
    vix_sign = _sign(vix["changes"][signal_horizon], inverse=True)
    if vix_sign is not None:
        risk_components.append(vix_sign)
    risk_signal = (_sign(sum(risk_components) / len(risk_components)) if risk_components else None)
    signals = {
        "usd": _sign(dxy["changes"][signal_horizon]),
        "risk": risk_signal,
        "commodities": {name: _sign(value["changes"][signal_horizon])
                        for name, value in commodities.items()},
    }

    symbols = document.get("symbols", [])
    mapped = map_exposures(symbols, document.get("sector_mapping", {}),
                           document.get("symbol_exposures", {}), document.get("sector_exposures", {}))
    interactions: dict[str, Any] = {}
    for symbol, mapping in mapped.items():
        exposure = mapping["exposure"]
        interactions[symbol] = {
            "sector": mapping["sector"], "exposure_source": mapping["source"], "exposure": exposure,
            "signals": None if exposure is None else {
                "usd": _interaction(exposure["usd"], signals["usd"]),
                "risk": _interaction(exposure["risk"], signals["risk"]),
                "commodities": {name: _interaction(exposure["commodities"][name], signals["commodities"][name])
                                for name in COMMODITIES},
            },
        }

    return {"as_of": _iso(as_of), "horizons": list(horizons), "volatility_windows": list(windows),
            "signal_horizon": int(signal_horizon), "global_equities": equities, "vix": vix, "dxy": dxy,
            "us_yields": yields, "commodities": commodities, "regime_signals": signals,
            "exposures": interactions}


calculate_global_regime = build_global_regime_report

