"""Chronological, dependency-free walk-forward evaluation utilities."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import math
from typing import Any, Callable, Iterable, Mapping, Sequence

CLASSES = ("UP", "FLAT", "DOWN")
GROUP_FIELDS = ("horizon", "regime", "sector", "liquidity", "confidence")


class WalkForwardError(ValueError):
    """Raised when an evaluation cannot be performed without guessing."""


Predictor = Callable[[Sequence[Mapping[str, Any]], Mapping[str, Any], Mapping[str, Any]], Any]


def _timestamp(value: Any, field: str = "as_of") -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise WalkForwardError(f"{field} must be a timezone-aware ISO-8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise WalkForwardError(f"{field} must be a timezone-aware ISO-8601 string") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise WalkForwardError(f"{field} must be timezone-aware")
    return result


def _seconds(value: Any, field: str, *, allow_zero: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise WalkForwardError(f"{field} must be a finite number of seconds")
    value = float(value)
    if value < 0 or (not allow_zero and value == 0):
        raise WalkForwardError(f"{field} must be {'positive' if not allow_zero else 'non-negative'}")
    return value


def _outcome(row: Mapping[str, Any]) -> tuple[str, float | None]:
    raw = row.get("outcome")
    target = row.get("target")
    if isinstance(raw, Mapping):
        direction = raw.get("direction", raw.get("class"))
        target = raw.get("target", raw.get("value", target))
    else:
        direction = raw
    if isinstance(direction, str):
        direction = direction.upper()
    if direction not in CLASSES:
        raise WalkForwardError(f"outcome must be one of {CLASSES}")
    if target is not None:
        if isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target):
            raise WalkForwardError("numeric outcome target must be finite")
        target = float(target)
    return direction, target


def prepare_rows(rows: Iterable[Mapping[str, Any]], *, id_field: str = "id",
                 reject_duplicate_ids: bool = True,
                 reject_duplicate_timestamps: bool = False) -> list[dict[str, Any]]:
    """Validate and chronologically sort rows, without randomization."""
    prepared: list[dict[str, Any]] = []
    seen_ids: set[Any] = set()
    seen_times: set[datetime] = set()
    for index, source in enumerate(rows):
        if not isinstance(source, Mapping):
            raise WalkForwardError(f"rows[{index}] must be an object")
        row = dict(source)
        moment = _timestamp(row.get("as_of"), f"rows[{index}].as_of")
        features = row.get("features")
        if not isinstance(features, Mapping):
            raise WalkForwardError(f"rows[{index}].features must be an object")
        direction, target = _outcome(row)
        row_id = row.get(id_field)
        if row_id is None:
            row_id = row.get("row_id") if id_field == "id" else None
        if row_id is None:
            row_id = row.get("as_of")
        try:
            duplicate_id = row_id in seen_ids
        except TypeError as exc:
            raise WalkForwardError(f"rows[{index}].{id_field} must be JSON-scalar") from exc
        if reject_duplicate_ids and duplicate_id:
            raise WalkForwardError(f"duplicate row ID: {row_id!r}")
        if reject_duplicate_timestamps and moment in seen_times:
            raise WalkForwardError(f"duplicate timestamp: {row['as_of']!r}")
        seen_ids.add(row_id)
        seen_times.add(moment)
        row["_time"] = moment
        row["_row_id"] = row_id
        row["_direction"] = direction
        row["_target"] = target
        prepared.append(row)
    prepared.sort(key=lambda item: (item["_time"], str(item["_row_id"])))
    return prepared


def _horizon_end(row: Mapping[str, Any]) -> datetime:
    explicit = row.get("horizon_end")
    if explicit is not None:
        return _timestamp(explicit, "horizon_end")
    horizon = row.get("horizon_seconds")
    if horizon is None and isinstance(row.get("horizon"), (int, float)):
        horizon = row["horizon"]
    return row["_time"] + timedelta(seconds=_seconds(horizon, "horizon", allow_zero=True)) if horizon is not None else row["_time"]


def generate_folds(rows: Iterable[Mapping[str, Any]], *, train_end: str,
                   validation_seconds: float, test_seconds: float,
                   step_seconds: float | None = None, mode: str = "expanding",
                   train_seconds: float | None = None, purge_seconds: float = 0,
                   embargo_seconds: float = 0, fold_count: int | None = None,
                   id_field: str = "id", reject_duplicate_ids: bool = True,
                   reject_duplicate_timestamps: bool = False) -> list[dict[str, Any]]:
    """Generate chronological expanding or rolling folds from an initial train end."""
    data = prepare_rows(rows, id_field=id_field, reject_duplicate_ids=reject_duplicate_ids,
                        reject_duplicate_timestamps=reject_duplicate_timestamps)
    if mode not in ("expanding", "rolling"):
        raise WalkForwardError("mode must be 'expanding' or 'rolling'")
    validation_seconds = _seconds(validation_seconds, "validation_seconds", allow_zero=False)
    test_seconds = _seconds(test_seconds, "test_seconds", allow_zero=False)
    step_seconds = _seconds(step_seconds if step_seconds is not None else test_seconds,
                            "step_seconds", allow_zero=False)
    purge_seconds = _seconds(purge_seconds, "purge_seconds")
    embargo_seconds = _seconds(embargo_seconds, "embargo_seconds")
    if mode == "rolling" and train_seconds is None:
        raise WalkForwardError("rolling mode requires train_seconds")
    train_span = _seconds(train_seconds, "train_seconds", allow_zero=False) if train_seconds is not None else None
    if fold_count is not None and (isinstance(fold_count, bool) or not isinstance(fold_count, int) or fold_count < 1):
        raise WalkForwardError("fold_count must be a positive integer")
    boundary = _timestamp(train_end, "train_end")
    latest = data[-1]["_time"] if data else None
    folds: list[dict[str, Any]] = []
    while fold_count is None or len(folds) < fold_count:
        validation_start = boundary
        validation_end = validation_start + timedelta(seconds=validation_seconds)
        test_start = validation_end + timedelta(seconds=embargo_seconds)
        test_end = test_start + timedelta(seconds=test_seconds)
        if latest is None or (fold_count is None and test_start > latest):
            break
        train_start = boundary - timedelta(seconds=train_span) if train_span is not None else None
        train_cutoff = validation_start - timedelta(seconds=purge_seconds)
        train_candidates = [row for row in data if (train_start is None or row["_time"] >= train_start)
                            and row["_time"] < train_cutoff]
        train = [row for row in train_candidates if _horizon_end(row) <= validation_start]
        validation_candidates = [row for row in data if validation_start <= row["_time"] < validation_end]
        validation = [row for row in validation_candidates if _horizon_end(row) <= test_start]
        test = [row for row in data if test_start <= row["_time"] < test_end]
        folds.append({
            "index": len(folds), "mode": mode, "train_start": train_start,
            "train_end": boundary, "validation_start": validation_start,
            "validation_end": validation_end, "test_start": test_start, "test_end": test_end,
            "purge_seconds": purge_seconds, "embargo_seconds": embargo_seconds,
            "train": train, "validation": validation, "test": test,
            "purged_train_count": len(train_candidates) - len(train),
            "purged_validation_count": len(validation_candidates) - len(validation),
        })
        boundary += timedelta(seconds=step_seconds)
    return folds


def generate_walk_forward_folds(rows: Iterable[Mapping[str, Any]], **config: Any) -> list[dict[str, Any]]:
    """Public descriptive alias for :func:`generate_folds`."""
    return generate_folds(rows, **config)


def _built_in_predict(spec: Mapping[str, Any], train: Sequence[Mapping[str, Any]],
                      row: Mapping[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    name = spec.get("name", spec.get("type"))
    if name == "always_flat":
        direction = "FLAT"
    elif name == "majority_train":
        counts = Counter(item["_direction"] for item in train)
        direction = max(CLASSES, key=lambda label: (counts[label], -CLASSES.index(label))) if train else "FLAT"
    elif name == "previous_direction":
        prior = [item for item in train if item["_time"] < row["_time"]]
        direction = prior[-1]["_direction"] if prior else "FLAT"
    elif name == "feature_sign":
        feature = spec.get("feature")
        if not isinstance(feature, str) or not feature:
            raise WalkForwardError("feature_sign requires an explicit feature")
        value = row["features"].get(feature)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return {"direction": None, "target": None}
        threshold = _seconds(spec.get("threshold", 0), "predictor threshold")
        direction = "UP" if value > threshold else "DOWN" if value < -threshold else "FLAT"
    else:
        raise WalkForwardError(f"unknown built-in predictor: {name!r}")
    target = spec.get("target")
    return {"direction": direction, "target": float(target) if isinstance(target, (int, float)) and not isinstance(target, bool) else None}


def _metric_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    matrix = {actual: {predicted: 0 for predicted in CLASSES} for actual in CLASSES}
    for row in rows:
        matrix[row["actual"]][row["predicted"]] += 1
    recalls, f1s = [], []
    for label in CLASSES:
        tp = matrix[label][label]
        actual = sum(matrix[label].values())
        predicted = sum(matrix[key][label] for key in CLASSES)
        if actual:
            recalls.append(tp / actual)
        if actual + predicted:
            f1s.append(2 * tp / (actual + predicted))
    correct = sum(matrix[label][label] for label in CLASSES)
    target_errors = [abs(row["predicted_target"] - row["actual_target"]) for row in rows
                     if row.get("predicted_target") is not None and row.get("actual_target") is not None]
    pct = lambda value: round(100 * value, 6)
    return {
        "evaluated": len(rows), "accuracy_pct": pct(correct / len(rows)) if rows else None,
        "three_way_accuracy_pct": pct(correct / len(rows)) if rows else None,
        "balanced_accuracy_pct": pct(sum(recalls) / len(recalls)) if recalls else None,
        "macro_f1_pct": pct(sum(f1s) / len(f1s)) if f1s else None,
        "confusion_matrix": matrix,
        "target_mae": round(sum(target_errors) / len(target_errors), 6) if target_errors else None,
        "target_evaluated": len(target_errors),
    }


def _public_time(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def evaluate_walk_forward(rows: Iterable[Mapping[str, Any]], predictor: Mapping[str, Any] | Predictor,
                          *, predictor_config: Mapping[str, Any] | None = None,
                          splits: Sequence[str] = ("test",), **fold_config: Any) -> dict[str, Any]:
    """Evaluate a JSON predictor spec or deterministic callback over chronological folds.

    Callbacks receive ``(public_train_rows, public_row, predictor_config)`` and return a
    class string or ``{direction, target}``.  Callback identity is serialized from
    ``predictor_config`` (or its function name), never from the callable itself.
    """
    data = prepare_rows(rows, id_field=fold_config.get("id_field", "id"),
                        reject_duplicate_ids=fold_config.get("reject_duplicate_ids", True),
                        reject_duplicate_timestamps=fold_config.get("reject_duplicate_timestamps", False))
    folds = generate_folds(data, **fold_config)
    if any(split not in ("validation", "test") for split in splits) or not splits:
        raise WalkForwardError("splits must contain validation and/or test")
    if callable(predictor):
        spec = dict(predictor_config or {"name": getattr(predictor, "__name__", "callback")})
        callback = predictor
    elif isinstance(predictor, Mapping):
        spec = dict(predictor)
        callback = None
    else:
        raise WalkForwardError("predictor must be a JSON object or callback")
    predictions: list[dict[str, Any]] = []
    fold_reports = []
    state: dict[str, Any] = {}
    for fold in folds:
        fold_predictions = []
        public_train = [_public_row(row) for row in fold["train"]]
        for split in splits:
            for row in fold[split]:
                raw = callback(public_train, _public_row(row), spec) if callback else _built_in_predict(spec, fold["train"], row, state)
                raw = {"direction": raw} if isinstance(raw, str) else raw
                if not isinstance(raw, Mapping):
                    raise WalkForwardError("predictor must return a class string or object")
                direction = raw.get("direction", raw.get("prediction"))
                if isinstance(direction, str):
                    direction = direction.upper()
                if direction is None:
                    continue
                if direction not in CLASSES:
                    raise WalkForwardError(f"predictor returned invalid direction: {direction!r}")
                target = raw.get("target")
                if target is not None and (isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target)):
                    raise WalkForwardError("predictor target must be finite")
                prediction = {"fold": fold["index"], "split": split, "row_id": row["_row_id"],
                              "as_of": row["as_of"], "actual": row["_direction"], "predicted": direction,
                              "actual_target": row["_target"], "predicted_target": float(target) if target is not None else None}
                for field in GROUP_FIELDS:
                    if field in row:
                        prediction[field] = row[field]
                    elif isinstance(row.get("group"), Mapping) and field in row["group"]:
                        prediction[field] = row["group"][field]
                predictions.append(prediction)
                fold_predictions.append(prediction)
        eligible = sum(len(fold[split]) for split in splits)
        fold_reports.append({
            "index": fold["index"], "mode": fold["mode"],
            "train_start": _public_time(fold["train_start"]), "train_end": _public_time(fold["train_end"]),
            "validation_start": _public_time(fold["validation_start"]), "validation_end": _public_time(fold["validation_end"]),
            "test_start": _public_time(fold["test_start"]), "test_end": _public_time(fold["test_end"]),
            "purge_seconds": fold["purge_seconds"], "embargo_seconds": fold["embargo_seconds"],
            "train_count": len(fold["train"]), "validation_count": len(fold["validation"]), "test_count": len(fold["test"]),
            "purged_train_count": fold["purged_train_count"], "purged_validation_count": fold["purged_validation_count"],
            "eligible": eligible, "predicted": len(fold_predictions),
            "coverage_pct": round(100 * len(fold_predictions) / eligible, 6) if eligible else None,
            "metrics": _metric_rows(fold_predictions),
        })
    eligible_total = sum(report["eligible"] for report in fold_reports)
    grouped: dict[str, Any] = {}
    for field in GROUP_FIELDS:
        values = sorted({str(row[field]) for row in predictions if field in row})
        if values:
            grouped[field] = {value: _metric_rows([row for row in predictions if str(row.get(field)) == value]) for value in values}
    metrics = _metric_rows(predictions)
    metrics["coverage_pct"] = round(100 * len(predictions) / eligible_total, 6) if eligible_total else None
    metrics["eligible"] = eligible_total
    return {"schema_version": "1.0", "classes": list(CLASSES), "predictor": spec,
            "folds": fold_reports, "predictions": predictions, "metrics": metrics,
            "coverage_pct": metrics["coverage_pct"], "grouped_metrics": grouped}


def _public_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


BUILT_IN_PREDICTORS = ("always_flat", "previous_direction", "majority_train", "feature_sign")
