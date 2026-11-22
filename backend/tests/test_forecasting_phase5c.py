"""Deterministic checks for Phase 5C chronology, baselines, and CPU models."""

from datetime import date, timedelta
import importlib.util
import unittest

import numpy as np

from app.research.forecasting_phase5c import (
    CLASSIFICATION_CANDIDATES,
    HOLDOUT_START,
    REGRESSION_CANDIDATES,
    VALIDATION_WINDOWS,
    _classification_metrics,
    _classification_block_intervals,
    _fit_predict,
    final_holdout_rows,
    validation_rows,
    validation_training_rows,
)
from app.research.forecasting import FEATURE_NAMES


def _row(anchor: date, end: date, label: int) -> dict:
    features = {name: None for name in FEATURE_NAMES}
    features["momentum_20d"] = float(label - 0.5)
    features["relative_return_20d_vs_sp500"] = float(label - 0.5)
    return {
        "forecast_anchor_date": anchor.isoformat(), "features": features,
        "targets": {
            "5": {"stock_return": 0.01 if label else -0.01, "excess_return": 0.005 if label else -0.005,
                  "target_end_date": end.isoformat(), "stock_direction": label, "excess_direction": label},
            "20": {"stock_return": 0.02 if label else -0.02, "excess_return": 0.01 if label else -0.01,
                   "target_end_date": end.isoformat(), "stock_direction": label, "excess_direction": label},
        },
    }


class ForecastingPhase5CTest(unittest.TestCase):
    def test_validation_and_holdout_rows_obey_anchor_and_target_maturity_cutoffs(self):
        rows = [
            _row(date(2024, 10, 22), date(2024, 10, 23), 1),
            _row(date(2024, 10, 23), date(2024, 10, 24), 0),
            _row(date(2024, 10, 24), date(2024, 10, 31), 1),
        ]
        datasets = {"AAPL": {"rows": rows}}
        training = validation_training_rows(datasets, 5, "stock_return", HOLDOUT_START)
        self.assertEqual([row["forecast_anchor_date"] for row in training], ["2024-10-22"])
        validation = validation_rows(datasets, 5, "stock_return", date(2024, 10, 22), date(2024, 10, 23))
        self.assertEqual([row["forecast_anchor_date"] for row in validation], ["2024-10-22"])
        final_train, holdout = final_holdout_rows(datasets, 5, "stock_return")
        self.assertEqual([row["forecast_anchor_date"] for row in final_train], ["2024-10-22"])
        self.assertEqual([row["forecast_anchor_date"] for row in holdout], ["2024-10-24"])

    def test_validation_windows_are_fixed_and_end_before_holdout(self):
        self.assertEqual(len(VALIDATION_WINDOWS), 5)
        self.assertTrue(all(end < HOLDOUT_START for _, _, end in VALIDATION_WINDOWS))
        self.assertEqual(len(REGRESSION_CANDIDATES["random_forest"]), 2)
        self.assertEqual(len(CLASSIFICATION_CANDIDATES["hist_gradient_boosting"]), 2)

    def test_classification_metrics_ignore_exact_zero_unlabelled_rows_and_report_log_loss(self):
        metrics = _classification_metrics(np.asarray([1, 0, -1]), np.asarray([0.8, 0.3, 0.9]))
        self.assertEqual(metrics["sample_count"], 2)
        self.assertEqual(metrics["directional_accuracy"], 1.0)
        self.assertEqual(metrics["balanced_accuracy"], 1.0)
        self.assertLessEqual(metrics["brier_score"], 0.065)
        self.assertLess(metrics["log_loss"], 0.3)

    @unittest.skipUnless(importlib.util.find_spec("sklearn"), "install the optional research extra")
    def test_random_forest_and_hist_gradient_boosting_are_reproducible(self):
        train = [{"features": {"momentum_20d": float(i)}} for i in range(40)]
        predict = [{"features": {"momentum_20d": float(i)}} for i in range(40, 45)]
        y = np.asarray([float(i) * 0.01 + (0.1 if i % 2 else 0) for i in range(40)])
        models = (
            ("random_forest", {"n_estimators": 12, "max_depth": 4, "min_samples_leaf": 2, "max_features": 1.0}),
            ("hist_gradient_boosting", {"learning_rate": 0.1, "max_iter": 12, "max_leaf_nodes": 7, "l2_regularization": 1.0}),
        )
        for model, parameters in models:
            first, _ = _fit_predict(model, parameters, train, predict, y, task="regression", feature_names=("momentum_20d",))
            second, _ = _fit_predict(model, parameters, train, predict, y, task="regression", feature_names=("momentum_20d",))
            np.testing.assert_allclose(first, second, rtol=0, atol=0)

    def test_overlapping_directional_scores_use_reproducible_blocks_and_small_samples_are_flagged(self):
        dates = []
        current = date(2024, 1, 1)
        while len(dates) < 40:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        rows = [{"ticker": "AAPL", **_row(day, day + timedelta(days=1), index % 2)} for index, day in enumerate(dates)]
        probabilities = np.asarray([0.55 if index % 2 else 0.45 for index in range(40)])
        result = _classification_block_intervals(rows, {
            "training_prevalence_probability": np.full(40, 0.5),
            "logistic_regression": probabilities,
        }, 5, "stock_return")
        self.assertGreater(result["logistic_regression"]["baseline_minus_model_brier"], 0)
        self.assertEqual(len(result["logistic_regression"]["block_bootstrap_95_percentile"]), 2)
        small = _classification_block_intervals(rows[:3], {
            "training_prevalence_probability": np.full(3, 0.5),
            "logistic_regression": probabilities[:3],
        }, 20, "stock_return")
        self.assertEqual(small["logistic_regression"]["status"], "insufficient_sample_for_block_interval")

if __name__ == "__main__":
    unittest.main()
