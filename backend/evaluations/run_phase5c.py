"""Run Phase 5C model selection and final holdout on a validated Phase 5B snapshot."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from app.research.forecasting_phase5c import run_phase5c
from app.research.market_data import file_sha256, load_market_snapshot


def _source_hash() -> str:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(), root / "app/research/forecasting_phase5c.py",
        root / "app/research/forecasting.py", root / "app/research/market_data.py",
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run(snapshot_dir: Path, output_dir: Path) -> Path:
    result_path = output_dir / "phase5c_evaluation.json"
    if result_path.exists():
        raise FileExistsError(f"Final holdout result already exists and will not be overwritten: {result_path}")
    loaded = load_market_snapshot(snapshot_dir)
    manifest_hash = file_sha256(snapshot_dir / "manifest.json")
    artifact_dir = snapshot_dir / "research_output"
    datasets = {}
    for ticker in loaded["series"]:
        if ticker not in {"AAPL", "MSFT", "NVDA", "AMZN", "TSLA"}:
            continue
        path = artifact_dir / f"real_point_in_time_dataset_{ticker}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Existing Phase 5B feature artifact is missing: {path}")
        dataset = json.loads(path.read_text(encoding="utf-8"))
        if dataset.get("dataset_kind") != "real_provider_data":
            raise ValueError(f"Refusing non-real feature artifact for {ticker}.")
        if dataset.get("snapshot_manifest_sha256") != manifest_hash:
            raise ValueError(f"Phase 5B dataset for {ticker} does not match this snapshot manifest.")
        if dataset.get("row_count") != len(dataset.get("rows", [])):
            raise ValueError(f"Phase 5B dataset row count mismatch for {ticker}.")
        datasets[ticker] = dataset
    if set(datasets) != {"AAPL", "MSFT", "NVDA", "AMZN", "TSLA"}:
        raise ValueError(f"Five validated company datasets are required; found: {sorted(datasets)}")

    result = run_phase5c(
        datasets, snapshot_manifest_sha256=manifest_hash, source_hash=_source_hash(),
        progress=lambda message: print(message, flush=True),
    )
    result["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["experiment_id"] = f"phase5c-{manifest_hash[:12]}-{result['generated_at_utc'].replace(':', '').replace('-', '')[:13]}"
    result["source"] = loaded["manifest"]
    result["snapshot_data_quality_report"] = loaded["quality_report"]
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary_path = result_path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    temporary_path.replace(result_path)
    print(f"phase5c_output={result_path}", flush=True)
    return result_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, help="Validated Phase 5B market snapshot directory")
    parser.add_argument("--output-dir", help="Defaults to <input-dir>/phase5c_output")
    args = parser.parse_args()
    snapshot = Path(args.input_dir)
    output = Path(args.output_dir) if args.output_dir else snapshot / "phase5c_output"
    run(snapshot, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
