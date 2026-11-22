"""Deterministic checks for Phase 5A dataset and walk-forward isolation."""

import math
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from app.research.forecasting import (
    FEATURE_NAMES,
    TrainOnlyPreprocessor,
    build_point_in_time_dataset,
    aggregate_price_experiments,
    purged_walk_forward_splits,
    run_walk_forward_experiment,
    save_dataset,
    save_experiment,
)


def synthetic_bars(count: int, scale: float, phase: float = 0.0) -> list[dict]:
    rows, current_day, previous = [], date(2014, 1, 1), scale
    index = 0
    while len(rows) < count:
        if current_day.weekday() < 5:
            daily = 0.0003 + 0.012 * math.sin((index + phase) * 0.71)
            open_price = previous * (1 + 0.002 * math.cos(index * 0.31 + phase))
            close = previous * (1 + daily)
            rows.append({
                "date": current_day.isoformat(), "open": open_price,
                "high": max(open_price, close) * 1.008,
                "low": min(open_price, close) * 0.992,
                "close": close, "volume": 100_000 + (index % 23) * 1200,
            })
            previous, index = close, index + 1
        current_day += timedelta(days=1)
    return rows


class ForecastResearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = synthetic_bars(760, 100)
        benchmark = synthetic_bars(760, 400, 2.5)
        sector = synthetic_bars(760, 80, 4.0)
        cls.dataset = build_point_in_time_dataset(
            "SYNTH", stock, benchmark, sector, sector="Financials",
            data_source="Deterministic synthetic fixture; not market observations.",
        )

    def test_dataset_features_cutoff_and_targets_start_after_anchor(self):
        dataset = self.dataset
        self.assertGreater(len(dataset["rows"]), 200)
        row = dataset["rows"][100]
        anchor = row["forecast_anchor_date"]
        self.assertEqual(row["feature_as_of_date"], anchor)
        self.assertLessEqual(row["feature_observation_date"], anchor)
        self.assertEqual(set(row["features"]), set(FEATURE_NAMES))
        self.assertIn(row["market_regime"], {"uptrend", "downtrend", "sideways", "high_volatility", "low_volatility", "insufficient_history"})
        for target in row["targets"].values():
            self.assertGreater(target["target_start_date"], anchor)
            self.assertGreater(target["target_end_date"], anchor)
            self.assertEqual(target["entry_method"], "next trading session adjusted open")
        self.assertIn("Yahoo Finance history can be revised", dataset["limitations"][0])

    def test_future_bars_cannot_change_historical_features(self):
        stock = synthetic_bars(500, 100)
        benchmark = synthetic_bars(500, 400, 2.5)
        sector = synthetic_bars(500, 80, 4.0)
        before = build_point_in_time_dataset("SYNTH", stock, benchmark, sector, sector="Financials", minimum_history=253)
        anchor_date = before["rows"][50]["forecast_anchor_date"]
        changed = [dict(bar) for bar in stock]
        changed_benchmark = [dict(bar) for bar in benchmark]
        changed_sector = [dict(bar) for bar in sector]
        for bar in changed:
            if bar["date"] > anchor_date:
                bar["open"] *= 100
                bar["high"] *= 100
                bar["low"] *= 100
                bar["close"] *= 100
                bar["volume"] *= 100
        for bars_to_change in (changed_benchmark, changed_sector):
            for bar in bars_to_change:
                if bar["date"] > anchor_date:
                    for column in ("open", "high", "low", "close"):
                        bar[column] *= 50
        after = build_point_in_time_dataset("SYNTH", changed, changed_benchmark, changed_sector, sector="Financials", minimum_history=253)
        before_row = next(row for row in before["rows"] if row["forecast_anchor_date"] == anchor_date)
        after_row = next(row for row in after["rows"] if row["forecast_anchor_date"] == anchor_date)
        self.assertEqual(before_row["features"], after_row["features"])

    def test_dataset_records_the_benchmark_series_actually_supplied(self):
        stock = synthetic_bars(300, 100)
        spy = synthetic_bars(300, 400, 2.5)
        dataset = build_point_in_time_dataset(
            "SYNTH", stock, spy, minimum_history=253,
            benchmark_ticker="SPY",
            benchmark_source="Local test fixture for adjusted SPY proxy",
        )
        self.assertEqual(dataset["benchmark"]["ticker"], "SPY")
        self.assertEqual(dataset["rows"][0]["benchmark"]["ticker"], "SPY")

    def test_walk_forward_purges_overlapping_labels_and_stays_chronological(self):
        rows = self.dataset["rows"]
        splits = purged_walk_forward_splits(rows, 20, "stock_return")
        self.assertGreaterEqual(len(splits), 3)
        for split in splits:
            train, validation, test = split["train"], split["validation"], split["test"]
            validation_start = rows[validation[0]]["forecast_anchor_date"]
            test_start = rows[test[0]]["forecast_anchor_date"]
            self.assertLess(rows[train[-1]]["forecast_anchor_date"], validation_start)
            self.assertLess(rows[validation[-1]]["forecast_anchor_date"], test_start)
            self.assertTrue(all(rows[i]["targets"]["20"]["target_end_date"] < validation_start for i in train))
            self.assertTrue(all(rows[i]["targets"]["20"]["target_end_date"] < test_start for i in validation))

    def test_preprocessing_is_fitted_on_train_rows_only(self):
        train = [
            {"features": {"x": 1.0, "y": None}},
            {"features": {"x": 3.0, "y": None}},
        ]
        validation = [{"features": {"x": 1000.0, "y": 50.0}}]
        processor = TrainOnlyPreprocessor(("x", "y")).fit(train)
        train_mean, train_median = processor.means["x"], processor.medians["x"]
        transformed = processor.transform(validation)
        self.assertEqual(processor.means["x"], train_mean)
        self.assertEqual(processor.medians["x"], train_median)
        self.assertNotIn("y", processor.active_features)
        self.assertGreater(transformed[0, 0], 100)

    def test_experiment_emits_only_test_predictions_and_can_persist_metadata(self):
        result = run_walk_forward_experiment(self.dataset, horizon=5, target_name="stock_return", code_version="fixture")
        self.assertGreaterEqual(len(result["folds"]), 3)
        self.assertEqual(result["configuration"]["random_split"], False)
        self.assertEqual(result["data_source"], self.dataset["data_source"])
        self.assertTrue(result["out_of_sample_predictions"])
        self.assertTrue(result["metrics_by_market_regime"])
        for fold in result["folds"]:
            self.assertEqual(fold["sample_counts"]["test"], len(fold["out_of_sample_predictions"]))
            self.assertIn("mae", fold["regression_metrics"]["ridge_regression"])
            self.assertIn("directional_accuracy", fold["regression_metrics"]["ridge_regression"])
            if fold["direction_logistic_metrics"] and "status" not in fold["direction_logistic_metrics"]:
                self.assertIn("brier_score", fold["direction_logistic_metrics"])
        aggregate = aggregate_price_experiments([result], bootstrap_repetitions=100, seed=7)
        self.assertTrue(aggregate["baseline_comparison_uses_identical_oos_observations"])
        self.assertEqual(aggregate["per_stock"][0]["ticker"], "SYNTH")
        self.assertIn("interval_95_percentile", aggregate["paired_mae_uncertainty_intervals"]["ridge_vs_zero"])
        self.assertIn("not a significance test", aggregate["paired_mae_uncertainty_intervals"]["ridge_vs_zero"]["method"])
        with TemporaryDirectory() as directory:
            dataset_path = save_dataset(self.dataset, Path(directory) / "dataset.json")
            path = save_experiment(result, Path(directory) / "experiment.json")
            self.assertTrue(dataset_path.is_file())
            self.assertTrue(path.is_file())
            self.assertIn('"experiment_id"', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
