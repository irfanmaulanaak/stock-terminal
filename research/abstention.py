"""Deterministic Phase 8 forecast abstention policy.

The policy is intentionally conservative: absence of a required safety input is
itself evidence for abstention.  It performs no I/O and uses only the standard
library, so an archived input can always be replayed.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


DIRECTIONS = ("UP", "FLAT", "DOWN")
DECISIONS = DIRECTIONS + ("ABSTAIN",)


def _unit_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and 0.0 <= number <= 1.0 else None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _probabilities(value: Any) -> tuple[dict[str, float] | None, bool]:
    if value is None:
        return None, True
    if not isinstance(value, Mapping):
        return None, False
    aliases = {
        "UP": ("UP", "up", "probability_up"),
        "FLAT": ("FLAT", "flat", "probability_flat"),
        "DOWN": ("DOWN", "down", "probability_down"),
    }
    result: dict[str, float] = {}
    for direction, names in aliases.items():
        present = [value[name] for name in names if name in value]
        if len(present) != 1:
            return None, False
        number = _unit_number(present[0])
        if number is None:
            return None, False
        result[direction] = number
    if not math.isclose(sum(result.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
        return None, False
    return result, True


def _context_coverage(value: Any) -> tuple[float, bool, bool]:
    """Return (coverage, structurally valid, all available)."""
    if isinstance(value, bool):
        return (1.0 if value else 0.0), True, value
    if not isinstance(value, Mapping) or not value:
        return 0.0, False, False
    availability = list(value.values())
    if not all(isinstance(item, bool) for item in availability):
        return 0.0, False, False
    available = sum(item is True for item in availability)
    return available / len(availability), True, available == len(availability)


def apply_abstention_policy(
    forecast_direction: Any,
    confidence: Any,
    probabilities: Any = None,
    data_quality: Any = None,
    required_context_available: Any = None,
    liquidity: Any = None,
    suspension: Any = None,
    limit_move: Any = None,
    corporate_action: Any = None,
    history_count: Any = None,
    signal_conflict: Any = None,
    *,
    min_history_count: int = 20,
    min_liquidity: float = 1.0,
    conflict_threshold: float = 0.5,
) -> dict[str, Any]:
    """Apply the Phase 8 safety gates and return a JSON-serializable decision.

    ``required_context_available`` may be one boolean or a non-empty mapping of
    context names to booleans. ``liquidity`` is an explicitly supplied numeric
    measure compared with ``min_liquidity``. ``signal_conflict`` is a score in
    [0, 1] and abstains only when strictly above ``conflict_threshold``.
    """
    if isinstance(min_history_count, bool) or not isinstance(min_history_count, int) or min_history_count < 0:
        raise ValueError("min_history_count must be a non-negative integer")
    minimum_liquidity = _finite_number(min_liquidity)
    threshold = _unit_number(conflict_threshold)
    if minimum_liquidity is None or minimum_liquidity < 0:
        raise ValueError("min_liquidity must be a non-negative finite number")
    if threshold is None:
        raise ValueError("conflict_threshold must be a finite number in [0, 1]")

    reasons: list[str] = []
    direction = forecast_direction if forecast_direction in DIRECTIONS else None
    if forecast_direction is None:
        reasons.append("missing_forecast_direction")
    elif direction is None:
        reasons.append("invalid_forecast_direction")

    normalized_confidence = _unit_number(confidence)
    if confidence is None:
        reasons.append("missing_confidence")
    elif normalized_confidence is None:
        reasons.append("invalid_confidence")

    normalized_probabilities, probabilities_valid = _probabilities(probabilities)
    if not probabilities_valid:
        reasons.append("invalid_probabilities")

    quality_status = None
    if not isinstance(data_quality, Mapping):
        reasons.append("missing_data_quality" if data_quality is None else "invalid_data_quality")
    else:
        quality_status = data_quality.get("status")
        if quality_status is None:
            reasons.append("missing_data_quality_status")
        elif quality_status not in ("ok", "partial", "unavailable"):
            reasons.append("invalid_data_quality")
        elif quality_status == "unavailable":
            reasons.append("unavailable_data")
        elif quality_status == "partial":
            reasons.append("partial_data")
        for key, code in (("missing", "missing_data"), ("stale", "stale_data"),
                          ("invalid", "invalid_data"), ("partial", "partial_data"),
                          ("thin_liquidity", "inadequate_liquidity"),
                          ("suspension_warning", "suspension"),
                          ("limit_move_warning", "limit_move"),
                          ("corporate_action_warning", "corporate_action")):
            flag = data_quality.get(key, False)
            if not isinstance(flag, bool):
                reasons.append("invalid_data_quality")
            elif flag:
                reasons.append(code)

    coverage, context_valid, all_context = _context_coverage(required_context_available)
    if required_context_available is None:
        reasons.append("missing_required_context")
    elif not context_valid:
        reasons.append("invalid_required_context")
    elif not all_context:
        reasons.append("required_context_unavailable")

    liquidity_number = _finite_number(liquidity)
    if liquidity is None:
        reasons.append("missing_liquidity")
    elif liquidity_number is None or liquidity_number < 0:
        reasons.append("invalid_liquidity")
    elif liquidity_number < minimum_liquidity:
        reasons.append("inadequate_liquidity")

    if history_count is None:
        reasons.append("missing_history")
    elif isinstance(history_count, bool) or not isinstance(history_count, int) or history_count < 0:
        reasons.append("invalid_history")
    elif history_count < min_history_count:
        reasons.append("inadequate_history")

    for value, missing_code, active_code in (
        (suspension, "missing_suspension_flag", "suspension"),
        (limit_move, "missing_limit_move_flag", "limit_move"),
        (corporate_action, "missing_corporate_action_flag", "corporate_action"),
    ):
        if value is None:
            reasons.append(missing_code)
        elif not isinstance(value, bool):
            reasons.append("invalid_" + active_code + "_flag")
        elif value:
            reasons.append(active_code)

    conflict_number = _unit_number(signal_conflict)
    if signal_conflict is None:
        reasons.append("missing_signal_conflict")
    elif conflict_number is None:
        reasons.append("invalid_signal_conflict")
    elif conflict_number > threshold:
        reasons.append("signal_conflict")

    # A condition can be represented by both a status and a detailed flag. Keep
    # the first occurrence of every code while preserving gate order.
    reason_codes = list(dict.fromkeys(reasons))
    actionable = not reason_codes
    audit_inputs = {
        "forecast_direction": forecast_direction,
        "confidence": confidence,
        "probabilities": probabilities,
        "data_quality": data_quality,
        "required_context_available": required_context_available,
        "liquidity": liquidity,
        "suspension": suspension,
        "limit_move": limit_move,
        "corporate_action": corporate_action,
        "history_count": history_count,
        "signal_conflict": signal_conflict,
        "thresholds": {"min_history_count": min_history_count,
                       "min_liquidity": minimum_liquidity,
                       "conflict_threshold": threshold},
    }
    return {
        "decision": direction if actionable else "ABSTAIN",
        "status": "actionable" if actionable else "insufficient_data",
        "reason_codes": reason_codes,
        "coverage": round(coverage, 6),
        "confidence": normalized_confidence,
        "probabilities": normalized_probabilities,
        "audit_inputs": audit_inputs,
    }


decide_abstention = apply_abstention_policy
