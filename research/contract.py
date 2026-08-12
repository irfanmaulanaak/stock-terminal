"""Versioned Phase 0 contract for IDX checkpoint research snapshots.

The calendar helpers deliberately model weekdays and accept an explicit holiday
set.  This keeps the package stdlib-only and prevents an implicit, stale holiday
calendar from being mistaken for an exchange calendar.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "1.0"
TIMEZONE = "Asia/Jakarta"

SLOT_OPEN = "open"
SLOT_BREAK = "break"
SLOT_CLOSE = "close"
SLOTS = (SLOT_OPEN, SLOT_BREAK, SLOT_CLOSE)
SLOT_TIMES = {SLOT_OPEN: "09:01", SLOT_BREAK: "12:01", SLOT_CLOSE: "16:01"}

HORIZON_OPEN_TO_BREAK = "open_to_break"
HORIZON_BREAK_TO_CLOSE = "break_to_close"
HORIZON_CLOSE_TO_NEXT_OPEN = "close_to_next_open"
HORIZONS = {
    SLOT_OPEN: HORIZON_OPEN_TO_BREAK,
    SLOT_BREAK: HORIZON_BREAK_TO_CLOSE,
    SLOT_CLOSE: HORIZON_CLOSE_TO_NEXT_OPEN,
}
SENTIMENT_LAYERS = ("company", "sector", "indonesia_market", "global")
DATA_QUALITY_STATUSES = ("ok", "partial", "unavailable")
FORECAST_MODIFIERS = ("supportive", "neutral", "mixed", "reduced_conviction", "market_headwind", "insufficient_data")


class ValidationError(ValueError):
    """Raised with all contract violations found in a snapshot."""

    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(errors)
        super().__init__("snapshot contract violation: " + "; ".join(self.errors))


def _as_date(value: date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid ISO date: {value!r}") from exc


def is_trading_day(day: date | str, holidays: Iterable[date | str] = ()) -> bool:
    """Return whether *day* is a weekday not present in *holidays*."""
    candidate = _as_date(day)
    closed = {_as_date(item) for item in holidays}
    return candidate.weekday() < 5 and candidate not in closed


def next_trading_day(day: date | str, holidays: Iterable[date | str] = ()) -> date:
    """Return the first trading day strictly after *day*."""
    candidate = _as_date(day) + timedelta(days=1)
    closed = {_as_date(item) for item in holidays}
    while not is_trading_day(candidate, closed):
        candidate += timedelta(days=1)
    return candidate


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _timestamp(value: Any) -> bool:
    if not _nonempty_string(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def validate_snapshot(snapshot: Any) -> None:
    """Validate a decoded snapshot, raising :class:`ValidationError` on failure.

    Unknown keys are permitted so producers can add fields without breaking old
    readers.  Required preservation fields are intentionally not optional.
    """
    errors: list[str] = []
    if not isinstance(snapshot, Mapping):
        raise ValidationError(("root must be an object",))

    metadata = snapshot.get("archive_metadata")
    if not isinstance(metadata, Mapping):
        errors.append("archive_metadata must be an object")
        metadata = {}
    required_meta = ("schema_version", "snapshot_id", "created_at", "trading_date", "slot", "horizon", "timezone", "source", "immutable")
    for key in required_meta:
        if key not in metadata:
            errors.append(f"archive_metadata.{key} is required")
    if metadata.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"archive_metadata.schema_version must be {SCHEMA_VERSION!r}")
    for key in ("snapshot_id", "source"):
        if key in metadata and not _nonempty_string(metadata[key]):
            errors.append(f"archive_metadata.{key} must be a non-empty string")
    if "created_at" in metadata and not _timestamp(metadata["created_at"]):
        errors.append("archive_metadata.created_at must be an ISO-8601 timestamp with timezone")
    trading_date = metadata.get("trading_date")
    if trading_date is not None:
        try:
            _as_date(trading_date)
        except ValueError:
            errors.append("archive_metadata.trading_date must be an ISO date")
    slot = metadata.get("slot")
    if slot not in SLOTS:
        errors.append(f"archive_metadata.slot must be one of {SLOTS}")
    elif metadata.get("horizon") != HORIZONS[slot]:
        errors.append(f"archive_metadata.horizon must be {HORIZONS[slot]!r} for slot {slot!r}")
    if metadata.get("timezone") != TIMEZONE:
        errors.append(f"archive_metadata.timezone must be {TIMEZONE!r}")
    if metadata.get("immutable") is not True:
        errors.append("archive_metadata.immutable must be true")

    market = snapshot.get("market_context")
    if not isinstance(market, Mapping):
        errors.append("market_context must be an object")
    else:
        for layer in ("indonesia_market", "global"):
            if not _nonempty_string(market.get(layer)):
                errors.append(f"market_context.{layer} must be a non-empty string")

    stocks = snapshot.get("stocks")
    if not isinstance(stocks, list) or not stocks:
        errors.append("stocks must be a non-empty array")
        stocks = []
    seen: set[str] = set()
    for index, stock in enumerate(stocks):
        prefix = f"stocks[{index}]"
        if not isinstance(stock, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        symbol = stock.get("symbol")
        if not _nonempty_string(symbol):
            errors.append(f"{prefix}.symbol must be a non-empty string")
        elif symbol in seen:
            errors.append(f"{prefix}.symbol duplicates {symbol!r}")
        else:
            seen.add(symbol)
        context = stock.get("sentiment_context")
        if not isinstance(context, Mapping):
            errors.append(f"{prefix}.sentiment_context must be an object")
        else:
            for layer in SENTIMENT_LAYERS:
                if not _nonempty_string(context.get(layer)):
                    errors.append(f"{prefix}.sentiment_context.{layer} must be a non-empty string")
        if not isinstance(stock.get("sentiment_conflict"), bool):
            errors.append(f"{prefix}.sentiment_conflict must be a boolean")
        modifier = stock.get("forecast_modifier")
        if modifier not in FORECAST_MODIFIERS:
            errors.append(f"{prefix}.forecast_modifier must be one of {FORECAST_MODIFIERS}")
        if not _nonempty_string(stock.get("sentiment_summary")):
            errors.append(f"{prefix}.sentiment_summary must be a non-empty string")
        quality = stock.get("data_quality")
        if not isinstance(quality, Mapping):
            errors.append(f"{prefix}.data_quality must be an object")
        else:
            if quality.get("status") not in DATA_QUALITY_STATUSES:
                errors.append(f"{prefix}.data_quality.status must be one of {DATA_QUALITY_STATUSES}")
            if not isinstance(quality.get("issues"), list) or not all(_nonempty_string(v) for v in quality.get("issues", [])):
                errors.append(f"{prefix}.data_quality.issues must be an array of non-empty strings")
            if not _timestamp(quality.get("observed_at")):
                errors.append(f"{prefix}.data_quality.observed_at must be an ISO-8601 timestamp with timezone")
    if errors:
        raise ValidationError(errors)
