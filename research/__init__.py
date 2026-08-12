"""Local, dependency-free contracts for immutable IDX research snapshots."""

from .contract import (
    HORIZONS,
    SLOT_BREAK,
    SLOT_CLOSE,
    SLOT_OPEN,
    SLOTS,
    ValidationError,
    is_trading_day,
    next_trading_day,
    validate_snapshot,
)
from .data_quality import assess_data_quality, calculate_data_quality, normalize_bar, normalize_bars, normalize_quote

__all__ = [
    "HORIZONS",
    "SLOT_BREAK",
    "SLOT_CLOSE",
    "SLOT_OPEN",
    "SLOTS",
    "ValidationError",
    "is_trading_day",
    "next_trading_day",
    "validate_snapshot",
    "assess_data_quality",
    "calculate_data_quality",
    "normalize_bar",
    "normalize_bars",
    "normalize_quote",
]
