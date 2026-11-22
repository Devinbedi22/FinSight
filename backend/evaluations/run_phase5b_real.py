"""Build real-data point-in-time rows and purged baseline evaluation from a local snapshot."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from app.research.forecasting import (
    aggregate_price_experiments,
    build_point_in_time_dataset,
    run_walk_forward_experiment,
    save_dataset,
    save_experiment,
)
from app.research.market_data import (
    BENCHMARK_TICKER,
    GICS_SECTOR_BY_TICKER,
    SECTOR_PROXY_BY_TICKER,
    STOCK_TICKERS,
    file_sha256,
    load_market_snapshot,
)


def _source_version() -> str:
    root = Path(__file__).resolve().parents[1]
    try:
        revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unavailable"
    digest = hashlib.sha256()
    for path in (
        Path(__file__).resolve(), root / "app/research/forecasting.py",
        root / "app/research/market_data.py", root / "app/services/market_context.py",
    ):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return f"git_head={revision}; source_sha256={digest.hexdigest()}"


def run(snapshot_dir: Path, output_dir: Path, *, bootstrap_repetitions: int = 500) -> dict:
    loaded = load_market_snapshot(snapshot_dir)
    manifest = loaded["manifest"]
    series = loaded["series"]
    if BENCHMARK_TICKER not in series:
        raise ValueError(f"S&P 500 proxy {BENCHMARK_TICKER} missing from local snapshot")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_hash = file_sha256(snapshot_dir / "manifest.json")
    source = f"Yahoo Finance via yfinance; local snapshot manifest sha256={manifest_hash}"
    code_version = _source_version()
    datasets, experiments, exclusions = {}, [], {}
    for ticker in STOCK_TICKERS:
        if ticker not in series:
            exclusions[ticker] = "No validated series in the snapshot."
            continue
        sector_proxy = SECTOR_PROXY_BY_TICKER[ticker]
        if sector_proxy not in series:
            sector_points = []
            sector_note = f"Sector proxy {sector_proxy} unavailable; sector features remain null."
        else:
            sector_points = series[sector_proxy]
            sector_note = None
        dataset = build_point_in_time_dataset(
            ticker, series[ticker], series[BENCHMARK_TICKER], sector_points,
            sector=GICS_SECTOR_BY_TICKER[ticker],
            data_source=source,
            benchmark_ticker=BENCHMARK_TICKER,
            benchmark_source="Yahoo Finance via yfinance (SPY adjusted OHLCV; S&P 500 ETF proxy, distributions adjusted by provider)",
        )
        dataset["dataset_kind"] = "real_provider_data"
        dataset["snapshot_manifest_sha256"] = manifest_hash
        dataset["source_retrieved_at_utc"] = manifest["retrieved_at_utc"]
        dataset["sector_proxy_note"] = sector_note
        datasets[ticker] = {
            "row_count": dataset["row_count"],
            "anchor_period": [dataset["rows"][0]["forecast_anchor_date"], dataset["rows"][-1]["forecast_anchor_date"]] if dataset["rows"] else None,
            "feature_artifact": str(save_dataset(dataset, output_dir / f"real_point_in_time_dataset_{ticker}.json")),
            "source_retrieved_at_utc": manifest["retrieved_at_utc"],
            "sector_proxy": sector_proxy,
            "gics_sector": GICS_SECTOR_BY_TICKER[ticker],
            "sector_proxy_note": sector_note,
        }
        if dataset["row_count"] < 100:
            exclusions[ticker] = f"Only {dataset['row_count']} feature rows; insufficient for the configured walk-forward evaluation."
            continue
        for horizon in (5, 20):
            for target_name in ("stock_return", "excess_return"):
                experiment = run_walk_forward_experiment(
                    dataset, horizon=horizon, target_name=target_name, code_version=code_version,
                )
                experiment["dataset_kind"] = "real_provider_data"
                experiment["snapshot_manifest_sha256"] = manifest_hash
                experiment["source_retrieved_at_utc"] = manifest["retrieved_at_utc"]
                experiment["sector_proxy"] = sector_proxy
                experiment["gics_sector"] = GICS_SECTOR_BY_TICKER[ticker]
                one_stock_summary = aggregate_price_experiments(
                    [experiment], bootstrap_repetitions=bootstrap_repetitions,
                    seed=1200 + len(experiments),
                )
                experiment["paired_mae_uncertainty_intervals"] = one_stock_summary.get("paired_mae_uncertainty_intervals", {})
                experiments.append(experiment)
    aggregates = []
    for horizon in (5, 20):
        for target_name in ("stock_return", "excess_return"):
            selected = [item for item in experiments if item["horizon_trading_sessions"] == horizon and item["target_name"] == target_name]
            aggregate = aggregate_price_experiments(
                selected, bootstrap_repetitions=bootstrap_repetitions,
                seed=1000 + horizon + (1 if target_name == "excess_return" else 0),
            )
            aggregate["dataset_kind"] = "real_provider_data"
            aggregates.append(aggregate)
    result = {
        "schema_version": "finsight.phase5b.real-evaluation.v1",
        "dataset_kind": "real_provider_data",
        "experiment_id": f"phase5b-yahoo-{manifest_hash[:12]}",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_version": code_version,
        "source": manifest,
        "snapshot_manifest_sha256": manifest_hash,
        "data_quality_report": loaded["quality_report"],
        "fixed_universe": list(STOCK_TICKERS),
        "benchmark_proxy": BENCHMARK_TICKER,
        "sector_proxies": SECTOR_PROXY_BY_TICKER,
        "gics_sectors": GICS_SECTOR_BY_TICKER,
        "dataset_counts": datasets,
        "exclusions": exclusions,
        "per_stock_experiments": experiments,
        "aggregate_experiments": aggregates,
        "interpretation": "Observed historical predictive metrics only. Logistic scores are uncalibrated. No statistical significance, trading profitability, or executable strategy claim is made.",
    }
    result_path = save_experiment(result, output_dir / "real_market_evaluation.json")
    result["result_file"] = str(result_path)
    print(f"dataset_kind=real_provider_data source=Yahoo Finance via yfinance")
    print(f"snapshot_retrieved_at={manifest['retrieved_at_utc']}")
    for ticker, summary in datasets.items():
        print(f"ticker={ticker} rows={summary['row_count']} anchors={summary['anchor_period']}")
    for aggregate in aggregates:
        metrics = aggregate.get("aggregate_metrics", {})
        ridge = metrics.get("ridge_regression", {})
        print(f"horizon={aggregate.get('horizon_trading_sessions')} target={aggregate.get('target_name')} oos_n={aggregate.get('oos_observation_count', 0)} ridge={ridge}")
    print(f"evaluation_file={result_path}")
    if not experiments:
        print("No stock had sufficient real data for walk-forward evaluation; no real performance metrics were generated.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, help="Snapshot directory printed by download_market_data.py")
    parser.add_argument("--output-dir", help="Defaults to <input-dir>/research_output")
    parser.add_argument("--bootstrap-repetitions", type=int, default=500)
    args = parser.parse_args()
    snapshot_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else snapshot_dir / "research_output"
    run(snapshot_dir, output_dir, bootstrap_repetitions=args.bootstrap_repetitions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
