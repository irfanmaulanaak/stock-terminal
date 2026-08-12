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
]
