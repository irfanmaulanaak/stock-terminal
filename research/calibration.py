"""Deterministic, standard-library-only Phase 12 probability calibration."""

from __future__ import annotations

from collections import defaultdict
import json
import math
from typing import Any, Callable, Iterable, Mapping, Sequence

from research.walk_forward import CLASSES, WalkForwardError, generate_folds, prepare_rows


CALIBRATION_VERSION = "phase12-1.0"
CALIBRATOR_METHODS = ("platt", "platt_temperature")
ProbabilitySource = Callable[[Sequence[Mapping[str, Any]], Mapping[str, Any], Mapping[str, Any]], Any]


def validate_probabilities(value: Any, *, tolerance: float = 1e-9) -> dict[str, float] | None:
    """Return canonical probabilities, or ``None`` when they are unsafe to use."""
    if not isinstance(value, Mapping) or set(value) != set(CLASSES):
        return None
    result: dict[str, float] = {}
    for label in CLASSES:
        item = value[label]
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        number = float(item)
        if not math.isfinite(number) or number < 0.0 or number > 1.0:
            return None
        result[label] = number
    if not math.isclose(sum(result.values()), 1.0, rel_tol=0.0, abs_tol=tolerance):
        return None
    return result


def _clip(value: float, epsilon: float = 1e-12) -> float:
    return min(1.0 - epsilon, max(epsilon, value))


def _logit(value: float) -> float:
    value = _clip(value)
    return math.log(value / (1.0 - value))


def _sigmoid(value: float) -> float:
    if value >= 0:
        exp = math.exp(-value)
        return 1.0 / (1.0 + exp)
    exp = math.exp(value)
    return exp / (1.0 + exp)


def _fit_binary(xs: Sequence[float], ys: Sequence[float], *, iterations: int,
                learning_rate: float, regularization: float) -> tuple[float, float]:
    slope = 0.0
    intercept = _logit((sum(ys) + 0.5) / (len(ys) + 1.0))
    for _ in range(iterations):
        probabilities = [_sigmoid(intercept + slope * x) for x in xs]
        gradient_slope = sum((p - y) * x for p, y, x in zip(probabilities, ys, xs)) / len(xs)
        gradient_intercept = sum(p - y for p, y in zip(probabilities, ys)) / len(xs)
        slope -= learning_rate * (gradient_slope + regularization * slope)
        intercept -= learning_rate * gradient_intercept
    return slope, intercept


def _temperature(probability_rows: Sequence[Mapping[str, float]], outcomes: Sequence[str],
                 *, iterations: int, learning_rate: float) -> float:
    log_temperature = 0.0
    for _ in range(iterations):
        temperature = math.exp(log_temperature)
        gradient = 0.0
        for probabilities, outcome in zip(probability_rows, outcomes):
            logits = [math.log(_clip(probabilities[label])) for label in CLASSES]
            scaled = [value / temperature for value in logits]
            peak = max(scaled)
            weights = [math.exp(value - peak) for value in scaled]
            total = sum(weights)
            expected = sum((weight / total) * logit for weight, logit in zip(weights, logits))
            gradient += (logits[CLASSES.index(outcome)] - expected) / temperature
        log_temperature -= learning_rate * gradient / len(outcomes)
        log_temperature = min(math.log(100.0), max(math.log(0.01), log_temperature))
    return math.exp(log_temperature)


def _row_probabilities(row: Mapping[str, Any], probability_field: str) -> Any:
    value = row.get(probability_field)
    if value is None and probability_field == "probabilities" and isinstance(row.get("prediction"), Mapping):
        value = row["prediction"].get("probabilities")
    return value


class FittedCalibrator:
    """Serializable one-vs-rest Platt calibrator with optional temperature scaling."""

    def __init__(self, metadata: Mapping[str, Any]):
        self.metadata = dict(metadata)

    def calibrate(self, probabilities: Any, *, horizon: Any = None) -> dict[str, Any]:
        canonical = validate_probabilities(probabilities)
        if canonical is None:
            return {"available": False, "probabilities": None, "decision": "ABSTAIN",
                    "reason": "invalid_probabilities"}
        key = str(horizon) if horizon is not None else "__all__"
        groups = self.metadata["groups"]
        parameters = groups.get(key)
        if parameters is None:
            return {"available": False, "probabilities": None, "decision": "ABSTAIN",
                    "reason": "calibrator_unavailable_for_horizon"}
        raw = {}
        for label in CLASSES:
            item = parameters["classes"][label]
            raw[label] = _sigmoid(item["intercept"] + item["slope"] * _logit(canonical[label]))
        total = sum(raw.values())
        if not math.isfinite(total) or total <= 0:
            return {"available": False, "probabilities": None, "decision": "ABSTAIN",
                    "reason": "invalid_calibrated_probabilities"}
        calibrated = {label: raw[label] / total for label in CLASSES}
        temperature = parameters.get("temperature", 1.0)
        if temperature != 1.0:
            logits = [math.log(_clip(calibrated[label])) / temperature for label in CLASSES]
            peak = max(logits)
            weights = [math.exp(value - peak) for value in logits]
            denominator = sum(weights)
            calibrated = {label: weights[index] / denominator for index, label in enumerate(CLASSES)}
        direction = max(CLASSES, key=lambda label: (calibrated[label], -CLASSES.index(label)))
        return {"available": True, "probabilities": calibrated, "decision": direction, "reason": None}

    predict = calibrate

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": "1.0", "metadata": self.metadata}

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":") if indent is None else None, indent=indent)

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "FittedCalibrator":
        if not isinstance(document, Mapping) or not isinstance(document.get("metadata"), Mapping):
            raise WalkForwardError("serialized calibrator must contain metadata")
        metadata = dict(document["metadata"])
        if metadata.get("version") != CALIBRATION_VERSION or metadata.get("method") not in CALIBRATOR_METHODS:
            raise WalkForwardError("unsupported serialized calibrator")
        return cls(metadata)

    @classmethod
    def from_json(cls, value: str) -> "FittedCalibrator":
        return cls.from_dict(json.loads(value))


def fit_calibrator(rows: Iterable[Mapping[str, Any]], *, probability_field: str = "probabilities",
                   horizon_field: str | None = "horizon", temperature_scaling: bool = False,
                   iterations: int = 500, learning_rate: float = 0.05,
                   regularization: float = 0.001) -> FittedCalibrator:
    """Fit OVR binary Platt models on chronological calibration rows only."""
    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 1:
        raise WalkForwardError("iterations must be a positive integer")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
           for v in (learning_rate, regularization)) or learning_rate == 0:
        raise WalkForwardError("learning_rate must be positive and regularization non-negative")
    data = prepare_rows(rows)
    grouped: dict[str, list[tuple[dict[str, float], str]]] = defaultdict(list)
    rejected = 0
    for row in data:
        probabilities = validate_probabilities(_row_probabilities(row, probability_field))
        if probabilities is None:
            rejected += 1
            continue
        key = str(row.get(horizon_field)) if horizon_field is not None and row.get(horizon_field) is not None else "__all__"
        grouped[key].append((probabilities, row["_direction"]))
    parameters: dict[str, Any] = {}
    for key in sorted(grouped):
        samples = grouped[key]
        classes = {}
        for label in CLASSES:
            slope, intercept = _fit_binary([_logit(item[0][label]) for item in samples],
                                           [float(item[1] == label) for item in samples],
                                           iterations=iterations, learning_rate=float(learning_rate),
                                           regularization=float(regularization))
            classes[label] = {"slope": slope, "intercept": intercept,
                              "positive_count": sum(item[1] == label for item in samples)}
        provisional = {"classes": classes, "temperature": 1.0}
        temporary = FittedCalibrator({"groups": {key: provisional}})
        platt_rows = [temporary.calibrate(item[0], horizon=None if key == "__all__" else key)["probabilities"] for item in samples]
        temp = _temperature(platt_rows, [item[1] for item in samples], iterations=iterations,
                            learning_rate=float(learning_rate)) if temperature_scaling else 1.0
        parameters[key] = {"row_count": len(samples), "classes": classes, "temperature": temp}
    metadata = {"version": CALIBRATION_VERSION,
                "method": "platt_temperature" if temperature_scaling else "platt",
                "classes": list(CLASSES), "probability_field": probability_field,
                "horizon_field": horizon_field, "iterations": iterations,
                "learning_rate": float(learning_rate), "regularization": float(regularization),
                "calibration_row_count": len(data), "fitted_row_count": len(data) - rejected,
                "rejected_probability_count": rejected, "groups": parameters}
    return FittedCalibrator(metadata)


def calibration_metrics(rows: Iterable[Mapping[str, Any]], *, bins: int = 10,
                        probability_field: str = "probabilities") -> dict[str, Any]:
    """Calculate proper scores, reliability, ECE, calibration coefficients, and coverage."""
    if isinstance(bins, bool) or not isinstance(bins, int) or bins < 1:
        raise WalkForwardError("bins must be a positive integer")
    items = list(rows)
    valid = []
    for row in items:
        probabilities = validate_probabilities(_row_probabilities(row, probability_field))
        actual = row.get("actual", row.get("outcome"))
        if isinstance(actual, Mapping):
            actual = actual.get("direction", actual.get("class"))
        if isinstance(actual, str):
            actual = actual.upper()
        if probabilities is not None and actual in CLASSES:
            valid.append((probabilities, actual))
    count = len(valid)
    reliability = []
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        members = [(max(p.values()), float(max(CLASSES, key=lambda label: (p[label], -CLASSES.index(label))) == y))
                   for p, y in valid if lower <= max(p.values()) and (max(p.values()) < upper or index == bins - 1)]
        reliability.append({"index": index, "lower": lower, "upper": upper, "count": len(members),
                            "mean_confidence": sum(x for x, _ in members) / len(members) if members else None,
                            "accuracy": sum(y for _, y in members) / len(members) if members else None})
    ece = sum(bucket["count"] / count * abs(bucket["mean_confidence"] - bucket["accuracy"])
              for bucket in reliability if bucket["count"]) if count else None
    per_class = {}
    for label in CLASSES:
        pairs = [(p[label], float(y == label)) for p, y in valid]
        brier = sum((p - y) ** 2 for p, y in pairs) / count if count else None
        slope = intercept = None
        if count and any(y == 1 for _, y in pairs) and any(y == 0 for _, y in pairs):
            slope, intercept = _fit_binary([_logit(p) for p, _ in pairs], [y for _, y in pairs],
                                           iterations=1000, learning_rate=0.03, regularization=0.0)
        per_class[label] = {"brier_score": brier, "log_loss": (-sum(y * math.log(_clip(p)) + (1-y) * math.log(_clip(1-p)) for p, y in pairs) / count) if count else None,
                            "calibration_slope": slope, "calibration_intercept": intercept,
                            "support": sum(y == label for _, y in valid)}
    return {"eligible": len(items), "evaluated": count, "rejected": len(items) - count,
            "coverage": count / len(items) if items else None,
            "coverage_pct": 100 * count / len(items) if items else None,
            "brier_score": sum(sum((p[label] - float(y == label)) ** 2 for label in CLASSES) for p, y in valid) / count if count else None,
            "multiclass_log_loss": -sum(math.log(_clip(p[y])) for p, y in valid) / count if count else None,
            "reliability_bins": reliability, "expected_calibration_error": ece,
            "per_class": per_class}


def _public(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def calibrate_walk_forward(rows: Iterable[Mapping[str, Any]], probability_source: Mapping[str, Any] | ProbabilitySource,
                           *, source_config: Mapping[str, Any] | None = None,
                           calibrator_config: Mapping[str, Any] | None = None,
                           bins: int = 10, **fold_config: Any) -> dict[str, Any]:
    """Fit source on train, calibrator on validation, and score untouched test rows."""
    data = prepare_rows(rows)
    folds = generate_folds(data, **fold_config)
    reports, predictions = [], []
    source_spec = dict(source_config or ({"name": getattr(probability_source, "__name__", "callback")} if callable(probability_source) else probability_source))
    for fold in folds:
        if callable(probability_source):
            predict = lambda row: probability_source([_public(item) for item in fold["train"]], _public(row), source_spec)
            source_metadata = {"type": "callback", "training_row_count": len(fold["train"])}
        else:
            from research.models import fit_model
            model = fit_model([_public(item) for item in fold["train"]], source_spec)
            predict = lambda row, fitted=model: fitted.predict(_public(row))
            source_metadata = model.metadata
        calibration_rows = []
        for row in fold["validation"]:
            output = predict(row)
            probabilities = output.get("probabilities") if isinstance(output, Mapping) and "probabilities" in output else output
            public = _public(row)
            public["probabilities"] = probabilities
            calibration_rows.append(public)
        calibrator = fit_calibrator(calibration_rows, **dict(calibrator_config or {}))
        fold_predictions = []
        for row in fold["test"]:
            output = predict(row)
            base = output.get("probabilities") if isinstance(output, Mapping) and "probabilities" in output else output
            calibrated = calibrator.calibrate(base, horizon=row.get("horizon"))
            prediction = {"fold": fold["index"], "row_id": row["_row_id"], "as_of": row["as_of"],
                          "actual": row["_direction"], "base_probabilities": validate_probabilities(base),
                          "probabilities": calibrated["probabilities"], "decision": calibrated["decision"],
                          "available": calibrated["available"], "reason": calibrated["reason"]}
            fold_predictions.append(prediction)
            predictions.append(prediction)
        reports.append({"index": fold["index"], "train_count": len(fold["train"]),
                        "validation_count": len(fold["validation"]), "test_count": len(fold["test"]),
                        "source_fit_split": "train", "calibrator_fit_split": "validation",
                        "evaluation_split": "test", "source_metadata": source_metadata,
                        "calibrator": calibrator.to_dict(), "metrics": calibration_metrics(fold_predictions, bins=bins)})
    return {"schema_version": "1.0", "calibration_version": CALIBRATION_VERSION,
            "classes": list(CLASSES), "probability_source": source_spec, "folds": reports,
            "predictions": predictions, "metrics": calibration_metrics(predictions, bins=bins)}


evaluate_calibration = calibration_metrics


def brier_score(rows: Iterable[Mapping[str, Any]], *, probability_field: str = "probabilities") -> float | None:
    """Return the multiclass Brier score for valid rows."""
    return calibration_metrics(rows, probability_field=probability_field)["brier_score"]


def multiclass_log_loss(rows: Iterable[Mapping[str, Any]], *, probability_field: str = "probabilities") -> float | None:
    """Return multiclass negative log likelihood for valid rows."""
    return calibration_metrics(rows, probability_field=probability_field)["multiclass_log_loss"]


def reliability_bins(rows: Iterable[Mapping[str, Any]], *, bins: int = 10,
                     probability_field: str = "probabilities") -> list[dict[str, Any]]:
    """Return equal-width top-label confidence reliability bins."""
    return calibration_metrics(rows, bins=bins, probability_field=probability_field)["reliability_bins"]


def expected_calibration_error(rows: Iterable[Mapping[str, Any]], *, bins: int = 10,
                               probability_field: str = "probabilities") -> float | None:
    """Return top-label expected calibration error."""
    return calibration_metrics(rows, bins=bins, probability_field=probability_field)["expected_calibration_error"]
