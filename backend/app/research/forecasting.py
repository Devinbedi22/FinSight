"""Leakage-conscious price-only forecasting experiments, separate from live APIs."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from app.services.market_context import calculate_market_context

DATASET_SCHEMA_VERSION = "finsight.forecast.dataset.v1"
EXPERIMENT_SCHEMA_VERSION = "finsight.forecast.experiment.v1"
HORIZONS = (5, 20)
FEATURE_NAMES = (
    "close_sma20_gap", "close_sma50_gap", "close_sma200_gap",
    "sma20_sma50_gap", "sma50_sma200_gap",
    "close_ema12_gap", "close_ema26_gap", "close_ema50_gap",
    "ema12_ema26_gap", "rsi_14", "macd_close_ratio", "macd_signal_close_ratio",
    "macd_histogram_close_ratio", "bollinger_position", "atr_close_ratio",
    "historical_volatility_20d", "volume_vs_20d_average", "momentum_20d",
    "momentum_252d", "relative_return_20d_vs_sp500", "correlation_20d_vs_sp500",
    "relative_volatility_20d_vs_sp500", "relative_return_20d_vs_sector",
    "relative_volatility_20d_vs_sector", "regime_uptrend", "regime_downtrend",
    "regime_sideways", "regime_high_volatility", "regime_low_volatility",
    "regime_insufficient_history",
)
FEATURE_DEFINITIONS = {
    "close_sma20_gap": "Adjusted anchor close / SMA20 - 1",
    "close_sma50_gap": "Adjusted anchor close / SMA50 - 1",
    "close_sma200_gap": "Adjusted anchor close / SMA200 - 1",
    "sma20_sma50_gap": "SMA20 / SMA50 - 1",
    "sma50_sma200_gap": "SMA50 / SMA200 - 1",
    "close_ema12_gap": "Adjusted anchor close / EMA12 - 1",
    "close_ema26_gap": "Adjusted anchor close / EMA26 - 1",
    "close_ema50_gap": "Adjusted anchor close / EMA50 - 1",
    "ema12_ema26_gap": "EMA12 / EMA26 - 1",
    "rsi_14": "Wilder 14-session RSI on adjusted closes, 0–100",
    "macd_close_ratio": "MACD line / adjusted anchor close",
    "macd_signal_close_ratio": "MACD signal line / adjusted anchor close",
    "macd_histogram_close_ratio": "MACD histogram / adjusted anchor close",
    "bollinger_position": "(anchor close - lower band) / (upper band - lower band)",
    "atr_close_ratio": "Wilder ATR14 / adjusted anchor close",
    "historical_volatility_20d": "Sample standard deviation of 20 daily returns × sqrt(252)",
    "volume_vs_20d_average": "Anchor volume / trailing 20-session mean volume",
    "momentum_20d": "Anchor adjusted close / adjusted close 20 sessions earlier - 1",
    "momentum_252d": "Anchor adjusted close / adjusted close 252 sessions earlier - 1",
    "relative_return_20d_vs_sp500": "Stock 20-session return minus S&P 500 proxy return on common sessions",
    "correlation_20d_vs_sp500": "Pearson correlation of daily returns on latest 20 common sessions",
    "relative_volatility_20d_vs_sp500": "Stock return standard deviation / S&P 500 proxy standard deviation",
    "relative_return_20d_vs_sector": "Stock 20-session return minus mapped sector ETF proxy return",
    "relative_volatility_20d_vs_sector": "Stock return standard deviation / mapped sector ETF proxy standard deviation",
    "regime_uptrend": "1 when Phase 4 observable regime label is uptrend, otherwise 0",
    "regime_downtrend": "1 when Phase 4 observable regime label is downtrend, otherwise 0",
    "regime_sideways": "1 when Phase 4 observable regime label is sideways, otherwise 0",
    "regime_high_volatility": "1 when Phase 4 observable regime label is high volatility, otherwise 0",
    "regime_low_volatility": "1 when Phase 4 observable regime label is low volatility, otherwise 0",
    "regime_insufficient_history": "1 when Phase 4 regime criteria lack sufficient history, otherwise 0",
}


def _bar_map(points: list[dict]) -> dict[str, dict]:
    return {str(point["date"]): point for point in points if point.get("date")}


def _number(metric: dict | None) -> float | None:
    value = metric.get("value") if metric else None
    return float(value) if isinstance(value, (float, int)) and math.isfinite(value) else None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator - 1


def _make_features(context: dict, close: float) -> dict[str, float | None]:
    metrics = context["indicators"]
    values = {key: _number(metrics.get(key)) for key in metrics}
    lower, upper = values["bollinger_lower"], values["bollinger_upper"]
    band_width = upper - lower if upper is not None and lower is not None else None
    regime = context["regime"]["label"]
    features = {
        "close_sma20_gap": _ratio(close, values["sma_20"]),
        "close_sma50_gap": _ratio(close, values["sma_50"]),
        "close_sma200_gap": _ratio(close, values["sma_200"]),
        "sma20_sma50_gap": _ratio(values["sma_20"], values["sma_50"]),
        "sma50_sma200_gap": _ratio(values["sma_50"], values["sma_200"]),
        "close_ema12_gap": _ratio(close, values["ema_12"]),
        "close_ema26_gap": _ratio(close, values["ema_26"]),
        "close_ema50_gap": _ratio(close, values["ema_50"]),
        "ema12_ema26_gap": _ratio(values["ema_12"], values["ema_26"]),
        "rsi_14": values["rsi_14"],
        "macd_close_ratio": values["macd"] / close if values["macd"] is not None and close else None,
        "macd_signal_close_ratio": values["macd_signal"] / close if values["macd_signal"] is not None and close else None,
        "macd_histogram_close_ratio": values["macd_histogram"] / close if values["macd_histogram"] is not None and close else None,
        "bollinger_position": (close - lower) / band_width if band_width not in (None, 0) else None,
        "atr_close_ratio": values["atr_14"] / close if values["atr_14"] is not None and close else None,
        "historical_volatility_20d": values["historical_volatility_20d"],
        "volume_vs_20d_average": values["volume_vs_20d_average"],
        "momentum_20d": values["momentum_20d"],
        "momentum_252d": values["momentum_252d"],
        "relative_return_20d_vs_sp500": values["relative_return_20d_vs_sp500"],
        "correlation_20d_vs_sp500": values["correlation_20d_vs_sp500"],
        "relative_volatility_20d_vs_sp500": values["relative_volatility_20d_vs_sp500"],
        "relative_return_20d_vs_sector": values["relative_return_20d_vs_sector"],
        "relative_volatility_20d_vs_sector": values["relative_volatility_20d_vs_sector"],
    }
    features.update({
        "regime_uptrend": float(regime == "uptrend"),
        "regime_downtrend": float(regime == "downtrend"),
        "regime_sideways": float(regime == "sideways"),
        "regime_high_volatility": float(regime == "high_volatility"),
        "regime_low_volatility": float(regime == "low_volatility"),
        "regime_insufficient_history": float(regime == "insufficient_history"),
    })
    return {name: features.get(name) for name in FEATURE_NAMES}


def _targets(
    anchor: dict, future_stock: list[dict], benchmark_by_date: dict[str, dict], horizons: tuple[int, ...],
) -> dict[str, dict]:
    result = {}
    for horizon in horizons:
        future = future_stock[:horizon]
        stock_return = benchmark_return = excess_return = None
        start_date = end_date = None
        if len(future) >= horizon and future[0].get("open") not in (None, 0) and future[-1].get("close") is not None:
            start_date, end_date = str(future[0]["date"]), str(future[-1]["date"])
            stock_return = float(future[-1]["close"]) / float(future[0]["open"]) - 1
            benchmark_start = benchmark_by_date.get(start_date, {}).get("open")
            benchmark_end = benchmark_by_date.get(end_date, {}).get("close")
            if benchmark_start not in (None, 0) and benchmark_end is not None:
                benchmark_return = float(benchmark_end) / float(benchmark_start) - 1
                excess_return = stock_return - benchmark_return
        result[str(horizon)] = {
            "stock_return": stock_return,
            "benchmark_return": benchmark_return,
            "excess_return": excess_return,
            "stock_direction": (1 if stock_return > 0 else 0) if stock_return not in (None, 0) else None,
            "excess_direction": (1 if excess_return > 0 else 0) if excess_return not in (None, 0) else None,
            "target_start_date": start_date,
            "target_end_date": end_date,
            "entry_method": "next trading session adjusted open",
            "exit_method": f"{horizon}th future trading session adjusted close",
        }
    return result


def build_point_in_time_dataset(
    ticker: str,
    stock_points: list[dict],
    benchmark_points: list[dict],
    sector_points: list[dict] | None = None,
    *, sector: str | None = None,
    horizons: tuple[int, ...] = HORIZONS,
    minimum_history: int = 253,
    start_date: date | None = None,
    end_date: date | None = None,
    data_source: str = "Yahoo Finance via yfinance; caller-supplied adjusted daily OHLCV",
    benchmark_ticker: str = "^GSPC",
    benchmark_source: str = "Yahoo Finance via yfinance (^GSPC S&P 500 index proxy)",
) -> dict:
    """Build anchor rows; each feature call sees only bars through that anchor."""
    stock = sorted((dict(p) for p in stock_points if p.get("date")), key=lambda p: p["date"])
    benchmark = sorted((dict(p) for p in benchmark_points if p.get("date")), key=lambda p: p["date"])
    sectors = sorted((dict(p) for p in (sector_points or []) if p.get("date")), key=lambda p: p["date"])
    benchmark_by_date = _bar_map(benchmark)
    max_horizon = max(horizons)
    rows = []
    for index in range(max(0, minimum_history - 1), len(stock) - max_horizon):
        anchor = stock[index]
        anchor_day = date.fromisoformat(anchor["date"])
        if start_date and anchor_day < start_date or end_date and anchor_day > end_date:
            continue
        close = anchor.get("close")
        if close is None:
            continue
        history = stock[: index + 1]
        benchmark_history = [bar for bar in benchmark if bar["date"] <= anchor["date"]]
        sector_history = [bar for bar in sectors if bar["date"] <= anchor["date"]]
        context = calculate_market_context(
            ticker, history, benchmark_history, as_of=anchor_day, sector=sector,
            sector_points=sector_history, benchmark_ticker=benchmark_ticker,
            benchmark_source=benchmark_source,
        )
        rows.append({
            "ticker": ticker.upper(), "sector": sector,
            "forecast_anchor_date": anchor["date"],
            "information_cutoff": f"{anchor['date']} after session close, when that daily bar is available",
            "feature_as_of_date": context["as_of_date"],
            "feature_observation_date": context["latest_observation_date"],
            "feature_source": context["source"],
            "benchmark": context["benchmark"],
            "market_regime": context["regime"]["label"],
            "features": _make_features(context, float(close)),
            "targets": _targets(anchor, stock[index + 1 :], benchmark_by_date, horizons),
        })
    return {
        "schema_version": DATASET_SCHEMA_VERSION,
        "ticker": ticker.upper(), "sector": sector,
        "data_source": data_source,
        "benchmark": {"ticker": benchmark_ticker, "source": benchmark_source},
        "price_adjustment": "Caller supplies auto-adjusted daily OHLCV; adjusted open is used for entry and adjusted close for exit.",
        "feature_names": list(FEATURE_NAMES),
        "feature_definitions": FEATURE_DEFINITIONS,
        "horizons_trading_sessions": list(horizons),
        "minimum_feature_history_sessions": minimum_history,
        "row_count": len(rows), "rows": rows,
        "limitations": [
            "Yahoo Finance history can be revised for splits, distributions, and provider corrections; historical vintages are not available here.",
            "A caller using the current S&P 500 list may introduce survivorship and membership look-ahead; this dataset builder does not infer historical membership.",
            "News sentiment and SEC fundamentals are excluded because true historical availability was not established for these samples.",
            "Missing feature and target values remain null; any imputation is confined to a training-fold preprocessor.",
            "Overlapping out-of-sample target windows create dependent observations; independence-based confidence intervals are not reported.",
        ],
    }


class TrainOnlyPreprocessor:
    """Median imputation and standardization fitted solely from supplied training rows."""

    def __init__(self, feature_names: tuple[str, ...] = FEATURE_NAMES):
        self.feature_names = feature_names
        self.medians: dict[str, float] = {}
        self.means: dict[str, float] = {}
        self.scales: dict[str, float] = {}
        self.active_features: list[str] = []
        self.fitted = False

    def fit(self, rows: list[dict]) -> "TrainOnlyPreprocessor":
        self.active_features = []
        for name in self.feature_names:
            observed = [float(row["features"][name]) for row in rows if row["features"].get(name) is not None and math.isfinite(float(row["features"][name]))]
            if not observed:
                continue
            median = float(np.median(observed))
            filled = np.asarray([float(row["features"][name]) if row["features"].get(name) is not None else median for row in rows], dtype=float)
            mean_value = float(filled.mean())
            scale = float(filled.std(ddof=0))
            if scale == 0 or not math.isfinite(scale):
                scale = 1.0
            self.active_features.append(name)
            self.medians[name], self.means[name], self.scales[name] = median, mean_value, scale
        self.fitted = True
        return self

    def transform(self, rows: list[dict]) -> np.ndarray:
        if not self.fitted:
            raise RuntimeError("Preprocessor must be fitted on training rows before transform")
        if not self.active_features:
            return np.zeros((len(rows), 0), dtype=float)
        matrix = []
        for row in rows:
            values = []
            for name in self.active_features:
                raw = row["features"].get(name)
                value = float(raw) if raw is not None and math.isfinite(float(raw)) else self.medians[name]
                values.append((value - self.means[name]) / self.scales[name])
            matrix.append(values)
        return np.asarray(matrix, dtype=float)


def purged_walk_forward_splits(
    rows: list[dict], horizon: int, target_name: str,
    *, initial_train_fraction: float = 0.60, block_fraction: float = 0.10,
) -> list[dict[str, list[int]]]:
    """Expanding chronological folds; purge labels ending on/after next block start."""
    ordered = sorted(enumerate(rows), key=lambda pair: pair[1]["forecast_anchor_date"])
    n = len(ordered)
    block = max(1, int(n * block_fraction))
    first_test = max(3 * block, int(n * initial_train_fraction))
    splits = []
    for test_start in range(first_test, n, block):
        validation_start = test_start - block
        validation_end = test_start
        test_end = min(n, test_start + block)
        validation_anchor = ordered[validation_start][1]["forecast_anchor_date"]
        test_anchor = ordered[test_start][1]["forecast_anchor_date"]
        train = [original for original, row in ordered[:validation_start]
                 if row["targets"][str(horizon)].get(target_name) is not None
                 and row["targets"][str(horizon)].get("target_end_date") < validation_anchor]
        validation = [original for original, row in ordered[validation_start:validation_end]
                      if row["targets"][str(horizon)].get(target_name) is not None
                      and row["targets"][str(horizon)].get("target_end_date") < test_anchor]
        test = [original for original, row in ordered[test_start:test_end]
                if row["targets"][str(horizon)].get(target_name) is not None]
        if train and validation and test:
            splits.append({"train": train, "validation": validation, "test": test})
    return splits


def _targets_for(rows: list[dict], indices: list[int], horizon: int, target_name: str) -> np.ndarray:
    return np.asarray([float(rows[index]["targets"][str(horizon)][target_name]) for index in indices], dtype=float)


def _ridge_fit(x: np.ndarray, y: np.ndarray, alpha: float) -> tuple[np.ndarray, float]:
    if x.shape[1] == 0:
        return np.zeros(0), float(y.mean())
    centered = y - y.mean()
    coefficients = np.linalg.solve(x.T @ x + alpha * np.eye(x.shape[1]), x.T @ centered)
    return coefficients, float(y.mean())


def _ridge_predict(x: np.ndarray, model: tuple[np.ndarray, float]) -> np.ndarray:
    coefficients, intercept = model
    return x @ coefficients + intercept


def _logistic_fit(x: np.ndarray, y: np.ndarray, alpha: float, iterations: int = 800) -> tuple[np.ndarray, float] | None:
    if len(np.unique(y)) < 2:
        return None
    coefficients = np.zeros(x.shape[1], dtype=float)
    intercept = 0.0
    denominator = max(1e-6, float(np.mean(np.sum(x * x, axis=1))) * 0.25 + alpha)
    learning_rate = min(1.0, 1.0 / denominator)
    for _ in range(iterations):
        logits = np.clip(x @ coefficients + intercept, -35, 35)
        probabilities = 1 / (1 + np.exp(-logits))
        error = probabilities - y
        gradient = (x.T @ error) / len(y) + alpha * coefficients
        intercept_gradient = float(error.mean())
        coefficients -= learning_rate * gradient
        intercept -= learning_rate * intercept_gradient
    return coefficients, intercept


def _logistic_predict(x: np.ndarray, model: tuple[np.ndarray, float]) -> np.ndarray:
    logits = np.clip(x @ model[0] + model[1], -35, 35)
    return 1 / (1 + np.exp(-logits))


def _regression_metrics(actual: list[float], predicted: list[float], zero: list[float], historical_mean: list[float]) -> dict:
    y, pred = np.asarray(actual), np.asarray(predicted)
    mae = float(np.mean(np.abs(y - pred)))
    rmse = float(np.sqrt(np.mean((y - pred) ** 2)))
    zero_mae = float(np.mean(np.abs(y - np.asarray(zero))))
    mean_mae = float(np.mean(np.abs(y - np.asarray(historical_mean))))
    directions = (y > 0) == (pred > 0)
    labels = y > 0
    positives, negatives = int(labels.sum()), int((~labels).sum())
    recalls = []
    if positives:
        recalls.append(float(((pred > 0) & labels).sum() / positives))
    if negatives:
        recalls.append(float(((pred <= 0) & ~labels).sum() / negatives))
    return {
        "mae": mae, "rmse": rmse,
        "mae_improvement_vs_zero": 1 - mae / zero_mae if zero_mae else None,
        "mae_improvement_vs_training_mean": 1 - mae / mean_mae if mean_mae else None,
        "directional_accuracy": float(directions.mean()) if len(y) else None,
        "balanced_accuracy": float(np.mean(recalls)) if recalls else None,
    }


def _classification_metrics(actual: list[int], probabilities: list[float]) -> dict:
    y = np.asarray(actual, dtype=int)
    probabilities_array = np.asarray(probabilities, dtype=float)
    decisions = probabilities_array >= 0.5
    positive, negative = y == 1, y == 0
    recalls = []
    if positive.any():
        recalls.append(float((decisions[positive]).mean()))
    if negative.any():
        recalls.append(float((~decisions[negative]).mean()))
    return {
        "directional_accuracy": float((decisions == y).mean()),
        "balanced_accuracy": float(np.mean(recalls)) if recalls else None,
        "brier_score": float(np.mean((probabilities_array - y) ** 2)),
    }


def _moving_block_mae_reduction(
    prediction_groups: list[list[dict]], model_name: str, baseline_name: str,
    *, block_length: int, repetitions: int = 500, seed: int = 42,
) -> dict:
    """Paired circular moving-block bootstrap of MAE reduction, preserving fold/ticker groups."""
    import random

    groups = [sorted(group, key=lambda row: row["forecast_anchor_date"]) for group in prediction_groups if group]
    count = sum(len(group) for group in groups)
    if count < max(30, block_length * 3) or repetitions < 100:
        return {"status": "insufficient_sample_for_block_interval", "sample_count": count}
    baseline_abs, model_abs = [], []
    for group in groups:
        baseline_abs.extend(abs(row["actual"] - row[baseline_name]) for row in group)
        model_abs.extend(abs(row["actual"] - row[model_name]) for row in group)
    estimate = float(np.mean(baseline_abs) - np.mean(model_abs))
    rng = random.Random(seed)
    replicates = []
    for _ in range(repetitions):
        baseline_sample, model_sample = [], []
        for group in groups:
            selected = []
            while len(selected) < len(group):
                start = rng.randrange(len(group))
                take = min(block_length, len(group) - len(selected))
                selected.extend(group[(start + offset) % len(group)] for offset in range(take))
            baseline_sample.extend(abs(row["actual"] - row[baseline_name]) for row in selected)
            model_sample.extend(abs(row["actual"] - row[model_name]) for row in selected)
        replicates.append(float(np.mean(baseline_sample) - np.mean(model_sample)))
    low, high = np.percentile(np.asarray(replicates), [2.5, 97.5]).tolist()
    return {
        "metric": f"paired_mae_reduction_{baseline_name}_minus_{model_name}",
        "estimate": estimate, "interval_95_percentile": [float(low), float(high)],
        "sample_count": count, "block_length_trading_sessions": block_length,
        "repetitions": repetitions, "seed": seed,
        "method": "Paired circular moving-block bootstrap within ticker/fold groups; not a significance test.",
    }


def aggregate_price_experiments(experiments: list[dict], *, bootstrap_repetitions: int = 500, seed: int = 42) -> dict:
    """Pool out-of-sample rows from per-stock runs using identical dates per baseline/model."""
    if not experiments:
        return {"status": "no_experiments", "per_stock": []}
    horizon = experiments[0]["horizon_trading_sessions"]
    target_name = experiments[0]["target_name"]
    tagged = []
    per_stock = []
    for experiment in experiments:
        predictions = [{**row, "ticker": experiment["ticker"]} for row in experiment.get("out_of_sample_predictions", [])]
        tagged.extend(predictions)
        per_stock.append({
            "ticker": experiment["ticker"], "oos_observation_count": len(predictions),
            "evaluation_periods": experiment.get("evaluation_period"),
            "metrics": experiment.get("overall_out_of_sample_metrics", {}),
            "metrics_by_market_regime": experiment.get("metrics_by_market_regime", {}),
            "folds": experiment.get("folds", []),
        })
    if not tagged:
        return {"status": "no_out_of_sample_predictions", "per_stock": per_stock}
    def regression(rows: list[dict], model: str) -> dict:
        return _regression_metrics(
            [row["actual"] for row in rows], [row[model] for row in rows],
            [row["zero_return"] for row in rows], [row["historical_mean"] for row in rows],
        )
    overall = {model: regression(tagged, model) for model in ("zero_return", "historical_mean", "ridge_regression")}
    classified = [row for row in tagged if row.get("direction_probability") is not None and row["actual"] != 0]
    if classified:
        overall["logistic_direction"] = _classification_metrics(
            [1 if row["actual"] > 0 else 0 for row in classified],
            [row["direction_probability"] for row in classified],
        )
        overall["logistic_direction"]["sample_count"] = len(classified)
    by_regime = {}
    for regime in sorted({row.get("market_regime", "unavailable") for row in tagged}):
        group = [row for row in tagged if row.get("market_regime", "unavailable") == regime]
        by_regime[regime] = {
            "sample_count": len(group),
            "metrics": {model: regression(group, model) for model in ("zero_return", "historical_mean", "ridge_regression")},
        }
        classified = [row for row in group if row.get("direction_probability") is not None and row["actual"] != 0]
        if classified:
            by_regime[regime]["logistic_direction"] = _classification_metrics(
                [1 if row["actual"] > 0 else 0 for row in classified],
                [row["direction_probability"] for row in classified],
            )
            by_regime[regime]["logistic_direction"]["sample_count"] = len(classified)
    grouped = {}
    for row in tagged:
        grouped.setdefault((row["ticker"], row["fold"]), []).append(row)
    groups = list(grouped.values())
    intervals = {
        "ridge_vs_zero": _moving_block_mae_reduction(groups, "ridge_regression", "zero_return", block_length=horizon, repetitions=bootstrap_repetitions, seed=seed),
        "ridge_vs_historical_mean": _moving_block_mae_reduction(groups, "ridge_regression", "historical_mean", block_length=horizon, repetitions=bootstrap_repetitions, seed=seed + 1),
    }
    valid_dates = sorted({row["forecast_anchor_date"] for row in tagged})
    return {
        "status": "evaluated",
        "horizon_trading_sessions": horizon, "target_name": target_name,
        "oos_observation_count": len(tagged), "unique_evaluation_dates": len(valid_dates),
        "evaluation_period": [valid_dates[0], valid_dates[-1]],
        "baseline_comparison_uses_identical_oos_observations": True,
        "aggregate_metrics": overall, "metrics_by_market_regime": by_regime,
        "paired_mae_uncertainty_intervals": intervals,
        "per_stock": per_stock,
        "limitations": ["Overlapping outcome windows remain dependent; intervals use within-ticker/fold moving blocks.", "Bootstrap intervals summarize these observations and are not significance tests or evidence of profitability."],
    }


def _score_regression(rows: list[dict], indices: list[int], horizon: int, target_name: str, pred: np.ndarray, zero: np.ndarray, historical: np.ndarray) -> dict:
    actual = _targets_for(rows, indices, horizon, target_name).tolist()
    return _regression_metrics(actual, pred.tolist(), zero.tolist(), historical.tolist())


def run_walk_forward_experiment(
    dataset: dict,
    *, horizon: int,
    target_name: str = "stock_return",
    code_version: str | None = None,
    ridge_alphas: tuple[float, ...] = (0.1, 1.0, 10.0),
    logistic_alphas: tuple[float, ...] = (0.01, 0.1, 1.0),
    initial_train_fraction: float = 0.60,
    block_fraction: float = 0.10,
) -> dict:
    """Return fold metrics and only out-of-sample test predictions."""
    rows = dataset["rows"]
    continuous_target = target_name in {"stock_return", "excess_return"}
    if not continuous_target:
        raise ValueError("target_name must be stock_return or excess_return")
    splits = purged_walk_forward_splits(rows, horizon, target_name,
                                        initial_train_fraction=initial_train_fraction,
                                        block_fraction=block_fraction)
    folds, all_predictions = [], []
    for fold_number, split in enumerate(splits, start=1):
        train_indices, validation_indices, test_indices = split["train"], split["validation"], split["test"]
        train_rows = [rows[i] for i in train_indices]
        validation_rows = [rows[i] for i in validation_indices]
        test_rows = [rows[i] for i in test_indices]
        train_y = _targets_for(rows, train_indices, horizon, target_name)
        validation_y = _targets_for(rows, validation_indices, horizon, target_name)
        preprocessor = TrainOnlyPreprocessor().fit(train_rows)
        x_train = preprocessor.transform(train_rows)
        x_validation = preprocessor.transform(validation_rows)
        selected_alpha = min(ridge_alphas, key=lambda alpha: float(np.mean(np.abs(validation_y - _ridge_predict(x_validation, _ridge_fit(x_train, train_y, alpha))))))

        # Refit using all mature labels before the test boundary. Preprocessing
        # is re-fitted only on this final training set, never on test rows.
        final_indices = train_indices + validation_indices
        final_rows = [rows[i] for i in final_indices]
        final_y = _targets_for(rows, final_indices, horizon, target_name)
        final_preprocessor = TrainOnlyPreprocessor().fit(final_rows)
        x_final = final_preprocessor.transform(final_rows)
        x_test = final_preprocessor.transform(test_rows)
        ridge = _ridge_fit(x_final, final_y, selected_alpha)
        ridge_predictions = _ridge_predict(x_test, ridge)
        zero_predictions = np.zeros(len(test_indices))
        history_mean = np.full(len(test_indices), float(final_y.mean()))
        regression = {
            "zero_return": _score_regression(rows, test_indices, horizon, target_name, zero_predictions, zero_predictions, history_mean),
            "historical_mean": _score_regression(rows, test_indices, horizon, target_name, history_mean, zero_predictions, history_mean),
            "ridge_regression": _score_regression(rows, test_indices, horizon, target_name, ridge_predictions, zero_predictions, history_mean),
        }
        # Direction labels are based on the same stock/excess return target.
        direction_name = "stock_direction" if target_name == "stock_return" else "excess_direction"
        direction_train = [rows[i]["targets"][str(horizon)].get(direction_name) for i in train_indices]
        direction_test = [rows[i]["targets"][str(horizon)].get(direction_name) for i in test_indices]
        valid_train = [i for i, value in enumerate(direction_train) if value is not None]
        valid_test = [i for i, value in enumerate(direction_test) if value is not None]
        classification = None
        chosen_logistic_alpha = None
        if valid_train and valid_test:
            train_x = x_train[valid_train]
            train_labels = np.asarray([direction_train[i] for i in valid_train], dtype=int)
            val_direction = [rows[i]["targets"][str(horizon)].get(direction_name) for i in validation_indices]
            val_valid = [i for i, value in enumerate(val_direction) if value is not None]
            if val_valid and len(np.unique(train_labels)) == 2:
                val_labels = np.asarray([val_direction[i] for i in val_valid], dtype=int)
                val_x = x_validation[val_valid]
                chosen_logistic_alpha = min(logistic_alphas, key=lambda alpha: float(np.mean((_logistic_predict(val_x, _logistic_fit(train_x, train_labels, alpha)) - val_labels) ** 2)))
                final_labels = [rows[i]["targets"][str(horizon)].get(direction_name) for i in final_indices]
                final_valid = [i for i, value in enumerate(final_labels) if value is not None]
                final_logistic = _logistic_fit(x_final[final_valid], np.asarray([final_labels[i] for i in final_valid], dtype=int), chosen_logistic_alpha)
                probabilities = _logistic_predict(x_test[valid_test], final_logistic)
                actual_direction = [int(direction_test[i]) for i in valid_test]
                classification = _classification_metrics(actual_direction, probabilities.tolist())
            else:
                classification = {"status": "unavailable: both classes are required in the training and validation windows"}
        predictions = []
        for local_index, row_index in enumerate(test_indices):
            item = {
                "forecast_anchor_date": rows[row_index]["forecast_anchor_date"],
                "target_end_date": rows[row_index]["targets"][str(horizon)]["target_end_date"],
                "market_regime": rows[row_index].get("market_regime", "unavailable"),
                "actual": float(rows[row_index]["targets"][str(horizon)][target_name]),
                "zero_return": float(zero_predictions[local_index]),
                "historical_mean": float(history_mean[local_index]),
                "ridge_regression": float(ridge_predictions[local_index]),
                "direction_probability": None,
            }
            if classification and "status" not in classification and local_index in valid_test:
                position = valid_test.index(local_index)
                item["direction_probability"] = float(probabilities[position])
            predictions.append(item)
            all_predictions.append({"fold": fold_number, **item})
        folds.append({
            "fold": fold_number,
            "train_period": [rows[train_indices[0]]["forecast_anchor_date"], rows[train_indices[-1]]["forecast_anchor_date"]],
            "validation_period": [rows[validation_indices[0]]["forecast_anchor_date"], rows[validation_indices[-1]]["forecast_anchor_date"]],
            "test_period": [rows[test_indices[0]]["forecast_anchor_date"], rows[test_indices[-1]]["forecast_anchor_date"]],
            "sample_counts": {"train": len(train_indices), "validation": len(validation_indices), "test": len(test_indices)},
            "purged_sample_count": (validation_indices[0] - len(train_indices)) + ((test_indices[0] - validation_indices[0]) - len(validation_indices)),
            "selected_ridge_alpha": float(selected_alpha),
            "selected_logistic_alpha": float(chosen_logistic_alpha) if chosen_logistic_alpha is not None else None,
            "regression_metrics": regression,
            "direction_logistic_metrics": classification,
            "out_of_sample_predictions": predictions,
        })
    overall = {}
    metrics_by_regime = {}
    if all_predictions:
        actual = [item["actual"] for item in all_predictions]
        zero = [item["zero_return"] for item in all_predictions]
        historical = [item["historical_mean"] for item in all_predictions]
        ridge = [item["ridge_regression"] for item in all_predictions]
        overall = {
            "zero_return": _regression_metrics(actual, zero, zero, historical),
            "historical_mean": _regression_metrics(actual, historical, zero, historical),
            "ridge_regression": _regression_metrics(actual, ridge, zero, historical),
        }
        classified = [item for item in all_predictions if item["direction_probability"] is not None and item["actual"] != 0]
        if classified:
            overall["logistic_direction"] = _classification_metrics(
                [1 if item["actual"] > 0 else 0 for item in classified],
                [item["direction_probability"] for item in classified],
            )
        for regime in sorted({item.get("market_regime", "unavailable") for item in all_predictions}):
            regime_rows = [item for item in all_predictions if item.get("market_regime", "unavailable") == regime]
            metrics_by_regime[regime] = {
                "sample_count": len(regime_rows),
                "metrics": {
                    model: _regression_metrics(
                        [item["actual"] for item in regime_rows],
                        [item[model] for item in regime_rows],
                        [item["zero_return"] for item in regime_rows],
                        [item["historical_mean"] for item in regime_rows],
                    )
                    for model in ("zero_return", "historical_mean", "ridge_regression")
                },
            }
            regime_classified = [item for item in regime_rows if item["direction_probability"] is not None and item["actual"] != 0]
            if regime_classified:
                metrics_by_regime[regime]["logistic_direction"] = _classification_metrics(
                    [1 if item["actual"] > 0 else 0 for item in regime_classified],
                    [item["direction_probability"] for item in regime_classified],
                )
                metrics_by_regime[regime]["logistic_direction"]["sample_count"] = len(regime_classified)
    return {
        "schema_version": EXPERIMENT_SCHEMA_VERSION,
        "experiment_id": f"{dataset['ticker']}-{target_name}-{horizon}session-price-only-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ticker": dataset["ticker"], "horizon_trading_sessions": horizon,
        "benchmark": dataset.get("benchmark", {"ticker": "^GSPC", "source": "Yahoo Finance via yfinance (^GSPC S&P 500 index proxy)"}),
        "target_name": target_name,
        "forecast_anchor_definition": "After the anchor session closes and its completed adjusted daily OHLCV bar is available.",
        "information_cutoff": "No feature uses a bar dated after forecast_anchor_date.",
        "target_definition": "Entry at next trading session adjusted open; exit at the adjusted close of the Hth future trading session. Excess return subtracts S&P 500 proxy return on the same entry/exit dates.",
        "direction_definition": "positive=return > 0; negative=return < 0; exact zero has no directional label.",
        "model_identifiers": ["zero_return_v1", "historical_mean_v1", "ridge_regression_v1", "logistic_regression_v1"],
        "training_period": [fold["train_period"] for fold in folds],
        "evaluation_period": [fold["test_period"] for fold in folds],
        "feature_definitions": dataset["feature_definitions"],
        "data_source": dataset["data_source"],
        "data_vintage_limitations": dataset["limitations"],
        "configuration": {
            "initial_train_fraction": initial_train_fraction, "validation_and_test_block_fraction": block_fraction,
            "ridge_alpha_candidates": list(ridge_alphas), "logistic_l2_alpha_candidates": list(logistic_alphas),
            "preprocessing": "Median imputation and population-standard-deviation scaling fit within each training fold; all-missing training features are dropped.",
            "split_rule": "Expanding chronological windows; training labels ending on/after validation start and validation labels ending on/after test start are purged.",
            "random_split": False,
        },
        "code_version": code_version,
        "folds": folds, "overall_out_of_sample_metrics": overall,
        "metrics_by_market_regime": metrics_by_regime,
        "out_of_sample_predictions": all_predictions,
        "claims": "Predictive metrics only; no trading profitability or causal claim is made.",
    }


def save_experiment(experiment: dict, path: str | Path) -> Path:
    """Persist a self-describing research result as JSON; does not touch app DB."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(experiment, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    return destination


def save_dataset(dataset: dict, path: str | Path) -> Path:
    """Persist row-level point-in-time features and labels without dropping nulls."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(dataset, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    return destination
