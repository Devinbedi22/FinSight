"""Phase 5C pooled model selection and one-shot chronological holdout evaluation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
import math
import random
from typing import Callable

import numpy as np

from app.research.forecasting import FEATURE_NAMES, TrainOnlyPreprocessor

HOLDOUT_START = date(2024, 10, 24)
VALIDATION_WINDOWS = (
    ("validation_2020", date(2020, 1, 2), date(2020, 12, 31)),
    ("validation_2021", date(2021, 1, 1), date(2021, 12, 31)),
    ("validation_2022", date(2022, 1, 1), date(2022, 12, 31)),
    ("validation_2023", date(2023, 1, 1), date(2023, 12, 31)),
    ("validation_2024_pre_holdout", date(2024, 1, 2), date(2024, 9, 25)),
)

MOMENTUM_FEATURE = {
    "stock_return": "momentum_20d",
    "excess_return": "relative_return_20d_vs_sp500",
}
FEATURE_GROUPS = {
    "momentum": ("momentum_20d", "momentum_252d", "relative_return_20d_vs_sp500"),
    "volatility": ("historical_volatility_20d", "atr_close_ratio", "relative_volatility_20d_vs_sp500", "relative_volatility_20d_vs_sector"),
    "trend": (
        "close_sma20_gap", "close_sma50_gap", "close_sma200_gap", "sma20_sma50_gap", "sma50_sma200_gap",
        "close_ema12_gap", "close_ema26_gap", "close_ema50_gap", "ema12_ema26_gap", "rsi_14",
        "macd_close_ratio", "macd_signal_close_ratio", "macd_histogram_close_ratio", "bollinger_position",
    ),
    "sector_relative": ("relative_return_20d_vs_sector", "relative_volatility_20d_vs_sector"),
}

REGRESSION_CANDIDATES = {
    "ridge_regression": ({"alpha": 0.1}, {"alpha": 1.0}, {"alpha": 10.0}),
    "random_forest": (
        {"n_estimators": 60, "max_depth": 5, "min_samples_leaf": 25, "max_features": 0.8},
        {"n_estimators": 80, "max_depth": 8, "min_samples_leaf": 35, "max_features": 0.8},
    ),
    "hist_gradient_boosting": (
        {"learning_rate": 0.05, "max_iter": 60, "max_leaf_nodes": 15, "l2_regularization": 1.0},
        {"learning_rate": 0.03, "max_iter": 100, "max_leaf_nodes": 15, "l2_regularization": 5.0},
    ),
}
CLASSIFICATION_CANDIDATES = {
    "logistic_regression": ({"C": 0.1}, {"C": 1.0}),
    "random_forest": (
        {"n_estimators": 60, "max_depth": 5, "min_samples_leaf": 25, "max_features": 0.8},
        {"n_estimators": 80, "max_depth": 8, "min_samples_leaf": 35, "max_features": 0.8},
    ),
    "hist_gradient_boosting": (
        {"learning_rate": 0.05, "max_iter": 60, "max_leaf_nodes": 15, "l2_regularization": 1.0},
        {"learning_rate": 0.03, "max_iter": 100, "max_leaf_nodes": 15, "l2_regularization": 5.0},
    ),
}


def _day(row: dict) -> date:
    return date.fromisoformat(row["forecast_anchor_date"])


def _target(row: dict, horizon: int, target_name: str) -> float | None:
    value = row["targets"][str(horizon)].get(target_name)
    return float(value) if value is not None and math.isfinite(float(value)) else None


def _direction(row: dict, horizon: int, target_name: str) -> int | None:
    key = "stock_direction" if target_name == "stock_return" else "excess_direction"
    value = row["targets"][str(horizon)].get(key)
    return int(value) if value is not None else None


def select_rows(
    datasets: dict[str, dict], *, horizon: int, target_name: str,
    start: date | None = None, end: date | None = None,
    training_before: date | None = None,
) -> list[dict]:
    """Select labelled rows and retain ticker, enforcing date and outcome cutoffs."""
    result = []
    for ticker in sorted(datasets):
        for row in datasets[ticker]["rows"]:
            anchor = _day(row)
            target = row["targets"][str(horizon)]
            value = _target(row, horizon, target_name)
            if value is None:
                continue
            target_end = date.fromisoformat(target["target_end_date"])
            if start is not None and anchor < start:
                continue
            if end is not None and anchor > end:
                continue
            if training_before is not None and (anchor >= training_before or target_end >= training_before):
                continue
            result.append({"ticker": ticker, **row})
    return sorted(result, key=lambda row: (row["forecast_anchor_date"], row["ticker"]))


def validation_training_rows(datasets: dict[str, dict], horizon: int, target_name: str, validation_start: date) -> list[dict]:
    return select_rows(datasets, horizon=horizon, target_name=target_name, training_before=validation_start)


def validation_rows(datasets: dict[str, dict], horizon: int, target_name: str, start: date, end: date) -> list[dict]:
    rows = select_rows(datasets, horizon=horizon, target_name=target_name, start=start, end=end)
    # Validation labels must be fully realized before the final holdout begins.
    return [row for row in rows if date.fromisoformat(row["targets"][str(horizon)]["target_end_date"]) < HOLDOUT_START]


def final_holdout_rows(datasets: dict[str, dict], horizon: int, target_name: str) -> tuple[list[dict], list[dict]]:
    train = validation_training_rows(datasets, horizon, target_name, HOLDOUT_START)
    holdout = select_rows(datasets, horizon=horizon, target_name=target_name, start=HOLDOUT_START)
    return train, holdout


def _require_sklearn():
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
        from sklearn.linear_model import LogisticRegression
    except ImportError as exc:
        raise RuntimeError("Install the optional research dependencies with `pip install -e '.[research]'`.") from exc
    return {
        "HistGradientBoostingClassifier": HistGradientBoostingClassifier,
        "HistGradientBoostingRegressor": HistGradientBoostingRegressor,
        "RandomForestClassifier": RandomForestClassifier,
        "RandomForestRegressor": RandomForestRegressor,
        "LogisticRegression": LogisticRegression,
    }


def _new_estimator(task: str, model: str, parameters: dict, seed: int = 31415):
    classes = _require_sklearn()
    if model == "ridge_regression":
        return None
    if model == "logistic_regression":
        return classes["LogisticRegression"](C=parameters["C"], max_iter=1000, solver="lbfgs", random_state=seed)
    if model == "random_forest":
        estimator = classes["RandomForestRegressor" if task == "regression" else "RandomForestClassifier"]
        options = {**parameters, "n_jobs": 1, "random_state": seed}
        if task == "regression":
            options["criterion"] = "squared_error"
        else:
            options["class_weight"] = "balanced_subsample"
        return estimator(**options)
    if model == "hist_gradient_boosting":
        estimator = classes["HistGradientBoostingRegressor" if task == "regression" else "HistGradientBoostingClassifier"]
        return estimator(**parameters, random_state=seed, early_stopping=False)
    raise ValueError(f"Unknown Phase 5C model: {model}")


def _fit_predict(model: str, parameters: dict, train: list[dict], predict: list[dict], y: np.ndarray, *, task: str, feature_names=FEATURE_NAMES):
    processor = TrainOnlyPreprocessor(tuple(feature_names)).fit(train)
    x_train, x_predict = processor.transform(train), processor.transform(predict)
    if model == "ridge_regression":
        if not x_train.shape[1]:
            return np.full(len(predict), float(y.mean())), processor
        centered = y - y.mean()
        weights = np.linalg.solve(x_train.T @ x_train + parameters["alpha"] * np.eye(x_train.shape[1]), x_train.T @ centered)
        output = x_predict @ weights + float(y.mean())
    else:
        estimator = _new_estimator(task, model, parameters)
        labels = np.asarray(y, dtype=int) if task == "classification" else y
        estimator.fit(x_train, labels)
        if task == "classification":
            pos = list(estimator.classes_).index(1)
            output = estimator.predict_proba(x_predict)[:, pos]
        else:
            output = estimator.predict(x_predict)
    return np.asarray(output, dtype=float), processor


def _regression_metrics(rows: list[dict], predictions: np.ndarray, target_name: str, horizon: int) -> dict:
    actual = np.asarray([_target(row, horizon, target_name) for row in rows], dtype=float)
    pred = np.asarray(predictions, dtype=float)
    zero = np.zeros(len(rows))
    historical = np.asarray([row.get("historical_mean_baseline", 0.0) for row in rows], dtype=float)
    result = {"sample_count": len(rows)}
    for name, values in (("zero_return", zero), ("historical_mean", historical), ("model", pred)):
        error = actual - values
        result[name] = {
            "mae": float(np.mean(np.abs(error))), "rmse": float(np.sqrt(np.mean(error ** 2))),
            "directional_accuracy": float(np.mean((actual > 0) == (values > 0))),
        }
        positive, negative = actual > 0, actual <= 0
        recalls = []
        if positive.any(): recalls.append(float(np.mean(values[positive] > 0)))
        if negative.any(): recalls.append(float(np.mean(values[negative] <= 0)))
        result[name]["balanced_accuracy"] = float(np.mean(recalls)) if recalls else None
    result["model"]["mae_improvement_vs_zero"] = result["zero_return"]["mae"] - result["model"]["mae"]
    result["model"]["mae_improvement_vs_historical_mean"] = result["historical_mean"]["mae"] - result["model"]["mae"]
    return result


def _classification_metrics(labels: np.ndarray, probabilities: np.ndarray) -> dict:
    valid = labels >= 0
    y = np.asarray(labels[valid], dtype=int)
    p = np.clip(np.asarray(probabilities[valid], dtype=float), 1e-12, 1 - 1e-12)
    decision = p >= 0.5
    positive, negative = y == 1, y == 0
    recalls = []
    if positive.any(): recalls.append(float(decision[positive].mean()))
    if negative.any(): recalls.append(float((~decision[negative]).mean()))
    return {
        "sample_count": len(y),
        "directional_accuracy": float(np.mean(decision == y)) if len(y) else None,
        "balanced_accuracy": float(np.mean(recalls)) if recalls else None,
        "brier_score": float(np.mean((p - y) ** 2)) if len(y) else None,
        "log_loss": float(np.mean(-(y * np.log(p) + (1 - y) * np.log(1 - p)))) if len(y) else None,
    }


def _base_predictions(rows: list[dict], train_rows: list[dict], horizon: int, target_name: str) -> dict:
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for row in train_rows:
        by_ticker[row["ticker"]].append(row)
    means, prevalences = {}, {}
    for ticker, ticker_rows in by_ticker.items():
        means[ticker] = float(np.mean([_target(row, horizon, target_name) for row in ticker_rows]))
        labels = [_direction(row, horizon, target_name) for row in ticker_rows]
        labels = [label for label in labels if label is not None]
        prevalences[ticker] = float(np.mean(labels)) if labels else 0.5
    historical = np.asarray([means.get(row["ticker"], 0.0) for row in rows])
    prevalence = np.asarray([prevalences.get(row["ticker"], 0.5) for row in rows])
    majority = (prevalence >= 0.5).astype(float)
    momentum_name = MOMENTUM_FEATURE[target_name]
    momentum = np.asarray([
        1.0 if row["features"].get(momentum_name) is not None and row["features"][momentum_name] > 0
        else 0.0 if row["features"].get(momentum_name) is not None
        else 0.5
        for row in rows
    ])
    return {"historical_mean": historical, "prevalence_probability": prevalence, "majority_direction": majority, "momentum_direction": momentum}


def _decorate_rows(rows: list[dict], train_rows: list[dict], horizon: int, target_name: str) -> tuple[list[dict], dict]:
    base = _base_predictions(rows, train_rows, horizon, target_name)
    enriched = []
    for i, row in enumerate(rows):
        enriched.append({**row, "historical_mean_baseline": float(base["historical_mean"][i])})
    return enriched, base


def _metrics_by_ticker(rows: list[dict], predictions: np.ndarray, horizon: int, target_name: str) -> dict:
    result = {}
    for ticker in sorted({row["ticker"] for row in rows}):
        indices = [index for index, row in enumerate(rows) if row["ticker"] == ticker]
        group = [rows[index] for index in indices]
        result[ticker] = _regression_metrics(group, predictions[indices], target_name, horizon)
    return result


def _block_interval(rows: list[dict], predictions: np.ndarray, baseline: np.ndarray, horizon: int, target_name: str, *, seed: int, repetitions: int = 500) -> dict:
    groups: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(rows): groups[row["ticker"]].append(i)
    actual = np.asarray([_target(row, horizon, target_name) for row in rows], dtype=float)
    per_ticker = [indices for indices in groups.values()]
    estimate = float(np.mean(np.abs(actual - baseline)) - np.mean(np.abs(actual - predictions)))
    rng = random.Random(seed)
    samples = []
    for _ in range(repetitions):
        y_sample, p_sample, b_sample = [], [], []
        for indices in per_ticker:
            ordered = sorted(indices, key=lambda i: rows[i]["forecast_anchor_date"])
            selected = []
            while len(selected) < len(ordered):
                start = rng.randrange(len(ordered))
                take = min(horizon, len(ordered) - len(selected))
                selected.extend(ordered[(start + offset) % len(ordered)] for offset in range(take))
            y_sample.extend(actual[i] for i in selected)
            p_sample.extend(predictions[i] for i in selected)
            b_sample.extend(baseline[i] for i in selected)
        samples.append(float(np.mean(np.abs(np.asarray(y_sample) - b_sample)) - np.mean(np.abs(np.asarray(y_sample) - p_sample))))
    return {
        "baseline_minus_model_mae": estimate,
        "block_bootstrap_95_percentile": [float(x) for x in np.percentile(samples, [2.5, 97.5])],
        "block_length_sessions": horizon, "repetitions": len(samples), "seed": seed,
        "method": "Paired circular moving-block bootstrap within ticker over holdout forecasts; descriptive, not a significance test.",
    }


def _evaluate_regression(rows: list[dict], prediction_map: dict[str, np.ndarray], horizon: int, target_name: str) -> dict:
    output = {}
    baseline = np.zeros(len(rows))
    historical = np.asarray([row["historical_mean_baseline"] for row in rows])
    baseline_map = {"zero_return": baseline, "historical_mean": historical, **prediction_map}
    for name, prediction in baseline_map.items():
        metrics = _regression_metrics(rows, prediction, target_name, horizon)
        by_ticker = _metrics_by_ticker(rows, prediction, horizon, target_name)
        for ticker, ticker_metrics in by_ticker.items():
            ticker_target = np.asarray([_target(row, horizon, target_name) for row in rows if row["ticker"] == ticker])
            ticker_prediction = prediction[[i for i, row in enumerate(rows) if row["ticker"] == ticker]]
            ticker_zero = np.zeros(len(ticker_target))
            ticker_mean = np.asarray([row["historical_mean_baseline"] for row in rows if row["ticker"] == ticker])
            ticker_metrics["mae_improvement_vs_zero"] = float(np.mean(np.abs(ticker_target)) - ticker_metrics["model"]["mae"])
            ticker_metrics["mae_improvement_vs_historical_mean"] = float(np.mean(np.abs(ticker_target - ticker_mean)) - ticker_metrics["model"]["mae"])
        output[name] = {"pooled": metrics, "per_ticker": by_ticker}
    output["uncertainty_intervals"] = {
        f"{model}_vs_{baseline_name}": _block_interval(
            rows, prediction, baseline_values, horizon, target_name,
            seed=9000 + horizon + model_index * 10 + baseline_index,
        )
        for model_index, (model, prediction) in enumerate(prediction_map.items())
        for baseline_index, (baseline_name, baseline_values) in enumerate(
            (("zero_return", baseline), ("historical_mean", historical))
        ) if model not in {"historical_mean", "zero_return"}
    }
    return output


def _evaluate_classification(rows: list[dict], probability_map: dict[str, np.ndarray], horizon: int, target_name: str, *, include_uncertainty: bool = True) -> dict:
    labels = np.asarray([_direction(row, horizon, target_name) if _direction(row, horizon, target_name) is not None else -1 for row in rows], dtype=int)
    result = {}
    for name, probabilities in probability_map.items():
        result[name] = _classification_metrics(labels, probabilities)
        by_ticker = {}
        for ticker in sorted({row["ticker"] for row in rows}):
            indices = [i for i, row in enumerate(rows) if row["ticker"] == ticker]
            by_ticker[ticker] = _classification_metrics(labels[indices], probabilities[indices])
        result[name]["per_ticker"] = by_ticker
    if include_uncertainty:
        result["brier_block_bootstrap_vs_training_prevalence"] = _classification_block_intervals(rows, probability_map, horizon, target_name)
    return result


def _classification_block_intervals(rows: list[dict], probability_map: dict[str, np.ndarray], horizon: int, target_name: str, repetitions: int = 500) -> dict:
    groups: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        if _direction(row, horizon, target_name) is not None:
            groups[row["ticker"]].append(i)
    rng = random.Random(5100 + horizon)
    model_names = [name for name in probability_map if name != "training_prevalence_probability"]
    deltas = {name: [] for name in model_names}
    actual = {i: _direction(rows[i], horizon, target_name) for indices in groups.values() for i in indices}
    ordered_groups = [sorted(indices, key=lambda i: rows[i]["forecast_anchor_date"]) for indices in groups.values()]
    all_indices = [i for indices in ordered_groups for i in indices]
    if len(all_indices) < max(30, horizon * 3):
        return {name: {"status": "insufficient_sample_for_block_interval", "sample_count": len(all_indices)} for name in model_names}
    all_labels = np.asarray([actual[i] for i in all_indices], dtype=float)
    all_base = np.asarray([probability_map["training_prevalence_probability"][i] for i in all_indices], dtype=float)
    for _ in range(repetitions):
        selected = []
        for indices in ordered_groups:
            sample = []
            while len(sample) < len(indices):
                start = rng.randrange(len(indices))
                take = min(horizon, len(indices) - len(sample))
                sample.extend(indices[(start + offset) % len(indices)] for offset in range(take))
            selected.extend(sample)
        labels = np.asarray([actual[i] for i in selected], dtype=float)
        base = np.asarray([probability_map["training_prevalence_probability"][i] for i in selected], dtype=float)
        base_brier = float(np.mean((labels - base) ** 2))
        for name in model_names:
            probabilities = np.asarray([probability_map[name][i] for i in selected], dtype=float)
            deltas[name].append(base_brier - float(np.mean((labels - probabilities) ** 2)))
    return {
        name: {
            "baseline_minus_model_brier": float(
                np.mean((all_labels - all_base) ** 2)
                - np.mean((all_labels - np.asarray([probability_map[name][i] for i in all_indices], dtype=float)) ** 2)
            ),
            "block_bootstrap_95_percentile": [float(x) for x in np.percentile(deltas[name], [2.5, 97.5])],
            "block_length_sessions": horizon, "repetitions": repetitions,
            "method": "Paired circular moving-block bootstrap within ticker on holdout labels; descriptive, not a significance test.",
        }
        for name in model_names
    }


def _validation_fold_data(datasets: dict[str, dict], horizon: int, target_name: str) -> list[dict]:
    folds = []
    for name, start, end in VALIDATION_WINDOWS:
        train = validation_training_rows(datasets, horizon, target_name, start)
        validation = validation_rows(datasets, horizon, target_name, start, end)
        if len(train) < 1000 or len(validation) < 250:
            raise ValueError(f"Insufficient rows in {name}: train={len(train)} validation={len(validation)}")
        folds.append({"name": name, "start": start, "end": end, "train": train, "validation": validation})
    return folds


def _candidate_validation(datasets: dict[str, dict], horizon: int, target_name: str, model: str, parameters: dict, task: str) -> dict:
    predictions, labels, fold_results = [], [], []
    ticker_results: dict[str, dict[str, list]] = defaultdict(lambda: {"predictions": [], "labels": []})
    for fold in _validation_fold_data(datasets, horizon, target_name):
        train, validation = fold["train"], fold["validation"]
        targets = np.asarray([_target(row, horizon, target_name) for row in train], dtype=float)
        if task == "classification":
            valid = np.asarray([_direction(row, horizon, target_name) is not None for row in train])
            targets = np.asarray([_direction(row, horizon, target_name) for row in train if _direction(row, horizon, target_name) is not None], dtype=int)
            train_for_model = [row for row, use in zip(train, valid) if use]
        else:
            train_for_model = train
        if len(np.unique(targets)) < 2 and task == "classification":
            raise ValueError(f"Classification training labels have one class in {fold['name']}")
        prediction, _ = _fit_predict(model, parameters, train_for_model, validation, targets, task=task)
        predictions.extend(prediction.tolist())
        for row, predicted in zip(validation, prediction):
            value = _target(row, horizon, target_name) if task == "regression" else _direction(row, horizon, target_name)
            ticker_results[row["ticker"]]["predictions"].append(float(predicted))
            ticker_results[row["ticker"]]["labels"].append(-1 if value is None and task == "classification" else value)
        if task == "regression":
            labels.extend([_target(row, horizon, target_name) for row in validation])
            fold_results.append({"fold": fold["name"], "train_count": len(train), "validation_count": len(validation), "mae": float(np.mean(np.abs(np.asarray([_target(row, horizon, target_name) for row in validation]) - prediction)))})
        else:
            actual = [_direction(row, horizon, target_name) for row in validation]
            labels.extend([-1 if value is None else value for value in actual])
            fold_results.append({"fold": fold["name"], "train_count": len(train), "validation_count": len(validation), **_classification_metrics(np.asarray([-1 if value is None else value for value in actual]), prediction)})
    if task == "regression":
        score = float(np.mean(np.abs(np.asarray(labels) - np.asarray(predictions))))
        metrics = {"mae": score, "rmse": float(np.sqrt(np.mean((np.asarray(labels) - np.asarray(predictions)) ** 2)))}
    else:
        metrics = _classification_metrics(np.asarray(labels, dtype=int), np.asarray(predictions))
        score = float(metrics["brier_score"])
    per_ticker = {}
    for ticker, values in ticker_results.items():
        if task == "regression":
            actual = np.asarray(values["labels"], dtype=float)
            pred = np.asarray(values["predictions"], dtype=float)
            error = actual - pred
            per_ticker[ticker] = {"sample_count": len(actual), "mae": float(np.mean(np.abs(error))), "rmse": float(np.sqrt(np.mean(error ** 2)))}
        else:
            per_ticker[ticker] = _classification_metrics(np.asarray(values["labels"], dtype=int), np.asarray(values["predictions"], dtype=float))
    return {"score": score, "metrics": metrics, "per_ticker": per_ticker, "folds": fold_results, "validation_sample_count": len(labels)}


def _select_models(datasets: dict[str, dict], horizon: int, target_name: str, progress: Callable[[str], None] | None = None) -> tuple[dict, dict]:
    selected, scores = {}, {}
    for model, candidates in REGRESSION_CANDIDATES.items():
        trials = []
        for candidate, parameters in enumerate(candidates, start=1):
            if progress: progress(f"candidate_started horizon={horizon} target={target_name} task=regression model={model} candidate={candidate}/{len(candidates)}")
            trials.append({"parameters": parameters, **_candidate_validation(datasets, horizon, target_name, model, parameters, "regression")})
            if progress: progress(f"candidate_complete horizon={horizon} target={target_name} task=regression model={model} candidate={candidate}/{len(candidates)} score={trials[-1]['score']:.8f}")
        best = min(trials, key=lambda trial: trial["score"])
        selected[model] = best["parameters"]
        scores[model] = {"selected_parameters": best["parameters"], "validation": {key: best[key] for key in ("score", "metrics", "per_ticker", "folds", "validation_sample_count")}, "candidate_scores": [{"parameters": trial["parameters"], "score": trial["score"]} for trial in trials]}
    for model, candidates in CLASSIFICATION_CANDIDATES.items():
        trials = []
        for candidate, parameters in enumerate(candidates, start=1):
            if progress: progress(f"candidate_started horizon={horizon} target={target_name} task=classification model={model} candidate={candidate}/{len(candidates)}")
            trials.append({"parameters": parameters, **_candidate_validation(datasets, horizon, target_name, model, parameters, "classification")})
            if progress: progress(f"candidate_complete horizon={horizon} target={target_name} task=classification model={model} candidate={candidate}/{len(candidates)} score={trials[-1]['score']:.8f}")
        best = min(trials, key=lambda trial: trial["score"])
        selected[model + "_classifier"] = best["parameters"]
        scores[model + "_classifier"] = {"selected_parameters": best["parameters"], "validation": {key: best[key] for key in ("score", "metrics", "per_ticker", "folds", "validation_sample_count")}, "candidate_scores": [{"parameters": trial["parameters"], "score": trial["score"]} for trial in trials]}
    return selected, scores


def _holdout_predictions(train: list[dict], holdout: list[dict], horizon: int, target_name: str, selected: dict) -> tuple[dict, dict, dict]:
    base_rows, base = _decorate_rows(holdout, train, horizon, target_name)
    regression_predictions, classification_probabilities = {}, {}
    train_y = np.asarray([_target(row, horizon, target_name) for row in train], dtype=float)
    for model in REGRESSION_CANDIDATES:
        prediction, _ = _fit_predict(model, selected[model], train, base_rows, train_y, task="regression")
        regression_predictions[model] = prediction
    for model in CLASSIFICATION_CANDIDATES:
        model_name = model + "_classifier"
        valid = [_direction(row, horizon, target_name) is not None for row in train]
        clf_train = [row for row, use in zip(train, valid) if use]
        labels = np.asarray([_direction(row, horizon, target_name) for row in train if _direction(row, horizon, target_name) is not None], dtype=int)
        prediction, _ = _fit_predict(model, selected[model_name], clf_train, base_rows, labels, task="classification")
        classification_probabilities[model_name] = prediction
    classification_probabilities.update({
        "training_prevalence_probability": base["prevalence_probability"],
        "majority_class_direction": base["majority_direction"],
        "momentum_direction": base["momentum_direction"],
    })
    regression_predictions["historical_mean"] = base["historical_mean"]
    return base_rows, regression_predictions, classification_probabilities


def _feature_analysis(datasets: dict[str, dict]) -> dict:
    rows = select_rows(datasets, horizon=20, target_name="stock_return", end=date(2024, 9, 25))
    rows = [row for row in rows if _day(row) < HOLDOUT_START]
    early = [row for row in rows if _day(row) < date(2019, 1, 1)]
    validation = [row for row in rows if date(2020, 1, 1) <= _day(row) <= date(2024, 9, 25)]
    features = {}
    matrix = {}
    for name in FEATURE_NAMES:
        all_values = np.asarray([row["features"].get(name, np.nan) if row["features"].get(name) is not None else np.nan for row in rows], dtype=float)
        a = np.asarray([row["features"].get(name, np.nan) if row["features"].get(name) is not None else np.nan for row in early], dtype=float)
        b = np.asarray([row["features"].get(name, np.nan) if row["features"].get(name) is not None else np.nan for row in validation], dtype=float)
        av, bv = a[np.isfinite(a)], b[np.isfinite(b)]
        denominator = math.sqrt((float(av.var()) + float(bv.var())) / 2) if len(av) and len(bv) else 0.0
        features[name] = {
            "missing_fraction_pre_holdout": float(1 - np.isfinite(all_values).mean()),
            "early_count": len(av), "validation_count": len(bv),
            "early_mean": float(av.mean()) if len(av) else None,
            "validation_mean": float(bv.mean()) if len(bv) else None,
            "standardized_mean_shift": float((bv.mean() - av.mean()) / denominator) if denominator > 0 else None,
        }
        matrix[name] = all_values
    correlations = []
    for i, left in enumerate(FEATURE_NAMES):
        for right in FEATURE_NAMES[i + 1:]:
            a, b = matrix[left], matrix[right]
            valid = np.isfinite(a) & np.isfinite(b)
            if valid.sum() < 100 or np.std(a[valid]) == 0 or np.std(b[valid]) == 0:
                continue
            corr = float(np.corrcoef(a[valid], b[valid])[0, 1])
            if abs(corr) >= 0.95:
                correlations.append({"left": left, "right": right, "pearson": corr, "sample_count": int(valid.sum())})
    return {
        "sample_scope": "pre-holdout observations only; feature review does not inspect final holdout",
        "pre_holdout_row_count": len(rows), "early_period": ["2011-01-03", "2018-12-31"],
        "validation_period": ["2020-01-01", "2024-09-25"],
        "features": features, "high_pairwise_correlations_abs_ge_0_95": sorted(correlations, key=lambda x: -abs(x["pearson"])),
    }


def _validation_ablation(datasets: dict[str, dict], horizon: int, target_name: str, alpha: float) -> dict:
    result = {"full_feature_ridge_validation_mae": _candidate_validation(
        datasets, horizon, target_name, "ridge_regression", {"alpha": alpha}, "regression",
    )["score"]}
    for group, removed in FEATURE_GROUPS.items():
        actual, predicted = [], []
        keep = [name for name in FEATURE_NAMES if name not in removed]
        for fold in _validation_fold_data(datasets, horizon, target_name):
            y = np.asarray([_target(row, horizon, target_name) for row in fold["train"]], dtype=float)
            pred, _ = _fit_predict("ridge_regression", {"alpha": alpha}, fold["train"], fold["validation"], y, task="regression", feature_names=keep)
            actual.extend([_target(row, horizon, target_name) for row in fold["validation"]])
            predicted.extend(pred.tolist())
        result[group] = {"validation_mae": float(np.mean(np.abs(np.asarray(actual) - predicted))), "removed_features": list(removed), "feature_count_remaining": len(keep)}
    return result


def _permutation_importance_last_validation(datasets: dict[str, dict], horizon: int, target_name: str, model: str, parameters: dict) -> dict:
    from sklearn.inspection import permutation_importance
    fold = _validation_fold_data(datasets, horizon, target_name)[-1]
    train, validation = fold["train"], fold["validation"]
    processor = TrainOnlyPreprocessor().fit(train)
    x_train, x_val = processor.transform(train), processor.transform(validation)
    y_train = np.asarray([_target(row, horizon, target_name) for row in train], dtype=float)
    y_val = np.asarray([_target(row, horizon, target_name) for row in validation], dtype=float)
    if model == "ridge_regression":
        from sklearn.linear_model import Ridge
        estimator = Ridge(alpha=parameters["alpha"]).fit(x_train, y_train)
    else:
        estimator = _new_estimator("regression", model, parameters)
        estimator.fit(x_train, y_train)
    sample_size = min(500, len(validation))
    rng = np.random.default_rng(2718)
    selected = np.sort(rng.choice(len(validation), size=sample_size, replace=False))
    importance = permutation_importance(
        estimator, x_val[selected], y_val[selected], scoring="neg_mean_absolute_error",
        n_repeats=3, random_state=2718, n_jobs=1,
    )
    return {
        "validation_window": fold["name"], "sample_count": sample_size, "scoring": "increase in MAE after feature permutation; positive means the fitted model relied on that feature for lower validation MAE",
        "top_features": [{"feature": FEATURE_NAMES[i], "mae_increase": float(importance.importances_mean[i]), "std": float(importance.importances_std[i])} for i in np.argsort(importance.importances_mean)[::-1][:10]],
        "interpretation_limit": "Associational diagnostic only; correlated features can exchange or mask importance. Not a causal effect.",
    }


def _validation_baselines(datasets: dict[str, dict], horizon: int, target_name: str) -> dict:
    all_rows = []
    classification_labels, prevalence, majority, momentum = [], [], [], []
    for fold in _validation_fold_data(datasets, horizon, target_name):
        train, validation = fold["train"], fold["validation"]
        decorated, base = _decorate_rows(validation, train, horizon, target_name)
        all_rows.extend(decorated)
        prevalence.extend(base["prevalence_probability"].tolist())
        majority.extend(base["majority_direction"].tolist())
        momentum.extend(base["momentum_direction"].tolist())
        classification_labels.extend([
            -1 if _direction(row, horizon, target_name) is None else _direction(row, horizon, target_name)
            for row in validation
        ])
    zero = np.zeros(len(all_rows))
    historical = np.asarray([row["historical_mean_baseline"] for row in all_rows])
    regression = {
        "zero_return": _regression_metrics(all_rows, zero, target_name, horizon),
        "historical_mean": _regression_metrics(all_rows, historical, target_name, horizon),
    }
    labels = np.asarray(classification_labels, dtype=int)
    classification = {
        name: _classification_metrics(labels, np.asarray(values, dtype=float))
        for name, values in (
            ("training_prevalence_probability", prevalence),
            ("majority_class_direction", majority),
            ("momentum_direction", momentum),
        )
    }
    return {
        "validation_sample_count": len(all_rows), "regression": regression,
        "classification": classification,
        "validation_periods": [
            {"name": name, "start": start.isoformat(), "end": end.isoformat()}
            for name, start, end in VALIDATION_WINDOWS
        ],
    }


def run_phase5c(
    datasets: dict[str, dict], *, snapshot_manifest_sha256: str, source_hash: str,
    seed: int = 31415, progress: Callable[[str], None] | None = None,
) -> dict:
    """Select tabular models on pre-holdout validation and evaluate fixed holdout once."""
    results = []
    feature_analysis = _feature_analysis(datasets)
    for horizon in (5, 20):
        for target_name in ("stock_return", "excess_return"):
            if progress:
                progress(f"validation_started horizon={horizon} target={target_name}")
            selected, validation_selection = _select_models(datasets, horizon, target_name, progress)
            if progress:
                progress(f"validation_selected horizon={horizon} target={target_name} models={selected}")
            train, holdout = final_holdout_rows(datasets, horizon, target_name)
            if len(holdout) < 1000:
                raise ValueError(f"Final holdout is too small for {horizon}/{target_name}: {len(holdout)}")
            holdout_rows, regression_predictions, class_probabilities = _holdout_predictions(train, holdout, horizon, target_name, selected)
            regression_results = _evaluate_regression(holdout_rows, regression_predictions, horizon, target_name)
            classification_results = _evaluate_classification(holdout_rows, class_probabilities, horizon, target_name)
            regime_results = {}
            for regime in sorted({row.get("market_regime", "unavailable") for row in holdout_rows}):
                indices = [i for i, row in enumerate(holdout_rows) if row.get("market_regime", "unavailable") == regime]
                rows = [holdout_rows[i] for i in indices]
                regime_results[regime] = {"sample_count": len(rows)}
                for model, predictions in regression_predictions.items():
                    regime_results[regime][model] = _regression_metrics(rows, predictions[indices], target_name, horizon)
                regime_results[regime]["classification"] = _evaluate_classification(
                    rows, {name: probabilities[indices] for name, probabilities in class_probabilities.items()},
                    horizon, target_name, include_uncertainty=False,
                )
            best_regression = min(REGRESSION_CANDIDATES, key=lambda model: validation_selection[model]["validation"]["score"])
            results.append({
                "horizon_trading_sessions": horizon, "target_name": target_name,
                "validation_periods": [{"name": name, "start": start.isoformat(), "end": end.isoformat()} for name, start, end in VALIDATION_WINDOWS],
                "holdout_period": [min(row["forecast_anchor_date"] for row in holdout_rows), max(row["forecast_anchor_date"] for row in holdout_rows)],
                "holdout_start": HOLDOUT_START.isoformat(), "holdout_observation_count": len(holdout_rows),
                "holdout_ticker_observations": {ticker: sum(row["ticker"] == ticker for row in holdout_rows) for ticker in sorted(datasets)},
                "training_observation_count": len(train), "selected_hyperparameters": selected,
                "validation_model_selection": validation_selection,
                "validation_baselines": _validation_baselines(datasets, horizon, target_name),
                "holdout_regression": regression_results,
                "holdout_classification": classification_results,
                "holdout_metrics_by_market_regime": regime_results,
                "feature_ablation_validation_ridge": _validation_ablation(datasets, horizon, target_name, selected["ridge_regression"]["alpha"]),
                "validation_permutation_importance": _permutation_importance_last_validation(datasets, horizon, target_name, best_regression, selected[best_regression]),
            })
            if progress:
                progress(f"holdout_complete horizon={horizon} target={target_name} rows={len(holdout_rows)}")
    return {
        "schema_version": "finsight.phase5c.evaluation.v1", "dataset_kind": "real_provider_data",
        "data_snapshot_manifest_sha256": snapshot_manifest_sha256,
        "source_sha256": source_hash,
        "modeling_design": {
            "pooled_model": "A shared model is fit across the five fixed symbols without a ticker identity feature; per-ticker baselines and per-ticker holdout metrics are also reported.",
            "validation": "Five expanding calendar validation blocks from 2020 through 2024-09-25. Each training set includes only earlier anchors whose target window ended before that validation block.",
            "holdout": "Fixed final holdout anchors from 2024-10-24 through the last eligible 2026-10-23 anchor. All validation labels mature before holdout begins. Holdout is evaluated once after hyperparameters are selected.",
            "purge": "Training rows must have target_end_date strictly before the validation or holdout start. No validation label ends on or after 2024-10-24.",
            "preprocessing": "Median imputation and standardization are fitted separately on each training period; final holdout preprocessing is fitted only on the final pre-holdout training sample.",
            "final_holdout_tuning": False, "random_split": False,
            "direction_baselines": ["training-prevalence constant probability", "training-majority class", "momentum_20d for stock returns; relative_return_20d_vs_sp500 for excess returns"],
            "regression_baselines": ["zero return", "per-ticker training-period historical mean"],
            "fixed_random_state": seed,
            "uncertainty": "Paired circular moving-block bootstrap within ticker on final holdout, with block length equal to forecast horizon; descriptive intervals, not significance tests.",
        },
        "feature_analysis_pre_holdout_only": feature_analysis,
        "experiments": results,
        "limitations": [
            "Yahoo adjusted-price history can be retrospectively revised and is not point-in-time vintage data.",
            "The fixed current ticker universe has survivorship and historical constituent-membership bias.",
            "SPY is a benchmark proxy; XLK/XLY are sector proxies.",
            "Overlapping targets make observations dependent; intervals use moving blocks but do not establish significance.",
            "No news or SEC features are included; logistic and tree classifier scores are not calibrated probabilities.",
            "Targets are adjusted open-to-close return measurements, not an executable trading simulation.",
        ],
    }
