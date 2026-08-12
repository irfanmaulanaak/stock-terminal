"""Deterministic, stdlib-only evaluation of checkpoint forecast snapshots."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CLASSES = ("UP", "FLAT", "DOWN")
NEXT_SLOT = {"open": "break", "break": "close", "close": "open"}
LEGACY_SLOTS = {
    "open": "open", "open_0901_wib": "open",
    "break": "break", "break_1201_wib": "break",
    "close": "close", "close_1601_wib": "close",
}


class EvaluationError(ValueError):
    """Raised when a snapshot cannot be evaluated without guessing."""


@dataclass(frozen=True)
class Snapshot:
    path: str
    snapshot_id: str
    slot: str
    threshold_pct: float | None
    stocks: Mapping[str, Mapping[str, Any]]
    benchmark_symbol: str | None
    benchmark_price: float | None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _slot(document: Mapping[str, Any]) -> str:
    metadata = document.get("archive_metadata")
    raw = metadata.get("slot") if isinstance(metadata, Mapping) else document.get("snapshot_slot")
    if raw not in LEGACY_SLOTS:
        raise EvaluationError(f"unsupported or missing snapshot slot: {raw!r}")
    return LEGACY_SLOTS[raw]


def _threshold(document: Mapping[str, Any]) -> float | None:
    for container, key in ((document, "actual_threshold_pct"), (document, "threshold_pct")):
        value = _number(container.get(key))
        if value is not None:
            if value < 0:
                raise EvaluationError("snapshot threshold must be non-negative")
            return value
    metadata = document.get("archive_metadata")
    if isinstance(metadata, Mapping):
        for key in ("actual_threshold_pct", "threshold_pct"):
            value = _number(metadata.get(key))
            if value is not None:
                if value < 0:
                    raise EvaluationError("snapshot threshold must be non-negative")
                return value
    return None


def _benchmark(document: Mapping[str, Any]) -> tuple[str | None, float | None]:
    benchmark = document.get("benchmark")
    if not isinstance(benchmark, Mapping):
        return None, None
    symbol = benchmark.get("symbol")
    symbol = symbol.strip().upper() if isinstance(symbol, str) and symbol.strip() else None
    price = _number(benchmark.get("baseline"))
    if price is None:
        price = _number(benchmark.get("displayed_price"))
    return symbol, price


def load_snapshot(path: str | Path) -> Snapshot:
    """Load either a Phase 0 archive or a legacy dashboard-style snapshot."""
    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"cannot load {source}: {exc}") from exc
    if not isinstance(document, Mapping):
        raise EvaluationError(f"{source}: snapshot root must be an object")
    raw_stocks = document.get("stocks")
    if not isinstance(raw_stocks, list):
        raise EvaluationError(f"{source}: stocks must be an array")
    stocks: dict[str, Mapping[str, Any]] = {}
    for index, stock in enumerate(raw_stocks):
        if not isinstance(stock, Mapping):
            raise EvaluationError(f"{source}: stocks[{index}] must be an object")
        symbol = stock.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            raise EvaluationError(f"{source}: stocks[{index}].symbol is required")
        symbol = symbol.strip().upper()
        if symbol in stocks:
            raise EvaluationError(f"{source}: duplicate symbol {symbol}")
        stocks[symbol] = stock
    metadata = document.get("archive_metadata")
    snapshot_id = metadata.get("snapshot_id") if isinstance(metadata, Mapping) else document.get("as_of")
    benchmark_symbol, benchmark_price = _benchmark(document)
    return Snapshot(str(source), str(snapshot_id or source.name), _slot(document), _threshold(document), stocks,
                    benchmark_symbol, benchmark_price)


def classify(return_pct: float, threshold_pct: float) -> str:
    if return_pct > threshold_pct:
        return "UP"
    if return_pct < -threshold_pct:
        return "DOWN"
    return "FLAT"


def _pct(numerator: int, denominator: int) -> float | None:
    return round(100.0 * numerator / denominator, 6) if denominator else None


def _metrics(rows: Sequence[Mapping[str, Any]], prediction_key: str) -> dict[str, Any]:
    matrix = {actual: {predicted: 0 for predicted in CLASSES} for actual in CLASSES}
    for row in rows:
        matrix[row["actual"]][row[prediction_key]] += 1
    per_class: dict[str, dict[str, float | int | None]] = {}
    recalls: list[float] = []
    f1s: list[float] = []
    for label in CLASSES:
        true_positive = matrix[label][label]
        actual_count = sum(matrix[label].values())
        predicted_count = sum(matrix[actual][label] for actual in CLASSES)
        precision = true_positive / predicted_count if predicted_count else None
        recall = true_positive / actual_count if actual_count else None
        f1 = (2 * true_positive / (actual_count + predicted_count)) if actual_count + predicted_count else None
        if recall is not None:
            recalls.append(recall)
        if f1 is not None:
            f1s.append(f1)
        per_class[label] = {
            "support": actual_count,
            "precision_pct": round(precision * 100, 6) if precision is not None else None,
            "recall_pct": round(recall * 100, 6) if recall is not None else None,
        }
    correct = sum(matrix[label][label] for label in CLASSES)
    return {
        "accuracy_pct": _pct(correct, len(rows)),
        "balanced_accuracy_pct": round(100 * sum(recalls) / len(recalls), 6) if recalls else None,
        "macro_f1_pct": round(100 * sum(f1s) / len(f1s), 6) if f1s else None,
        "per_class": per_class,
        "up_precision_pct": per_class["UP"]["precision_pct"],
        "up_recall_pct": per_class["UP"]["recall_pct"],
        "confusion_matrix": matrix,
    }


def evaluate_pairs(pairs: Iterable[tuple[str | Path, str | Path]]) -> dict[str, Any]:
    """Evaluate explicit (forecast, next-checkpoint) paths in supplied order."""
    rows: list[dict[str, Any]] = []
    pair_reports: list[dict[str, Any]] = []
    total_forecasts = 0
    for forecast_path, checkpoint_path in pairs:
        forecast = load_snapshot(forecast_path)
        checkpoint = load_snapshot(checkpoint_path)
        expected = NEXT_SLOT[forecast.slot]
        if checkpoint.slot != expected:
            raise EvaluationError(
                f"{forecast.path}: {forecast.slot} forecasts must pair with {expected}, not {checkpoint.slot}"
            )
        if forecast.threshold_pct is None:
            raise EvaluationError(f"{forecast.path}: snapshot threshold is required")
        total_forecasts += len(forecast.stocks)
        missing: list[str] = []
        invalid: list[str] = []
        pair_rows: list[dict[str, Any]] = []
        market_class = None
        if (forecast.benchmark_symbol and forecast.benchmark_symbol == checkpoint.benchmark_symbol
                and forecast.benchmark_price and checkpoint.benchmark_price is not None):
            market_return = (checkpoint.benchmark_price / forecast.benchmark_price - 1) * 100
            market_class = classify(market_return, forecast.threshold_pct)
        for symbol in sorted(forecast.stocks):
            predicted = forecast.stocks[symbol].get("forecast")
            baseline = _number(forecast.stocks[symbol].get("baseline"))
            target = _number(forecast.stocks[symbol].get("target_return_pct"))
            matched = checkpoint.stocks.get(symbol)
            realized_price = _number(matched.get("baseline")) if matched else None
            if matched is None:
                missing.append(symbol)
                continue
            if predicted not in CLASSES or baseline is None or baseline <= 0 or realized_price is None or target is None:
                invalid.append(symbol)
                continue
            realized = (realized_price / baseline - 1) * 100
            row = {
                "actual": classify(realized, forecast.threshold_pct),
                "forecast": predicted,
                "market_direction": market_class,
                "realized_return_pct": round(realized, 6),
                "symbol": symbol,
                "target_absolute_error_pct": round(abs(target - realized), 6),
                "target_return_pct": target,
            }
            rows.append(row)
            pair_rows.append(row)
        pair_reports.append({
            "checkpoint_path": checkpoint.path,
            "checkpoint_snapshot_id": checkpoint.snapshot_id,
            "checkpoint_slot": checkpoint.slot,
            "evaluated": len(pair_rows),
            "forecast_path": forecast.path,
            "forecast_snapshot_id": forecast.snapshot_id,
            "forecast_slot": forecast.slot,
            "horizon": f"{forecast.slot}_to_{checkpoint.slot}" if forecast.slot != "close" else "close_to_next_open",
            "invalid_symbols": invalid,
            "market_direction": market_class,
            "missing_symbols": missing,
            "status": "complete" if len(pair_rows) == len(forecast.stocks) else "pending",
            "threshold_pct": forecast.threshold_pct,
            "total_forecasts": len(forecast.stocks),
        })
    metrics = _metrics(rows, "forecast")
    metrics["target_mae_pct"] = round(sum(row["target_absolute_error_pct"] for row in rows) / len(rows), 6) if rows else None
    metrics["evaluated"] = len(rows)
    metrics["total_forecasts"] = total_forecasts
    metrics["coverage_pct"] = _pct(len(rows), total_forecasts)
    flat_rows = [dict(row, naive="FLAT") for row in rows]
    flat_metrics = _metrics(flat_rows, "naive")
    flat_metrics.update({"evaluated": len(rows), "coverage_pct": _pct(len(rows), len(rows))})
    baselines: dict[str, Any] = {"always_flat": flat_metrics}
    market_rows = [row for row in rows if row["market_direction"] is not None]
    if market_rows:
        market_metrics = _metrics(market_rows, "market_direction")
        market_metrics.update({"evaluated": len(market_rows), "coverage_pct": _pct(len(market_rows), len(rows))})
        baselines["market_direction"] = market_metrics
    else:
        baselines["market_direction"] = None
    return {
        "schema_version": "1.0",
        "classes": list(CLASSES),
        "metrics": metrics,
        "baselines": baselines,
        "pairs": pair_reports,
        "observations": rows,
    }


def render_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _display(value: Any) -> str:
    return "—" if value is None else str(value)


def render_markdown(report: Mapping[str, Any]) -> str:
    metrics = report["metrics"]
    lines = ["# Forecast snapshot evaluation", "", "## Summary", "",
             "| Metric | Value |", "|---|---:|",
             f"| Evaluated | {metrics['evaluated']} / {metrics['total_forecasts']} |",
             f"| Coverage | {_display(metrics['coverage_pct'])}% |",
             f"| Accuracy | {_display(metrics['accuracy_pct'])}% |",
             f"| Balanced accuracy | {_display(metrics['balanced_accuracy_pct'])}% |",
             f"| Macro-F1 | {_display(metrics['macro_f1_pct'])}% |",
             f"| UP precision | {_display(metrics['up_precision_pct'])}% |",
             f"| UP recall | {_display(metrics['up_recall_pct'])}% |",
             f"| Target MAE | {_display(metrics['target_mae_pct'])} pp |", "", "## Per class", "",
             "| Class | Support | Precision | Recall |", "|---|---:|---:|---:|"]
    for label in CLASSES:
        item = metrics["per_class"][label]
        lines.append(f"| {label} | {item['support']} | {_display(item['precision_pct'])}% | {_display(item['recall_pct'])}% |")
    lines += ["", "## Confusion matrix", "", "Rows are actual classes; columns are forecast classes.", "",
              "| Actual \\ Forecast | UP | FLAT | DOWN |", "|---|---:|---:|---:|"]
    for actual in CLASSES:
        row = metrics["confusion_matrix"][actual]
        lines.append(f"| {actual} | {row['UP']} | {row['FLAT']} | {row['DOWN']} |")
    lines += ["", "## Naive baselines", "", "| Baseline | Accuracy | Balanced accuracy | Macro-F1 |",
              "|---|---:|---:|---:|"]
    for name in ("always_flat", "market_direction"):
        item = report["baselines"][name]
        lines.append(f"| {name.replace('_', ' ')} | {_display(item['accuracy_pct'] if item else None)}% | {_display(item['balanced_accuracy_pct'] if item else None)}% | {_display(item['macro_f1_pct'] if item else None)}% |")
    lines += ["", "## Explicit pairs", "", "| Forecast | Checkpoint | Horizon | Evaluated | Status |",
              "|---|---|---|---:|---|"]
    for pair in report["pairs"]:
        lines.append(f"| `{pair['forecast_path']}` | `{pair['checkpoint_path']}` | {pair['horizon']} | {pair['evaluated']} / {pair['total_forecasts']} | {pair['status']} |")
    return "\n".join(lines) + "\n"
