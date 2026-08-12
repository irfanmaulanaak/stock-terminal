"""Deterministic, read-only operational checks for research artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from research.archive import validate_manifest
from research.contract import SLOTS, ValidationError, validate_snapshot

DEFAULT_FORECAST_MAX_AGE_SECONDS = 18 * 60 * 60
DEFAULT_VERIFICATION_MAX_AGE_SECONDS = 48 * 60 * 60
DEFAULT_QUOTE_MAX_AGE_SECONDS = 15 * 60


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def _age(value: Any, now: datetime) -> float | None:
    parsed = _timestamp(value)
    return max(0.0, (now - parsed.astimezone(timezone.utc)).total_seconds()) if parsed else None


def _read_json(path: Path | None) -> tuple[Any, str | None]:
    if path is None or not path.is_file():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "invalid"


def _issue(level: str, code: str, message: str) -> dict[str, str]:
    return {"level": level, "code": code, "message": message}


def _slot(value: Any) -> str | None:
    if value in SLOTS:
        return value
    if isinstance(value, str):
        for candidate in SLOTS:
            if value.lower().startswith(candidate):
                return candidate
    return None


def operations_health(
    *, forecast_path: str | Path | None = None, verification_path: str | Path | None = None,
    archive_dir: str | Path | None = None, manifest_path: str | Path | None = None,
    required_slots: Iterable[str] = SLOTS, now: datetime | None = None,
    forecast_max_age_seconds: int = DEFAULT_FORECAST_MAX_AGE_SECONDS,
    verification_max_age_seconds: int = DEFAULT_VERIFICATION_MAX_AGE_SECONDS,
    quote_max_age_seconds: int = DEFAULT_QUOTE_MAX_AGE_SECONDS,
    research_sources: Mapping[str, bool | None] | None = None,
) -> dict[str, Any]:
    """Return stable health fields and codes without changing or fetching data."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    issues: list[dict[str, str]] = []
    forecast_file = Path(forecast_path) if forecast_path else None
    forecast, forecast_error = _read_json(forecast_file)
    forecast_age = _age(forecast.get("as_of") if isinstance(forecast, Mapping) else None, current)
    if forecast_error == "missing":
        issues.append(_issue("error", "FORECAST_MISSING", "Forecast snapshot is not available."))
    elif forecast_error:
        issues.append(_issue("error", "FORECAST_INVALID_JSON", "Forecast snapshot is not valid JSON."))
    elif forecast_age is None:
        issues.append(_issue("error", "FORECAST_TIMESTAMP_INVALID", "Forecast as_of is missing or invalid."))
    elif forecast_age > forecast_max_age_seconds:
        issues.append(_issue("warning", "FORECAST_STALE", "Forecast snapshot exceeds the configured maximum age."))

    stocks = forecast.get("stocks") if isinstance(forecast, Mapping) else None
    stocks = stocks if isinstance(stocks, list) else []
    declared = forecast.get("universe_count") if isinstance(forecast, Mapping) else None
    consistent = isinstance(declared, int) and not isinstance(declared, bool) and declared == len(stocks)
    if forecast is not None and not consistent:
        issues.append(_issue("error", "UNIVERSE_COUNT_MISMATCH", "Declared universe_count does not match the stocks array."))
    quote_ages = [s.get("quote_freshness_seconds") for s in stocks if isinstance(s, Mapping)]
    valid_quote_ages = [float(v) for v in quote_ages if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0]
    stale_quotes = sum(v > quote_max_age_seconds for v in valid_quote_ages)
    missing_quotes = len(stocks) - len(valid_quote_ages)
    if stale_quotes:
        issues.append(_issue("warning", "STALE_QUOTES", "One or more saved quote observations are stale."))
    if missing_quotes:
        issues.append(_issue("warning", "QUOTE_AGE_MISSING", "One or more symbols lack quote freshness metadata."))

    verification_file = Path(verification_path) if verification_path else None
    verification, verification_error = _read_json(verification_file)
    verification_age = None
    evaluation_status = "unavailable"
    evaluated = None
    if verification_error == "missing":
        issues.append(_issue("warning", "VERIFICATION_MISSING", "Verification report is not available."))
    elif verification_error:
        issues.append(_issue("error", "VERIFICATION_INVALID_JSON", "Verification report is not valid JSON."))
    else:
        flat = verification if isinstance(verification, Mapping) else {}
        metrics = flat.get("metrics") if isinstance(flat.get("metrics"), Mapping) else flat
        evaluated = metrics.get("evaluated") if isinstance(metrics, Mapping) else None
        evaluation_status = "available" if isinstance(evaluated, (int, float)) and evaluated > 0 else "pending"
        if evaluation_status == "pending":
            issues.append(_issue("warning", "VERIFICATION_PENDING", "Verification has no evaluated outcomes."))
        verification_age = _age(flat.get("generated_at") or flat.get("generatedAt") or flat.get("as_of"), current)
        if verification_age is None and verification_file:
            verification_age = max(0.0, current.timestamp() - verification_file.stat().st_mtime)
        if verification_age > verification_max_age_seconds:
            issues.append(_issue("warning", "VERIFICATION_STALE", "Verification report exceeds the configured maximum age."))

    expected_slots = tuple(required_slots)
    found_slots: set[str] = set()
    schema_valid = True
    archive_root = Path(archive_dir) if archive_dir else None
    if archive_root is not None:
        if not archive_root.is_dir():
            schema_valid = False
            issues.append(_issue("error", "ARCHIVE_MISSING", "Archive directory is not available."))
        else:
            for path in sorted(archive_root.glob("*.json")):
                if path.name == "manifest.json" or (manifest_path and path.resolve() == Path(manifest_path).resolve()):
                    continue
                document, error = _read_json(path)
                if error:
                    schema_valid = False
                    issues.append(_issue("error", "ARCHIVE_JSON_INVALID", "An archive checkpoint is not valid JSON."))
                    continue
                try:
                    validate_snapshot(document)
                    found_slots.add(document["archive_metadata"]["slot"])
                except (ValidationError, KeyError, TypeError):
                    schema_valid = False
                    issues.append(_issue("error", "ARCHIVE_SCHEMA_INVALID", "An archive checkpoint violates schema 1.0."))
            missing_slots = [slot for slot in expected_slots if slot not in found_slots]
            if missing_slots:
                issues.append(_issue("error", "CHECKPOINT_SLOTS_MISSING", "Required checkpoint slots are missing."))
    else:
        missing_slots = list(expected_slots)
        issues.append(_issue("warning", "ARCHIVE_NOT_SUPPLIED", "Archive checks were not configured."))

    manifest_valid = None
    if manifest_path:
        manifest, manifest_error = _read_json(Path(manifest_path))
        if manifest_error:
            manifest_valid = False
            issues.append(_issue("error", "ARCHIVE_MANIFEST_INVALID", "Archive manifest is missing or invalid."))
        elif archive_root is None:
            manifest_valid = False
            issues.append(_issue("error", "ARCHIVE_DIR_REQUIRED", "Manifest validation requires an archive directory."))
        else:
            try:
                validate_manifest(archive_root, manifest)
                manifest_valid = True
            except (OSError, ValueError):
                manifest_valid = False
                issues.append(_issue("error", "ARCHIVE_MANIFEST_INVALID", "Archive contents do not match the manifest."))

    sources = []
    for name, available in sorted((research_sources or {}).items()):
        status = "available" if available is True else "unavailable" if available is False else "unknown"
        sources.append({"name": name, "status": status})
        if available is False:
            issues.append(_issue("warning", "RESEARCH_SOURCE_UNAVAILABLE", f"Research source {name} is unavailable."))

    return {
        "status": "error" if any(i["level"] == "error" for i in issues) else "warning" if issues else "healthy",
        "forecastSource": {"status": "available" if forecast is not None else "unavailable"},
        "latestSnapshot": {"status": "unavailable" if forecast is None else "stale" if forecast_age is not None and forecast_age > forecast_max_age_seconds else "available", "asOf": forecast.get("as_of") if isinstance(forecast, Mapping) else None, "ageSeconds": round(forecast_age, 3) if forecast_age is not None else None, "maxAgeSeconds": forecast_max_age_seconds, "slot": _slot(forecast.get("snapshot_slot")) if isinstance(forecast, Mapping) else None},
        "verification": {"status": evaluation_status, "ageSeconds": round(verification_age, 3) if verification_age is not None else None, "maxAgeSeconds": verification_max_age_seconds, "evaluated": evaluated},
        "dataQuality": {"universeCount": len(stocks), "declaredUniverseCount": declared, "universeCountConsistent": consistent, "quoteAgeObservedCount": len(valid_quote_ages), "staleQuoteCount": stale_quotes, "missingQuoteAgeCount": missing_quotes, "staleAfterSeconds": quote_max_age_seconds},
        "archive": {"status": "unavailable" if archive_root is None else "valid" if schema_valid and not missing_slots and manifest_valid is not False else "invalid", "requiredSlots": list(expected_slots), "availableSlots": sorted(found_slots), "missingSlots": missing_slots, "schemaValid": schema_valid if archive_root is not None else None, "manifestValid": manifest_valid},
        "researchUpstream": {"status": "not_checked" if not sources else "available" if all(s["status"] == "available" for s in sources) else "degraded", "sources": sources},
        "warnings": issues,
        "generatedAt": current.isoformat().replace("+00:00", "Z"),
    }
