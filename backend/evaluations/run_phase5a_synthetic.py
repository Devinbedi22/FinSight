"""Generate clearly synthetic point-in-time samples and baseline experiment JSON."""

from __future__ import annotations

from datetime import date, timedelta
import hashlib
import random
import subprocess
from pathlib import Path

from app.research.forecasting import build_point_in_time_dataset, run_walk_forward_experiment, save_dataset, save_experiment


def synthetic_bars(count: int, seed: int, start_price: float, drift: float, daily_vol: float) -> list[dict]:
    rng = random.Random(seed)
    current = start_price
    previous_close = current
    current_day = date(2015, 1, 1)
    rows = []
    while len(rows) < count:
        if current_day.weekday() < 5:
            gap_return = rng.gauss(0, daily_vol / 3)
            open_price = previous_close * (1 + gap_return)
            current *= 1 + rng.gauss(drift, daily_vol)
            high = max(open_price, current) * (1 + abs(rng.gauss(0, daily_vol / 3)))
            low = min(open_price, current) * (1 - abs(rng.gauss(0, daily_vol / 3)))
            rows.append({
                "date": current_day.isoformat(), "open": open_price, "high": high,
                "low": low, "close": current, "volume": int(rng.lognormvariate(13, 0.35)),
            })
            previous_close = current
        current_day += timedelta(days=1)
    return rows


def main() -> None:
    root = Path(__file__).resolve().parent
    stock = synthetic_bars(800, 41, 100, 0.0003, 0.012)
    benchmark = synthetic_bars(800, 97, 400, 0.00025, 0.009)
    sector = synthetic_bars(800, 211, 80, 0.00028, 0.011)
    dataset = build_point_in_time_dataset(
        "SYNTH", stock, benchmark, sector, sector="Financials",
        data_source="Deterministic synthetic fixture (random seed fixed); not observed or historical market data.",
    )
    dataset["fixture_kind"] = "synthetic_only"
    dataset["fixture_configuration"] = {
        "sessions_per_series": 800,
        "stock_seed": 41, "benchmark_seed": 97, "sector_seed": 211,
        "synthetic_start_date": "2015-01-01", "sector_label": "Financials",
    }
    dataset_path = save_dataset(dataset, root / "forecast_phase5a_synthetic_dataset.json")
    try:
        git_head = subprocess.check_output(
            ["git", "-C", str(root.parent), "rev-parse", "--short", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        git_head = "unavailable"
    digest = hashlib.sha256()
    for source_file in (
        Path(__file__).resolve(),
        root.parent / "app" / "research" / "forecasting.py",
        root.parent / "app" / "services" / "market_context.py",
    ):
        digest.update(source_file.name.encode())
        digest.update(source_file.read_bytes())
    code_version = f"git_head={git_head}; source_sha256={digest.hexdigest()}"
    experiments = []
    for horizon in (5, 20):
        for target_name in ("stock_return", "excess_return"):
            experiments.append(run_walk_forward_experiment(
                dataset, horizon=horizon, target_name=target_name, code_version=code_version,
            ))
    output = {
        "fixture_kind": "synthetic_only",
        "warning": "These metrics validate the pipeline mechanics only. They are not real-market evaluation and are not evidence of predictive value or profitability.",
        "dataset_summary": {
            "schema_version": dataset["schema_version"], "ticker": dataset["ticker"],
            "row_count": dataset["row_count"], "feature_names": dataset["feature_names"],
            "data_source": dataset["data_source"],
            "fixture_configuration": dataset["fixture_configuration"],
            "anchor_period": [dataset["rows"][0]["forecast_anchor_date"], dataset["rows"][-1]["forecast_anchor_date"]] if dataset["rows"] else None,
        },
        "experiments": experiments,
    }
    path = save_experiment(output, root / "forecast_phase5a_synthetic.json")
    print(f"fixture_kind=synthetic_only")
    print(f"dataset_rows={dataset['row_count']}")
    print(f"dataset_artifact={dataset_path}")
    for experiment in experiments:
        print(
            f"horizon={experiment['horizon_trading_sessions']} target={experiment['target_name']} "
            f"folds={len(experiment['folds'])} test_predictions={len(experiment['out_of_sample_predictions'])} "
            f"ridge_metrics={experiment['overall_out_of_sample_metrics'].get('ridge_regression')}"
        )
    print(f"experiment_metadata={path}")


if __name__ == "__main__":
    main()
