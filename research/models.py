"""Transparent, deterministic, standard-library-only Phase 11 models."""

from __future__ import annotations

from collections import Counter
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from research.walk_forward import (CLASSES, WalkForwardError, evaluate_walk_forward,
                                   generate_folds, prepare_rows)


MODEL_VERSION = "phase11-1.0"
MODEL_NAMES = ("always_flat", "majority_train", "feature_sign",
               "multinomial_logistic", "ridge")


def _finite(value: Any) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def _features(spec: Mapping[str, Any], *, required: bool) -> list[str]:
    raw = spec.get("feature_names", spec.get("features", spec.get("feature")))
    if isinstance(raw, str):
        raw = [raw]
    if raw is None and not required:
        return []
    if (not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or not raw
            or any(not isinstance(name, str) or not name for name in raw)):
        raise WalkForwardError("model requires non-empty feature_names")
    names = list(raw)
    if len(set(names)) != len(names):
        raise WalkForwardError("feature_names must not contain duplicates")
    return names


def _number(value: Any, name: str, *, minimum: float | None = None) -> float:
    if not _finite(value):
        raise WalkForwardError(f"{name} must be a finite number")
    result = float(value)
    if minimum is not None and result < minimum:
        raise WalkForwardError(f"{name} must be at least {minimum}")
    return result


def _integer(value: Any, name: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise WalkForwardError(f"{name} must be an integer of at least {minimum}")
    return value


def _vector(row: Mapping[str, Any], names: Sequence[str]) -> list[float] | None:
    values = row.get("features")
    if not isinstance(values, Mapping):
        return None
    result = []
    for name in names:
        value = values.get(name)
        if not _finite(value):
            return None
        result.append(float(value))
    return result


def _standardizer(vectors: Sequence[Sequence[float]]) -> tuple[list[float], list[float]]:
    count = len(vectors)
    width = len(vectors[0]) if vectors else 0
    means = [sum(row[j] for row in vectors) / count for j in range(width)]
    scales = []
    for j, mean in enumerate(means):
        scale = math.sqrt(sum((row[j] - mean) ** 2 for row in vectors) / count)
        scales.append(scale if scale > 0 else 1.0)
    return means, scales


def _standardize(vector: Sequence[float], means: Sequence[float], scales: Sequence[float]) -> list[float]:
    return [(value - means[index]) / scales[index] for index, value in enumerate(vector)]


def _softmax(values: Sequence[float]) -> list[float]:
    peak = max(values)
    exponents = [math.exp(value - peak) for value in values]
    total = sum(exponents)
    return [value / total for value in exponents]


def _solve(matrix: list[list[float]], values: list[float]) -> list[float]:
    """Solve a small dense system with deterministic partial pivoting."""
    size = len(values)
    augmented = [list(matrix[i]) + [values[i]] for i in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: (abs(augmented[row][column]), -row))
        if abs(augmented[pivot][column]) < 1e-15:
            raise WalkForwardError("ridge system is singular; use positive regularization")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [current - factor * source
                              for current, source in zip(augmented[row], augmented[column])]
    return [augmented[row][-1] for row in range(size)]


class FittedModel:
    """JSON-friendly fitted model with explicit parameters and prediction outputs."""

    def __init__(self, metadata: Mapping[str, Any]):
        self.metadata = dict(metadata)

    @property
    def model_type(self) -> str:
        return self.metadata["model_type"]

    def predict(self, row: Mapping[str, Any]) -> dict[str, Any]:
        name = self.model_type
        probabilities: dict[str, float] | None = None
        scores: dict[str, float] | None = None
        direction: str | None = None
        target: float | None = None
        if name == "always_flat":
            direction = "FLAT"
            probabilities = {label: float(label == direction) for label in CLASSES}
            scores = dict(probabilities)
        elif name == "majority_train":
            probabilities = dict(self.metadata["class_probabilities"])
            scores = dict(self.metadata["class_counts"])
            direction = self.metadata["direction"]
        else:
            vector = _vector(row, self.metadata["feature_names"])
            if vector is None:
                return {"available": False, "probabilities": None, "scores": None,
                        "direction": None, "target": None,
                        "reason": "missing_or_non_numeric_feature"}
            if name == "feature_sign":
                thresholds = self.metadata["feature_thresholds"]
                signed = [1 if value > thresholds[index] else
                          -1 if value < -thresholds[index] else 0
                          for index, value in enumerate(vector)]
                score = sum(signed) / len(signed)
                limit = self.metadata["decision_threshold"]
                direction = "UP" if score > limit else "DOWN" if score < -limit else "FLAT"
                scores = {"UP": score, "FLAT": -abs(score), "DOWN": -score}
                probabilities = {label: float(label == direction) for label in CLASSES}
            elif name == "multinomial_logistic":
                standardized = _standardize(vector, self.metadata["means"], self.metadata["scales"])
                logits = [self.metadata["intercepts"][k] +
                          sum(coefficient * value for coefficient, value in
                              zip(self.metadata["coefficients"][k], standardized))
                          for k in range(len(CLASSES))]
                probability_values = _softmax(logits)
                scores = {label: logits[index] for index, label in enumerate(CLASSES)}
                probabilities = {label: probability_values[index] for index, label in enumerate(CLASSES)}
                direction = max(CLASSES, key=lambda label: (probabilities[label], -CLASSES.index(label)))
            elif name == "ridge":
                standardized = _standardize(vector, self.metadata["means"], self.metadata["scales"])
                target = self.metadata["intercepts"][0] + sum(
                    coefficient * value for coefficient, value in
                    zip(self.metadata["coefficients"][0], standardized))
                limit = self.metadata["decision_threshold"]
                direction = "UP" if target > limit else "DOWN" if target < -limit else "FLAT"
                scores = {"target_return": target}
            else:  # defensive check for deserialized documents
                raise WalkForwardError(f"unknown fitted model: {name!r}")
        return {"available": True, "probabilities": probabilities, "scores": scores,
                "direction": direction, "target": target, "reason": None}

    predict_one = predict

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": "1.0", "metadata": dict(self.metadata)}

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":") if indent is None else None, indent=indent)

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "FittedModel":
        if not isinstance(document, Mapping) or not isinstance(document.get("metadata"), Mapping):
            raise WalkForwardError("serialized model must contain metadata")
        metadata = dict(document["metadata"])
        if metadata.get("version") != MODEL_VERSION or metadata.get("model_type") not in MODEL_NAMES:
            raise WalkForwardError("unsupported serialized model")
        return cls(metadata)

    @classmethod
    def from_json(cls, value: str) -> "FittedModel":
        return cls.from_dict(json.loads(value))


def fit_model(rows: Iterable[Mapping[str, Any]], model: str | Mapping[str, Any],
              **overrides: Any) -> FittedModel:
    """Fit one transparent model after chronologically sorting training rows only."""
    spec = {"name": model} if isinstance(model, str) else dict(model)
    spec.update(overrides)
    name = spec.get("name", spec.get("type"))
    aliases = {"logistic": "multinomial_logistic", "logistic_regression": "multinomial_logistic",
               "multinomial_logistic_regression": "multinomial_logistic",
               "ridge_regression": "ridge", "ridge_linear_regression": "ridge"}
    name = aliases.get(name, name)
    if name not in MODEL_NAMES:
        raise WalkForwardError(f"unknown model: {name!r}")
    data = prepare_rows(rows)
    required = name in ("feature_sign", "multinomial_logistic", "ridge")
    names = _features(spec, required=required)
    regularization = _number(spec.get("regularization", spec.get("l2", 0.01)),
                             "regularization", minimum=0)
    iterations = _integer(spec.get("iterations", 500), "iterations")
    metadata: dict[str, Any] = {
        "version": MODEL_VERSION, "model_type": name, "feature_names": names,
        "means": [], "scales": [], "coefficients": [], "intercepts": [],
        "regularization": regularization, "iterations": 0,
        "training_row_count": len(data), "fitted_row_count": len(data),
    }
    if name == "always_flat":
        metadata["direction"] = "FLAT"
    elif name == "majority_train":
        counts = Counter(row["_direction"] for row in data)
        direction = max(CLASSES, key=lambda label: (counts[label], -CLASSES.index(label))) if data else "FLAT"
        total = sum(counts.values())
        metadata["class_counts"] = {label: counts[label] for label in CLASSES}
        metadata["class_probabilities"] = {
            label: counts[label] / total if total else float(label == "FLAT") for label in CLASSES}
        metadata["direction"] = direction
    elif name == "feature_sign":
        raw_thresholds = spec.get("feature_thresholds", spec.get("thresholds", 0))
        if isinstance(raw_thresholds, Mapping):
            thresholds = [_number(raw_thresholds.get(feature, 0), f"thresholds.{feature}", minimum=0)
                          for feature in names]
        else:
            threshold = _number(raw_thresholds, "thresholds", minimum=0)
            thresholds = [threshold] * len(names)
        metadata["feature_thresholds"] = thresholds
        metadata["decision_threshold"] = _number(spec.get("decision_threshold", 0),
                                                  "decision_threshold", minimum=0)
    else:
        examples = []
        for row in data:
            vector = _vector(row, names)
            outcome = row.get("target_return", row["_target"]) if name == "ridge" else row["_direction"]
            if name == "ridge" and outcome is not None and not _finite(outcome):
                raise WalkForwardError("target_return must be finite")
            if vector is not None and outcome is not None:
                examples.append((vector, outcome))
        if not examples:
            raise WalkForwardError("no complete training rows for model")
        vectors = [item[0] for item in examples]
        means, scales = _standardizer(vectors)
        matrix = [_standardize(vector, means, scales) for vector in vectors]
        metadata["means"], metadata["scales"] = means, scales
        metadata["fitted_row_count"] = len(examples)
        if name == "multinomial_logistic":
            rate = _number(spec.get("learning_rate", 0.1), "learning_rate", minimum=0)
            if rate == 0:
                raise WalkForwardError("learning_rate must be positive")
            coefficients = [[0.0] * len(names) for _ in CLASSES]
            intercepts = [0.0] * len(CLASSES)
            for _ in range(iterations):
                gradient_w = [[0.0] * len(names) for _ in CLASSES]
                gradient_b = [0.0] * len(CLASSES)
                for vector, (_, actual) in zip(matrix, examples):
                    logits = [intercepts[k] + sum(coefficients[k][j] * vector[j]
                              for j in range(len(names))) for k in range(len(CLASSES))]
                    probabilities = _softmax(logits)
                    for k, label in enumerate(CLASSES):
                        error = probabilities[k] - float(actual == label)
                        gradient_b[k] += error
                        for j in range(len(names)):
                            gradient_w[k][j] += error * vector[j]
                count = len(matrix)
                for k in range(len(CLASSES)):
                    intercepts[k] -= rate * gradient_b[k] / count
                    for j in range(len(names)):
                        gradient = gradient_w[k][j] / count + regularization * coefficients[k][j]
                        coefficients[k][j] -= rate * gradient
            metadata.update({"coefficients": coefficients, "intercepts": intercepts,
                             "iterations": iterations, "learning_rate": rate,
                             "training_method": "batch_softmax_gradient_descent"})
        else:
            width = len(names) + 1
            normal = [[0.0] * width for _ in range(width)]
            right = [0.0] * width
            for vector, (_, target) in zip(matrix, examples):
                design = [1.0] + vector
                for i in range(width):
                    right[i] += design[i] * float(target)
                    for j in range(width):
                        normal[i][j] += design[i] * design[j]
            for index in range(1, width):
                normal[index][index] += regularization * len(matrix)
            solution = _solve(normal, right)
            metadata.update({"coefficients": [solution[1:]], "intercepts": [solution[0]],
                             "target_name": "target_return",
                             "decision_threshold": _number(spec.get("decision_threshold", 0),
                                                           "decision_threshold", minimum=0),
                             "training_method": "ridge_normal_equations"})
    return FittedModel(metadata)


fit = fit_model
deserialize_model = FittedModel.from_json


def predict_model(model: FittedModel, row: Mapping[str, Any]) -> dict[str, Any]:
    return model.predict(row)


def fit_always_flat(rows: Iterable[Mapping[str, Any]]) -> FittedModel:
    return fit_model(rows, "always_flat")


def fit_majority_train(rows: Iterable[Mapping[str, Any]]) -> FittedModel:
    return fit_model(rows, "majority_train")


def fit_feature_sign(rows: Iterable[Mapping[str, Any]], feature_names: Sequence[str],
                     **config: Any) -> FittedModel:
    return fit_model(rows, {"name": "feature_sign", "feature_names": list(feature_names), **config})


def fit_multinomial_logistic(rows: Iterable[Mapping[str, Any]], feature_names: Sequence[str],
                             **config: Any) -> FittedModel:
    return fit_model(rows, {"name": "multinomial_logistic",
                            "feature_names": list(feature_names), **config})


fit_multinomial_logistic_regression = fit_multinomial_logistic


def fit_ridge(rows: Iterable[Mapping[str, Any]], feature_names: Sequence[str],
              **config: Any) -> FittedModel:
    return fit_model(rows, {"name": "ridge", "feature_names": list(feature_names), **config})


fit_ridge_regression = fit_ridge


def serialize_model(model: FittedModel, *, indent: int | None = None) -> str:
    return model.to_json(indent=indent)


def compare_models(rows: Iterable[Mapping[str, Any]], models: Sequence[str | Mapping[str, Any]], *,
                   folds: Mapping[str, Any], splits: Sequence[str] = ("test",)) -> dict[str, Any]:
    """Compare models with Phase 9 folds, fitting once on each fold's train rows."""
    if not isinstance(folds, Mapping):
        raise WalkForwardError("folds must be an object")
    if not isinstance(models, Sequence) or isinstance(models, (str, bytes)) or not models:
        raise WalkForwardError("models must be a non-empty array")
    source = list(rows)
    phase9_folds = generate_folds(source, **dict(folds))
    results = []
    for index, raw_spec in enumerate(models):
        spec = {"name": raw_spec} if isinstance(raw_spec, str) else dict(raw_spec)
        label = spec.get("label", spec.get("name", spec.get("type")))
        cache: dict[tuple[Any, ...], FittedModel] = {}
        fitted = []
        for fold in phase9_folds:
            key = tuple(item.get("id", item.get("row_id", item.get("as_of")))
                        for item in fold["train"])
            if key not in cache:
                cache[key] = fit_model(fold["train"], spec)
            fitted.append({"fold": fold["index"], **cache[key].metadata})

        def callback(train: Sequence[Mapping[str, Any]], row: Mapping[str, Any], _config: Mapping[str, Any]):
            key = tuple(item.get("id", item.get("row_id", item.get("as_of"))) for item in train)
            prediction = cache[key].predict(row)
            return {"direction": prediction["direction"], "target": prediction["target"]}

        descriptor = {key: value for key, value in spec.items() if key != "label"}
        report = evaluate_walk_forward(source, callback, predictor_config=descriptor,
                                       splits=splits, **dict(folds))
        results.append({"index": index, "name": label, "spec": descriptor,
                        "metrics": report["metrics"], "coverage_pct": report["coverage_pct"],
                        "grouped_metrics": report["grouped_metrics"], "folds": report["folds"],
                        "predictions": report["predictions"], "fit_metadata_by_fold": fitted})
    return {"schema_version": "1.0", "phase": 11,
            "metadata": {"model_count": len(results), "model_order": [item["name"] for item in results],
                         "fold_config": dict(folds), "splits": list(splits), "version": MODEL_VERSION},
            "models": results}


run_model_comparison = compare_models
model_comparison = compare_models
