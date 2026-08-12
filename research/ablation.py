"""Deterministic, standard-library-only feature ablation experiments."""

from __future__ import annotations

from collections import defaultdict
import math
from typing import Any, Iterable, Mapping, Sequence

from research.walk_forward import BUILT_IN_PREDICTORS, WalkForwardError, evaluate_walk_forward


DEFAULT_METRIC = "macro_f1_pct"
DELTA_METRICS = ("accuracy_pct", "balanced_accuracy_pct", "macro_f1_pct", "coverage_pct")


def _number(value: Any, field: str, *, non_negative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise WalkForwardError(f"{field} must be a finite number")
    result = float(value)
    if non_negative and result < 0:
        raise WalkForwardError(f"{field} must be non-negative")
    return result


def _feature_groups(value: Any, field: str) -> dict[str, list[str]]:
    if not isinstance(value, Mapping) or not value:
        raise WalkForwardError(f"{field} must be a non-empty object")
    result: dict[str, list[str]] = {}
    seen: set[str] = set()
    for group, raw_features in value.items():
        if not isinstance(group, str) or not group:
            raise WalkForwardError(f"{field} group names must be non-empty strings")
        if isinstance(raw_features, str):
            features = [raw_features]
        elif isinstance(raw_features, Sequence) and not isinstance(raw_features, (str, bytes)):
            features = list(raw_features)
        else:
            raise WalkForwardError(f"{field}.{group} must be a feature-name array")
        if not features or any(not isinstance(name, str) or not name for name in features):
            raise WalkForwardError(f"{field}.{group} must contain non-empty feature names")
        if len(set(features)) != len(features):
            raise WalkForwardError(f"{field}.{group} contains duplicate features")
        duplicate = seen.intersection(features)
        if duplicate:
            raise WalkForwardError(f"features may belong to only one selected group: {sorted(duplicate)!r}")
        seen.update(features)
        result[group] = features
    return result


def _predictor_name(value: Any, field: str) -> tuple[str, dict[str, Any]]:
    if isinstance(value, str):
        spec = {"name": value}
    elif isinstance(value, Mapping):
        spec = dict(value)
    else:
        raise WalkForwardError(f"{field} must be a built-in predictor name or object")
    name = spec.get("name", spec.get("type"))
    if name not in BUILT_IN_PREDICTORS:
        raise WalkForwardError(f"{field} must name one of {BUILT_IN_PREDICTORS}")
    return name, spec


def _delta(value: Any, baseline: Any) -> float | None:
    if value is None or baseline is None:
        return None
    return round(float(value) - float(baseline), 6)


def _deltas(report: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, float | None]:
    return {name: _delta(report["metrics"].get(name), baseline["metrics"].get(name))
            for name in DELTA_METRICS}


def _stability(report: Mapping[str, Any], baseline: Mapping[str, Any], metric: str) -> dict[str, Any]:
    baseline_folds = {fold["index"]: fold for fold in baseline["folds"]}
    folds = []
    values = []
    improved = 0
    for fold in report["folds"]:
        value = fold["metrics"].get(metric)
        base_value = baseline_folds[fold["index"]]["metrics"].get(metric)
        change = _delta(value, base_value)
        if value is not None:
            values.append(float(value))
        if change is not None and change > 0:
            improved += 1
        folds.append({"fold": fold["index"], "metric": value, "baseline_metric": base_value,
                      "delta": change, "coverage_pct": fold["coverage_pct"]})
    return {
        "metric": metric, "folds": folds, "fold_count": len(folds),
        "folds_improved": improved,
        "mean": round(sum(values) / len(values), 6) if values else None,
        "minimum": round(min(values), 6) if values else None,
        "maximum": round(max(values), 6) if values else None,
        "range": round(max(values) - min(values), 6) if values else None,
    }


def _feature_sign_callback(groups: Mapping[str, Sequence[str]], thresholds: Any):
    if thresholds is None:
        threshold_map: Mapping[str, Any] = {}
        decision_threshold = 0.0
    elif isinstance(thresholds, (int, float)) and not isinstance(thresholds, bool):
        threshold_map = {}
        decision_threshold = _number(thresholds, "thresholds", non_negative=True)
    elif isinstance(thresholds, Mapping):
        threshold_map = thresholds.get("features", thresholds)
        if not isinstance(threshold_map, Mapping):
            raise WalkForwardError("thresholds.features must be an object")
        decision_threshold = _number(thresholds.get("decision", thresholds.get("score", 0)),
                                     "thresholds.decision", non_negative=True)
    else:
        raise WalkForwardError("thresholds must be a non-negative number or object")
    feature_names = [feature for features in groups.values() for feature in features]
    unknown = set(threshold_map).difference(feature_names).difference({"decision", "score", "features"})
    if unknown:
        raise WalkForwardError(f"thresholds contains unknown features: {sorted(unknown)!r}")
    feature_thresholds = {name: _number(threshold_map.get(name, 0), f"thresholds.{name}", non_negative=True)
                          for name in feature_names}

    def predict(_train: Sequence[Mapping[str, Any]], row: Mapping[str, Any], _config: Mapping[str, Any]):
        features = row.get("features")
        if not isinstance(features, Mapping):
            return {"direction": None}
        vector = []
        for name in feature_names:
            value = features.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                return {"direction": None}
            threshold = feature_thresholds[name]
            vector.append(1 if value > threshold else -1 if value < -threshold else 0)
        score = sum(vector) / len(vector)
        return {"direction": "UP" if score > decision_threshold else
                "DOWN" if score < -decision_threshold else "FLAT"}

    return predict, feature_names, feature_thresholds, decision_threshold


def run_ablation_experiments(rows: Iterable[Mapping[str, Any]],
                             experiments: Sequence[Mapping[str, Any]], *,
                             folds: Mapping[str, Any],
                             baseline_predictor: Mapping[str, Any] | str = "previous_direction",
                             metric: str = DEFAULT_METRIC,
                             splits: Sequence[str] = ("test",)) -> dict[str, Any]:
    """Run ordered ablations on identical Phase 9 walk-forward folds.

    ``feature_sign`` signs every selected feature after its optional per-feature
    dead-band, then signs the mean vector score.  A row missing any selected
    feature is deliberately not predicted.
    """
    if not isinstance(folds, Mapping):
        raise WalkForwardError("folds must be an object")
    if not isinstance(experiments, Sequence) or isinstance(experiments, (str, bytes)) or not experiments:
        raise WalkForwardError("experiments must be a non-empty ordered array")
    if metric not in DELTA_METRICS[:-1]:
        raise WalkForwardError(f"metric must be one of {DELTA_METRICS[:-1]}")
    data = list(rows)
    baseline_name, baseline_spec = _predictor_name(baseline_predictor, "baseline_predictor")
    naive = evaluate_walk_forward(data, {"name": "always_flat"}, splits=splits, **dict(folds))
    baseline = evaluate_walk_forward(data, baseline_spec, splits=splits, **dict(folds))
    results = []
    names: set[str] = set()
    contributions: dict[str, list[float]] = defaultdict(list)
    for index, raw in enumerate(experiments):
        if not isinstance(raw, Mapping):
            raise WalkForwardError(f"experiments[{index}] must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise WalkForwardError("experiment names must be unique non-empty strings")
        names.add(name)
        groups = _feature_groups(raw.get("feature_groups"), f"experiments[{index}].feature_groups")
        predictor_name, predictor_spec = _predictor_name(raw.get("predictor"), f"experiments[{index}].predictor")
        if predictor_name == "feature_sign":
            callback, feature_names, feature_thresholds, decision_threshold = _feature_sign_callback(groups, raw.get("thresholds"))
            descriptor = {"name": "feature_sign", "feature_groups": groups,
                          "features": feature_names, "feature_thresholds": feature_thresholds,
                          "decision_threshold": decision_threshold}
            report = evaluate_walk_forward(data, callback, predictor_config=descriptor,
                                           splits=splits, **dict(folds))
        else:
            feature_names = [feature for values in groups.values() for feature in values]
            report = evaluate_walk_forward(data, predictor_spec, splits=splits, **dict(folds))
        changes = _deltas(report, baseline)
        group_changes = {group: changes[metric] for group in groups}
        for group, value in group_changes.items():
            if value is not None:
                contributions[group].append(value)
        results.append({
            "index": index, "name": name, "feature_groups": groups,
            "selected_features": feature_names, "predictor": report["predictor"],
            "thresholds": raw.get("thresholds"), "metrics": report["metrics"],
            "coverage_pct": report["coverage_pct"], "deltas_from_baseline": changes,
            "stability_by_fold": _stability(report, baseline, metric),
            "grouped_metrics": report["grouped_metrics"], "folds": report["folds"],
            "feature_group_contributions": group_changes,
        })
    baseline_value = baseline["metrics"].get(metric)
    eligible_winners = [result for result in results if result["metrics"].get(metric) is not None
                        and baseline_value is not None and result["metrics"][metric] > baseline_value]
    winner = max(eligible_winners, key=lambda result: (result["metrics"][metric], -result["index"])) if eligible_winners else None
    summaries = []
    for group in sorted(contributions):
        values = contributions[group]
        summaries.append({"group": group, "experiment_count": len(values),
                          f"mean_{metric}_delta": round(sum(values) / len(values), 6),
                          f"best_{metric}_delta": round(max(values), 6)})
    return {
        "schema_version": "1.0", "phase": 10,
        "metadata": {"experiment_count": len(results), "experiment_order": [item["name"] for item in results],
                     "metric": metric, "splits": list(splits), "fold_config": dict(folds),
                     "baseline_predictor": baseline["predictor"], "naive_predictor": naive["predictor"]},
        "naive_always_flat": {"metrics": naive["metrics"], "coverage_pct": naive["coverage_pct"],
                              "grouped_metrics": naive["grouped_metrics"]},
        "baseline": {"name": baseline_name, "predictor": baseline["predictor"],
                     "metrics": baseline["metrics"], "coverage_pct": baseline["coverage_pct"],
                     "grouped_metrics": baseline["grouped_metrics"]},
        "experiments": results,
        "feature_group_contribution_summary": summaries,
        "winner": ({"name": winner["name"], "metric": metric,
                    "value": winner["metrics"][metric], "baseline_value": baseline_value,
                    "improvement": winner["deltas_from_baseline"][metric]} if winner else None),
    }


run_ablations = run_ablation_experiments
