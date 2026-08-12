"""Deterministic cross-sectional and relative-strength calculations.

Returns are decimals (``0.01`` means one percent).  The report builder accepts
two explicit checkpoints and uses an observation only when its timestamp is
exactly equal to the checkpoint timestamp.  It never selects a nearby quote.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from research.data_quality import parse_timestamp


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _values(values: Mapping[str, Any], name: str) -> dict[str, float | None]:
    if not isinstance(values, Mapping):
        raise ValueError(f"{name} must be an object keyed by symbol")
    return {str(symbol): _number(value) for symbol, value in values.items()}


def benchmark_relative_returns(returns: Mapping[str, Any], benchmark_symbol: str) -> dict[str, float | None]:
    """Subtract the benchmark return; all results are null if it is missing."""
    values = _values(returns, "returns")
    benchmark = values.get(benchmark_symbol)
    return {symbol: (value - benchmark if value is not None and benchmark is not None else None)
            for symbol, value in values.items()}


def cross_sectional_breadth(returns: Mapping[str, Any]) -> dict[str, Any]:
    """Count advancing/declining/unchanged symbols and return net breadth."""
    values = [value for value in _values(returns, "returns").values() if value is not None]
    advancing = sum(value > 0 for value in values)
    declining = sum(value < 0 for value in values)
    unchanged = len(values) - advancing - declining
    return {"advancing": advancing, "declining": declining, "unchanged": unchanged,
            "available": len(values),
            "breadth": (advancing - declining) / len(values) if values else None}


def map_sectors(symbols: Sequence[str], sector_mapping: Mapping[str, Any]) -> dict[str, str | None]:
    """Apply an explicit sector mapping; unknown or blank sectors stay null."""
    if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence):
        raise ValueError("symbols must be an array")
    if not isinstance(sector_mapping, Mapping):
        raise ValueError("sector_mapping must be an object keyed by symbol")
    result: dict[str, str | None] = {}
    for raw_symbol in symbols:
        symbol = str(raw_symbol)
        if symbol in result:
            raise ValueError(f"duplicate symbol: {symbol}")
        sector = sector_mapping.get(symbol)
        result[symbol] = sector.strip() if isinstance(sector, str) and sector.strip() else None
    return result


def sector_returns(returns: Mapping[str, Any], sector_mapping: Mapping[str, Any]) -> dict[str, float]:
    """Return equal-weighted mean returns for explicitly mapped sectors."""
    values = _values(returns, "returns")
    sectors = map_sectors(list(values), sector_mapping)
    grouped: dict[str, list[float]] = {}
    for symbol, value in values.items():
        sector = sectors[symbol]
        if sector is not None and value is not None:
            grouped.setdefault(sector, []).append(value)
    return {sector: sum(group) / len(group) for sector, group in sorted(grouped.items())}


def sector_breadth(returns: Mapping[str, Any], sector_mapping: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Calculate cross-sectional breadth independently within each sector."""
    values = _values(returns, "returns")
    sectors = map_sectors(list(values), sector_mapping)
    grouped: dict[str, dict[str, float | None]] = {}
    for symbol, value in values.items():
        sector = sectors[symbol]
        if sector is not None:
            grouped.setdefault(sector, {})[symbol] = value
    return {sector: cross_sectional_breadth(group) for sector, group in sorted(grouped.items())}


def peer_relative_returns(returns: Mapping[str, Any], sector_mapping: Mapping[str, Any]) -> dict[str, float | None]:
    """Subtract the equal-weighted return of a symbol's *other* sector peers."""
    values = _values(returns, "returns")
    sectors = map_sectors(list(values), sector_mapping)
    result: dict[str, float | None] = {}
    for symbol, value in values.items():
        sector = sectors[symbol]
        peers = [peer_return for peer, peer_return in values.items()
                 if peer != symbol and sectors[peer] == sector and peer_return is not None]
        result[symbol] = value - sum(peers) / len(peers) if value is not None and sector is not None and peers else None
    return result


def volume_breadth(returns: Mapping[str, Any], volumes: Mapping[str, Any]) -> dict[str, Any]:
    """Compare advancing and declining volume, ignoring flat/unavailable rows."""
    return_values = _values(returns, "returns")
    volume_values = _values(volumes, "volumes")
    advancing = sum(volume_values.get(symbol) or 0.0 for symbol, value in return_values.items()
                    if value is not None and value > 0 and (volume_values.get(symbol) or 0) >= 0)
    declining = sum(volume_values.get(symbol) or 0.0 for symbol, value in return_values.items()
                    if value is not None and value < 0 and (volume_values.get(symbol) or 0) >= 0)
    total = advancing + declining
    return {"advancing_volume": advancing, "declining_volume": declining,
            "directional_volume": total,
            "breadth": (advancing - declining) / total if total > 0 else None}


def _checkpoint(checkpoint: Any, name: str) -> tuple[str, dict[str, dict[str, float | None]]]:
    if not isinstance(checkpoint, Mapping):
        raise ValueError(f"{name} must be an object")
    as_of = checkpoint.get("as_of")
    expected = parse_timestamp(as_of)
    if expected is None:
        raise ValueError(f"{name}.as_of must be a timezone-aware timestamp")
    observations = checkpoint.get("observations")
    if not isinstance(observations, (list, tuple)):
        raise ValueError(f"{name}.observations must be an array")
    indexed: dict[str, dict[str, float | None]] = {}
    for index, row in enumerate(observations):
        if not isinstance(row, Mapping) or not isinstance(row.get("symbol"), str) or not row["symbol"]:
            raise ValueError(f"{name}.observations[{index}] must have a symbol")
        symbol = row["symbol"]
        if symbol in indexed:
            raise ValueError(f"duplicate symbol in {name}: {symbol}")
        observed = parse_timestamp(row.get("observed_at"))
        aligned = observed is not None and observed == expected
        price = _number(row.get("price")) if aligned else None
        volume = _number(row.get("volume")) if aligned else None
        indexed[symbol] = {"price": price if price is not None and price > 0 else None,
                           "volume": volume if volume is not None and volume >= 0 else None}
    return expected.isoformat(timespec="seconds"), indexed


def build_relative_strength_report(start: Any, end: Any, benchmark_symbol: str,
                                   sector_mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Build a Phase 4 report from two explicitly timestamped checkpoints."""
    start_at, starts = _checkpoint(start, "start")
    end_at, ends = _checkpoint(end, "end")
    if parse_timestamp(end_at) <= parse_timestamp(start_at):
        raise ValueError("end.as_of must be later than start.as_of")
    symbols = list(dict.fromkeys([*starts, *ends]))
    sectors = map_sectors(symbols, sector_mapping)
    returns: dict[str, float | None] = {}
    volumes: dict[str, float | None] = {}
    for symbol in symbols:
        first = starts.get(symbol, {}).get("price")
        last = ends.get(symbol, {}).get("price")
        returns[symbol] = last / first - 1.0 if first is not None and last is not None else None
        volumes[symbol] = ends.get(symbol, {}).get("volume")
    return {
        "start_at": start_at, "end_at": end_at, "benchmark_symbol": benchmark_symbol,
        "returns": returns,
        "benchmark_relative_returns": benchmark_relative_returns(returns, benchmark_symbol),
        "cross_sectional_breadth": cross_sectional_breadth(returns),
        "sectors": sectors,
        "sector_returns": sector_returns(returns, sectors),
        "sector_breadth": sector_breadth(returns, sectors),
        "peer_relative_returns": peer_relative_returns(returns, sectors),
        "volume_breadth": volume_breadth(returns, volumes),
    }


calculate_relative_strength = build_relative_strength_report
calculate_benchmark_relative_returns = benchmark_relative_returns
calculate_cross_sectional_breadth = cross_sectional_breadth
calculate_sector_returns = sector_returns
calculate_sector_breadth = sector_breadth
calculate_peer_relative_returns = peer_relative_returns
calculate_volume_breadth = volume_breadth
