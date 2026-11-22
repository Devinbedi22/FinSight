"""Append-only, research-only forward forecast tracking.

The production forecast API is deliberately not imported here. Forecast records,
market snapshot archives, and later outcome assessments live in a separate local
SQLite registry and are immutable once inserted.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Any
import uuid

import numpy as np

from app.research.forecasting import (
    DATASET_SCHEMA_VERSION,
    _make_features,
    build_point_in_time_dataset,
    save_dataset,
)
from app.research.forecasting_phase5c import _fit_predict, _target, select_rows
from app.research.market_data import (
    BENCHMARK_TICKER,
    GICS_SECTOR_BY_TICKER,
    SECTOR_PROXY_BY_TICKER,
    STOCK_TICKERS,
    file_sha256,
    load_market_snapshot,
)
from app.services.market_context import calculate_market_context


REGISTRY_SCHEMA_VERSION = "finsight.forecast-registry.v1"
FEATURE_SCHEMA_VERSION = DATASET_SCHEMA_VERSION
FIXED_MODEL_ID = "ridge_regression"
FIXED_MODEL_VERSION = "phase5c_validation_ridge_alpha10_v1"
FIXED_MODEL_PARAMETERS = {"alpha": 10.0}
MODEL_DEFINITIONS = {
    "zero_return": {"version": "research_baseline_v1", "parameters": {}},
    "historical_mean": {"version": "ticker_training_mean_v1", "parameters": {"statistic": "mean of mature training-period target returns"}},
    FIXED_MODEL_ID: {
        "version": FIXED_MODEL_VERSION,
        "parameters": FIXED_MODEL_PARAMETERS,
        "selection_note": "Fixed alpha selected by Phase 5C pre-holdout chronological validation; not retuned on the final holdout.",
    },
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def stable_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _save_feature_cache_atomically(dataset: dict, path: Path) -> None:
    """Publish a feature cache only after the complete JSON artifact is written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.partial")
    try:
        save_dataset(dataset, temporary)
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing feature cache: {path}")
        os.rename(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(path: str | Path) -> sqlite3.Connection:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(destination, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_registry(path: str | Path) -> None:
    """Create the local registry and database-enforced append-only tables."""
    with _connect(path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS registry_metadata (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY,
                manifest_sha256 TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                retrieved_at_utc TEXT NOT NULL,
                registered_at_utc TEXT NOT NULL,
                archive_path TEXT NOT NULL,
                quality_notes_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS snapshot_bars (
                snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
                ticker TEXT NOT NULL,
                session_date TEXT NOT NULL,
                bar_sha256 TEXT NOT NULL,
                PRIMARY KEY (snapshot_id, ticker, session_date)
            );
            CREATE TABLE IF NOT EXISTS snapshot_revisions (
                revision_id TEXT PRIMARY KEY,
                earlier_snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
                later_snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
                ticker TEXT NOT NULL,
                session_date TEXT NOT NULL,
                earlier_bar_sha256 TEXT NOT NULL,
                later_bar_sha256 TEXT NOT NULL,
                detected_at_utc TEXT NOT NULL,
                UNIQUE (earlier_snapshot_id, later_snapshot_id, ticker, session_date)
            );
            CREATE TABLE IF NOT EXISTS forecasts (
                forecast_id TEXT PRIMARY KEY,
                unique_key TEXT NOT NULL UNIQUE,
                ticker TEXT NOT NULL,
                target_name TEXT NOT NULL CHECK (target_name IN ('stock_return', 'excess_return')),
                forecast_created_at_utc TEXT NOT NULL,
                forecast_anchor_session TEXT NOT NULL,
                information_cutoff TEXT NOT NULL,
                model_identifier TEXT NOT NULL,
                model_version TEXT NOT NULL,
                model_parameters_json TEXT NOT NULL,
                model_parameters_sha256 TEXT NOT NULL,
                feature_schema_version TEXT NOT NULL,
                feature_values_json TEXT NOT NULL,
                feature_values_sha256 TEXT NOT NULL,
                dataset_snapshot_identifier TEXT NOT NULL REFERENCES snapshots(snapshot_id),
                dataset_manifest_sha256 TEXT NOT NULL,
                source TEXT NOT NULL,
                source_retrieved_at_utc TEXT NOT NULL,
                prediction_horizon INTEGER NOT NULL CHECK (prediction_horizon IN (5, 20)),
                predicted_return REAL NOT NULL,
                predicted_direction INTEGER NOT NULL CHECK (predicted_direction IN (0, 1)),
                prediction_status TEXT NOT NULL CHECK (prediction_status = 'pending'),
                evaluation_eligibility_date TEXT,
                training_row_count INTEGER NOT NULL,
                training_anchor_start TEXT NOT NULL,
                training_anchor_end TEXT NOT NULL,
                training_label_cutoff TEXT NOT NULL,
                training_snapshot_identifier TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outcomes (
                outcome_id TEXT PRIMARY KEY,
                forecast_id TEXT NOT NULL REFERENCES forecasts(forecast_id),
                evaluation_snapshot_identifier TEXT NOT NULL REFERENCES snapshots(snapshot_id),
                evaluation_manifest_sha256 TEXT NOT NULL,
                evaluated_at_utc TEXT NOT NULL,
                outcome_status TEXT NOT NULL CHECK (outcome_status IN ('complete', 'incomplete_missing_stock_sessions')),
                target_start_session TEXT,
                target_end_session TEXT,
                realized_stock_return REAL,
                realized_benchmark_return REAL,
                realized_excess_return REAL,
                realized_target_return REAL,
                realized_direction INTEGER CHECK (realized_direction IN (0, 1) OR realized_direction IS NULL),
                evaluation_eligibility_date TEXT,
                data_revision_notes_json TEXT NOT NULL,
                observed_bar_hashes_json TEXT NOT NULL,
                UNIQUE (forecast_id, evaluation_snapshot_identifier)
            );
            CREATE TABLE IF NOT EXISTS research_references (
                reference_id TEXT PRIMARY KEY,
                artifact_sha256 TEXT NOT NULL,
                snapshot_manifest_sha256 TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                registered_at_utc TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS references_no_update BEFORE UPDATE ON research_references
            BEGIN SELECT RAISE(ABORT, 'research reference records are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS references_no_delete BEFORE DELETE ON research_references
            BEGIN SELECT RAISE(ABORT, 'research reference records are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS forecasts_no_update BEFORE UPDATE ON forecasts
            BEGIN SELECT RAISE(ABORT, 'forecast records are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS forecasts_no_delete BEFORE DELETE ON forecasts
            BEGIN SELECT RAISE(ABORT, 'forecast records are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS outcomes_no_update BEFORE UPDATE ON outcomes
            BEGIN SELECT RAISE(ABORT, 'outcome records are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS outcomes_no_delete BEFORE DELETE ON outcomes
            BEGIN SELECT RAISE(ABORT, 'outcome records are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS snapshots_no_update BEFORE UPDATE ON snapshots
            BEGIN SELECT RAISE(ABORT, 'snapshot records are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS snapshots_no_delete BEFORE DELETE ON snapshots
            BEGIN SELECT RAISE(ABORT, 'snapshot records are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS snapshot_bars_no_update BEFORE UPDATE ON snapshot_bars
            BEGIN SELECT RAISE(ABORT, 'snapshot bar records are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS snapshot_bars_no_delete BEFORE DELETE ON snapshot_bars
            BEGIN SELECT RAISE(ABORT, 'snapshot bar records are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS revisions_no_update BEFORE UPDATE ON snapshot_revisions
            BEGIN SELECT RAISE(ABORT, 'snapshot revision records are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS revisions_no_delete BEFORE DELETE ON snapshot_revisions
            BEGIN SELECT RAISE(ABORT, 'snapshot revision records are immutable'); END;
            """
        )
        db.execute(
            "INSERT OR IGNORE INTO registry_metadata(key, value_json, created_at_utc) VALUES (?, ?, ?)",
            ("schema_version", canonical_json(REGISTRY_SCHEMA_VERSION), _utc_now()),
        )


def _snapshot_bar_hashes(snapshot_dir: Path, manifest: dict) -> list[tuple[str, str, str]]:
    result = []
    for ticker, series_info in sorted(manifest["series"].items()):
        with (snapshot_dir / series_info["file"]).open("r", newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                normalized = {}
                for key, value in row.items():
                    try:
                        number = Decimal(value) if value not in (None, "") else None
                        normalized[key] = format(number.normalize(), "f") if number is not None and number.is_finite() else value
                    except (InvalidOperation, ValueError):
                        normalized[key] = value
                result.append((ticker, row["date"], stable_sha256(normalized)))
    return result


def register_snapshot(snapshot_dir: str | Path, registry_path: str | Path, store_root: str | Path) -> dict:
    """Verify and archive a provider snapshot, recording revisions by bar date."""
    source_dir = Path(snapshot_dir).resolve()
    loaded = load_market_snapshot(source_dir, verify_hashes=True)
    manifest = loaded["manifest"]
    manifest_path = source_dir / "manifest.json"
    manifest_hash = file_sha256(manifest_path)
    snapshot_id = f"yahoo-{manifest_hash[:20]}"
    root = Path(store_root).resolve()
    archive = root / "snapshots" / snapshot_id
    initialize_registry(registry_path)
    bars = _snapshot_bar_hashes(source_dir, manifest)
    with _connect(registry_path) as db:
        existing = db.execute("SELECT * FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
        if existing:
            if existing["manifest_sha256"] != manifest_hash:
                raise ValueError("Snapshot identifier collision with different manifest hash.")
            return {"snapshot_id": snapshot_id, "manifest_sha256": manifest_hash, "archive_path": existing["archive_path"], "already_registered": True, "revision_count": 0}

        archive.parent.mkdir(parents=True, exist_ok=True)
        if archive.exists():
            # Recover an archive copy left by an interruption between file copy
            # and SQLite commit. It is reused only after full manifest/hash validation.
            recovered = load_market_snapshot(archive, verify_hashes=True)
            if file_sha256(archive / "manifest.json") != manifest_hash:
                raise ValueError(f"Orphan snapshot archive does not match its requested manifest: {archive}")
        else:
            archive.parent.mkdir(parents=True, exist_ok=True)
            staging_archive = archive.with_name(f".{archive.name}.{uuid.uuid4().hex}.partial")
            staging_archive.mkdir()
            try:
                shutil.copy2(manifest_path, staging_archive / "manifest.json")
                for info in manifest["series"].values():
                    name = Path(info["file"])
                    if name.name != str(name) or name.name in ("", ".", ".."):
                        raise ValueError("Unsafe snapshot file path in manifest.")
                    shutil.copy2(source_dir / name, staging_archive / name)
                # Check the archived copy before it becomes discoverable in SQLite.
                load_market_snapshot(staging_archive, verify_hashes=True)
                if file_sha256(staging_archive / "manifest.json") != manifest_hash:
                    raise ValueError("Snapshot changed while being archived.")
                if archive.exists():
                    raise FileExistsError(f"Snapshot archive appeared during copy: {archive}")
                os.rename(staging_archive, archive)
            finally:
                if staging_archive.exists():
                    shutil.rmtree(staging_archive, ignore_errors=True)

        retrieved = manifest["retrieved_at_utc"]
        earlier = db.execute(
            "SELECT snapshot_id, retrieved_at_utc FROM snapshots WHERE retrieved_at_utc <= ? ORDER BY retrieved_at_utc DESC, snapshot_id DESC LIMIT 1",
            (retrieved,),
        ).fetchone()
        later = None if earlier else db.execute(
            "SELECT snapshot_id, retrieved_at_utc FROM snapshots WHERE retrieved_at_utc > ? ORDER BY retrieved_at_utc, snapshot_id LIMIT 1",
            (retrieved,),
        ).fetchone()
        comparison = earlier or later
        compare_current_as_later = earlier is not None
        now = _utc_now()
        quality_notes = {
            "manifest_quality_validation_error": manifest.get("quality_validation_error"),
            "data_quality_report": loaded["quality_report"],
            "adjustment_note": manifest.get("adjustments", {}).get("adjusted_ohlc"),
        }
        db.execute(
            "INSERT INTO snapshots VALUES (?, ?, ?, ?, ?, ?, ?)",
            (snapshot_id, manifest_hash, manifest["source"], manifest["retrieved_at_utc"], now, str(archive), canonical_json(quality_notes)),
        )
        db.executemany(
            "INSERT INTO snapshot_bars(snapshot_id,ticker,session_date,bar_sha256) VALUES (?,?,?,?)",
            [(snapshot_id, ticker, session, digest) for ticker, session, digest in bars],
        )
        revisions = []
        if comparison:
            old_bars = {
                (row["ticker"], row["session_date"]): row["bar_sha256"]
                for row in db.execute("SELECT ticker,session_date,bar_sha256 FROM snapshot_bars WHERE snapshot_id = ?", (comparison["snapshot_id"],))
            }
            for ticker, session, digest in bars:
                prior = old_bars.get((ticker, session))
                if prior is not None and prior != digest:
                    earlier_id, later_id = (comparison["snapshot_id"], snapshot_id) if compare_current_as_later else (snapshot_id, comparison["snapshot_id"])
                    earlier_hash, later_hash = (prior, digest) if compare_current_as_later else (digest, prior)
                    revision_id = stable_sha256([earlier_id, later_id, ticker, session, earlier_hash, later_hash])
                    revisions.append((revision_id, earlier_id, later_id, ticker, session, earlier_hash, later_hash, now))
            db.executemany(
                "INSERT INTO snapshot_revisions VALUES (?,?,?,?,?,?,?,?)", revisions,
            )
        return {
            "snapshot_id": snapshot_id, "manifest_sha256": manifest_hash, "archive_path": str(archive),
            "already_registered": False, "revision_count": len(revisions),
            "quality_warning": manifest.get("quality_validation_error"),
        }


def record_phase5c_reference(phase5c_path: str | Path, registry_path: str | Path) -> dict:
    """Pin, by hash, the already-evaluated Phase 5C artifact without changing it."""
    path = Path(phase5c_path)
    raw = path.read_bytes()
    result = json.loads(raw)
    experiment_configs = {
        f"{item['target_name']}_{item['horizon_trading_sessions']}": item.get("selected_hyperparameters", {})
        for item in result.get("experiments", [])
    }
    metadata = {
        "artifact_path_at_registration": str(path.resolve()),
        "experiment_id": result.get("experiment_id"),
        "holdout_periods": sorted({tuple(item.get("holdout_period", [])) for item in result.get("experiments", [])}),
        "selected_model_configurations": experiment_configs,
        "policy": "Results are historical and immutable; this registry does not tune from or overwrite them.",
    }
    # tuples are not JSON serializable; store dates as lists for deterministic metadata.
    metadata["holdout_periods"] = [list(item) for item in metadata["holdout_periods"]]
    artifact_hash = hashlib.sha256(raw).hexdigest()
    snapshot_hash = result["data_snapshot_manifest_sha256"]
    initialize_registry(registry_path)
    with _connect(registry_path) as db:
        existing = db.execute("SELECT * FROM research_references WHERE reference_id = 'phase5c_final_holdout'").fetchone()
        values = (artifact_hash, snapshot_hash, canonical_json(metadata))
        if existing:
            if (existing["artifact_sha256"], existing["snapshot_manifest_sha256"], existing["metadata_json"]) != values:
                raise ValueError("Phase 5C pinned reference differs from its previously recorded content.")
            return {"reference_id": existing["reference_id"], "artifact_sha256": artifact_hash, "snapshot_manifest_sha256": snapshot_hash, "already_registered": True}
        db.execute(
            "INSERT INTO research_references VALUES (?,?,?,?,?)",
            ("phase5c_final_holdout", artifact_hash, snapshot_hash, values[2], _utc_now()),
        )
    return {"reference_id": "phase5c_final_holdout", "artifact_sha256": artifact_hash, "snapshot_manifest_sha256": snapshot_hash, "already_registered": False}


def latest_common_anchor(series: dict[str, list[dict]], *, as_of_session: date | None = None) -> date:
    required = {BENCHMARK_TICKER, *STOCK_TICKERS}
    for ticker in STOCK_TICKERS:
        required.add(SECTOR_PROXY_BY_TICKER[ticker])
    absent = sorted(required - set(series))
    if absent:
        raise ValueError(f"Snapshot lacks the configured stock/benchmark/sector series: {', '.join(absent)}")
    common = set.intersection(*({point["date"] for point in series[ticker]} for ticker in sorted(required)))
    if as_of_session is not None:
        common = {day for day in common if date.fromisoformat(day) <= as_of_session}
    if not common:
        raise ValueError("Snapshot has no common session across the configured research universe.")
    return date.fromisoformat(max(common))


def create_forward_predictions(
    snapshot_dir: str | Path,
    registry_path: str | Path,
    store_root: str | Path,
    phase5c_path: str | Path,
    *,
    created_at_utc: str | None = None,
    as_of_session: date | None = None,
) -> dict:
    """Generate the three fixed research forecasts from one latest common close."""
    reference = record_phase5c_reference(phase5c_path, registry_path)
    archived = register_snapshot(snapshot_dir, registry_path, store_root)
    loaded = load_market_snapshot(archived["archive_path"], verify_hashes=True)
    manifest, series = loaded["manifest"], loaded["series"]
    anchor = latest_common_anchor(series, as_of_session=as_of_session)
    if as_of_session is not None:
        series = {ticker: [point for point in points if date.fromisoformat(point["date"]) <= as_of_session] for ticker, points in series.items()}
        # Training data must be rebuilt/cached from bars no later than the same
        # completed-session cutoff. A matching Phase 5B artifact is safe only if
        # it ends at or before this cutoff; later feature rows are excluded below.
    anchor_text = anchor.isoformat()
    created = created_at_utc or _utc_now()
    parsed_created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    if parsed_created.tzinfo is None:
        raise ValueError("Forecast creation timestamp must include a timezone.")
    if parsed_created.astimezone(timezone.utc) < datetime.fromisoformat(manifest["retrieved_at_utc"].replace("Z", "+00:00")):
        raise ValueError("Forecast creation time precedes source snapshot retrieval time.")

    manifest_hash = archived["manifest_sha256"]
    source = manifest["source"]
    datasets = {}
    live_features = {}
    for ticker in STOCK_TICKERS:
        stock = series[ticker]
        benchmark = series[BENCHMARK_TICKER]
        sector_proxy = SECTOR_PROXY_BY_TICKER[ticker]
        prebuilt = Path(snapshot_dir) / "research_output" / f"real_point_in_time_dataset_{ticker}.json"
        cache_dir = Path(store_root) / "feature_datasets" / archived["snapshot_id"]
        cache_path = cache_dir / f"real_point_in_time_dataset_{ticker}.json"
        if prebuilt.is_file():
            candidate = json.loads(prebuilt.read_text(encoding="utf-8"))
            if (
                candidate.get("dataset_kind") != "real_provider_data"
                or candidate.get("snapshot_manifest_sha256") != manifest_hash
                or candidate.get("ticker") != ticker
            ):
                raise ValueError(f"Prebuilt feature dataset provenance mismatch for {ticker}: {prebuilt}")
            datasets[ticker] = candidate
        elif cache_path.is_file():
            candidate = json.loads(cache_path.read_text(encoding="utf-8"))
            if candidate.get("dataset_kind") != "real_provider_data" or candidate.get("snapshot_manifest_sha256") != manifest_hash or candidate.get("ticker") != ticker:
                raise ValueError(f"Cached feature dataset provenance mismatch for {ticker}: {cache_path}")
            datasets[ticker] = candidate
        else:
            datasets[ticker] = build_point_in_time_dataset(
                ticker, stock, benchmark, series[sector_proxy],
                sector=GICS_SECTOR_BY_TICKER[ticker],
                data_source=f"{source}; snapshot manifest sha256={manifest_hash}",
                benchmark_ticker=BENCHMARK_TICKER,
                benchmark_source="Yahoo Finance via yfinance; SPY adjusted OHLCV proxy",
            )
            datasets[ticker]["dataset_kind"] = "real_provider_data"
            datasets[ticker]["snapshot_manifest_sha256"] = manifest_hash
            datasets[ticker]["source_retrieved_at_utc"] = manifest["retrieved_at_utc"]
            _save_feature_cache_atomically(datasets[ticker], cache_path)
        stock_anchor = next(point for point in stock if point["date"] == anchor_text)
        historical_stock = [point for point in stock if point["date"] <= anchor_text]
        historical_benchmark = [point for point in benchmark if point["date"] <= anchor_text]
        historical_sector = [point for point in series[sector_proxy] if point["date"] <= anchor_text]
        context = calculate_market_context(
            ticker, historical_stock, historical_benchmark, as_of=anchor,
            sector=GICS_SECTOR_BY_TICKER[ticker], sector_points=historical_sector,
            benchmark_ticker=BENCHMARK_TICKER,
            benchmark_source="Yahoo Finance via yfinance; SPY adjusted OHLCV proxy",
        )
        live_features[ticker] = {"ticker": ticker, "features": _make_features(context, float(stock_anchor["close"]))}

    outcomes = []
    for horizon in (5, 20):
        for target_name in ("stock_return", "excess_return"):
            train_rows = select_rows(
                datasets, horizon=horizon, target_name=target_name,
                training_before=anchor,
            )
            if len(train_rows) < 1000:
                raise ValueError(f"Only {len(train_rows)} mature pooled training rows for {target_name}/{horizon}; refusing unstable forecast creation.")
            y_train = np.asarray([_target(row, horizon, target_name) for row in train_rows], dtype=float)
            if not np.isfinite(y_train).all():
                raise ValueError("Mature training targets contain a non-finite value.")
            cutoff = f"{anchor_text} after session close; provider snapshot retrieved {manifest['retrieved_at_utc']}"
            training_start = min(row["forecast_anchor_date"] for row in train_rows)
            training_end = max(row["forecast_anchor_date"] for row in train_rows)
            label_cutoff = max(row["targets"][str(horizon)]["target_end_date"] for row in train_rows)
            for ticker in STOCK_TICKERS:
                row = live_features[ticker]
                ticker_rows = [r for r in train_rows if r["ticker"] == ticker]
                historical_mean = float(np.mean([_target(r, horizon, target_name) for r in ticker_rows])) if ticker_rows else 0.0
                ridge, _processor = _fit_predict(
                    FIXED_MODEL_ID, FIXED_MODEL_PARAMETERS, train_rows, [row], y_train, task="regression",
                )
                predictions = {
                    "zero_return": 0.0,
                    "historical_mean": historical_mean,
                    FIXED_MODEL_ID: float(ridge[0]),
                }
                for model_id, predicted_return in predictions.items():
                    definition = MODEL_DEFINITIONS[model_id]
                    params = definition["parameters"]
                    key_material = [ticker, target_name, anchor_text, model_id, definition["version"], FEATURE_SCHEMA_VERSION, horizon]
                    unique_key = stable_sha256(key_material)
                    forecast_id = unique_key
                    features_json = canonical_json(row["features"])
                    record = {
                        "forecast_id": forecast_id,
                        "unique_key": unique_key,
                        "ticker": ticker,
                        "target_name": target_name,
                        "forecast_created_at_utc": created,
                        "forecast_anchor_session": anchor_text,
                        "information_cutoff": cutoff,
                        "model_identifier": model_id,
                        "model_version": definition["version"],
                        "model_parameters_json": canonical_json(params),
                        "model_parameters_sha256": stable_sha256(params),
                        "feature_schema_version": FEATURE_SCHEMA_VERSION,
                        "feature_values_json": features_json,
                        "feature_values_sha256": hashlib.sha256(features_json.encode()).hexdigest(),
                        "dataset_snapshot_identifier": archived["snapshot_id"],
                        "dataset_manifest_sha256": manifest_hash,
                        "source": source,
                        "source_retrieved_at_utc": manifest["retrieved_at_utc"],
                        "prediction_horizon": horizon,
                        "predicted_return": float(predicted_return),
                        "predicted_direction": int(float(predicted_return) > 0),
                        "prediction_status": "pending",
                        # The exact future session cannot be known from a daily-price
                        # provider snapshot. It is recorded on the later outcome row.
                        "evaluation_eligibility_date": None,
                        "training_row_count": len(train_rows),
                        "training_anchor_start": training_start,
                        "training_anchor_end": training_end,
                        "training_label_cutoff": label_cutoff,
                        "training_snapshot_identifier": archived["snapshot_id"],
                        "created_at_utc": created,
                    }
                    inserted = insert_forecast(registry_path, record)
                    outcomes.append({"forecast_id": forecast_id, "ticker": ticker, "target_name": target_name, "horizon": horizon, "model": model_id, "predicted_return": float(predicted_return), "inserted": inserted})
    return {
        "snapshot_id": archived["snapshot_id"], "manifest_sha256": manifest_hash,
        "phase5c_reference": reference, "forecast_anchor_session": anchor_text,
        "forecast_created_at_utc": created, "forecast_count": len(outcomes),
        "inserted_count": sum(row["inserted"] for row in outcomes),
        "duplicate_count": sum(not row["inserted"] for row in outcomes),
        "training_cutoff_policy": "Only labels with target_end_date strictly before the forecast anchor were used.",
        "predictions": outcomes,
        "quality_warning": manifest.get("quality_validation_error"),
    }


def insert_forecast(registry_path: str | Path, record: dict) -> bool:
    """Insert a forecast once. The semantic key excludes the source snapshot."""
    initialize_registry(registry_path)
    columns = tuple(record)
    with _connect(registry_path) as db:
        cursor = db.execute(
            f"INSERT OR IGNORE INTO forecasts ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            tuple(record[column] for column in columns),
        )
        return cursor.rowcount == 1


def assess_outcome(forecast: dict, series: dict[str, list[dict]]) -> dict:
    """Assess maturity against observed SPY sessions; never fill missing bars."""
    ticker = forecast["ticker"]
    anchor = forecast["forecast_anchor_session"]
    horizon = int(forecast["prediction_horizon"])
    stock_map = {point["date"]: point for point in series.get(ticker, [])}
    benchmark_map = {point["date"]: point for point in series.get(BENCHMARK_TICKER, [])}
    if anchor not in stock_map or anchor not in benchmark_map:
        return {"status": "incomplete_missing_stock_sessions", "reason": "forecast anchor absent from stock or benchmark series", "mature": False}
    benchmark_sessions = sorted(day for day in benchmark_map if day > anchor)
    if len(benchmark_sessions) < horizon:
        return {"status": "not_mature", "reason": "not enough later benchmark sessions", "mature": False, "observed_sessions": len(benchmark_sessions)}
    expected = benchmark_sessions[:horizon]
    missing = [day for day in expected if day not in stock_map]
    if missing:
        return {"status": "incomplete_missing_stock_sessions", "reason": "stock bars missing on observed benchmark sessions", "mature": True, "missing_sessions": missing, "expected_sessions": expected}
    entry_day, exit_day = expected[0], expected[-1]
    entry_open = stock_map[entry_day].get("open")
    exit_close = stock_map[exit_day].get("close")
    benchmark_open = benchmark_map[entry_day].get("open")
    benchmark_close = benchmark_map[exit_day].get("close")
    if any(value is None or not math.isfinite(float(value)) or float(value) <= 0 for value in (entry_open, exit_close, benchmark_open, benchmark_close)):
        return {"status": "incomplete_missing_stock_sessions", "reason": "required entry or exit price unavailable", "mature": True, "expected_sessions": expected}
    stock_return = float(exit_close) / float(entry_open) - 1.0
    benchmark_return = float(benchmark_close) / float(benchmark_open) - 1.0
    excess_return = stock_return - benchmark_return
    target_return = stock_return if forecast["target_name"] == "stock_return" else excess_return
    return {
        "status": "complete", "mature": True, "target_start_session": entry_day,
        "target_end_session": exit_day, "evaluation_eligibility_date": exit_day,
        "realized_stock_return": stock_return,
        "realized_benchmark_return": benchmark_return,
        "realized_excess_return": excess_return,
        "realized_target_return": target_return,
        "realized_direction": int(target_return > 0), "expected_sessions": expected,
    }


def _row_hash_index(registry_path: str | Path, snapshot_id: str, ticker: str, sessions: list[str]) -> dict:
    if not sessions:
        return {}
    placeholders = ",".join("?" for _ in sessions)
    with _connect(registry_path) as db:
        rows = db.execute(
            f"SELECT session_date,bar_sha256 FROM snapshot_bars WHERE snapshot_id=? AND ticker=? AND session_date IN ({placeholders})",
            (snapshot_id, ticker, *sessions),
        ).fetchall()
    return {row["session_date"]: row["bar_sha256"] for row in rows}


def evaluate_forward_outcomes(
    snapshot_dir: str | Path,
    registry_path: str | Path,
    store_root: str | Path,
    *,
    as_of_session: date | None = None,
) -> dict:
    """Append assessments for mature forecasts using a later immutable snapshot."""
    archived = register_snapshot(snapshot_dir, registry_path, store_root)
    loaded = load_market_snapshot(archived["archive_path"], verify_hashes=True)
    manifest, series = loaded["manifest"], loaded["series"]
    if as_of_session is not None:
        series = {ticker: [point for point in points if date.fromisoformat(point["date"]) <= as_of_session] for ticker, points in series.items()}
    with _connect(registry_path) as db:
        forecasts = [dict(row) for row in db.execute("SELECT * FROM forecasts ORDER BY forecast_anchor_session,ticker,forecast_id")]
    inserted = 0
    not_mature = 0
    incomplete = 0
    complete = 0
    skipped_not_later = 0
    for forecast in forecasts:
        if forecast["dataset_snapshot_identifier"] == archived["snapshot_id"]:
            skipped_not_later += 1
            continue
        try:
            source_retrieved = datetime.fromisoformat(forecast["source_retrieved_at_utc"].replace("Z", "+00:00"))
            current_retrieved = datetime.fromisoformat(manifest["retrieved_at_utc"].replace("Z", "+00:00"))
        except ValueError:
            skipped_not_later += 1
            continue
        if current_retrieved <= source_retrieved:
            skipped_not_later += 1
            continue
        assessment = assess_outcome(forecast, series)
        if not assessment.get("mature"):
            not_mature += 1
            continue
        status = assessment["status"]
        if status == "complete": complete += 1
        else: incomplete += 1
        sessions = assessment.get("expected_sessions", [])
        relevant = {forecast["ticker"], BENCHMARK_TICKER}
        observed = {}
        revisions = []
        for symbol in relevant:
            hashes = _row_hash_index(registry_path, archived["snapshot_id"], symbol, sessions)
            observed[symbol] = hashes
            original = _row_hash_index(registry_path, forecast["dataset_snapshot_identifier"], symbol, sessions)
            for session in sessions:
                before, after = original.get(session), hashes.get(session)
                if before is not None and after is not None and before != after:
                    revisions.append({"ticker": symbol, "session_date": session, "forecast_snapshot_bar_sha256": before, "evaluation_snapshot_bar_sha256": after})
        outcome_id = stable_sha256([forecast["forecast_id"], archived["snapshot_id"]])
        row = {
            "outcome_id": outcome_id,
            "forecast_id": forecast["forecast_id"],
            "evaluation_snapshot_identifier": archived["snapshot_id"],
            "evaluation_manifest_sha256": archived["manifest_sha256"],
            "evaluated_at_utc": _utc_now(),
            "outcome_status": status,
            "target_start_session": assessment.get("target_start_session"),
            "target_end_session": assessment.get("target_end_session"),
            "realized_stock_return": assessment.get("realized_stock_return"),
            "realized_benchmark_return": assessment.get("realized_benchmark_return"),
            "realized_excess_return": assessment.get("realized_excess_return"),
            "realized_target_return": assessment.get("realized_target_return"),
            "realized_direction": assessment.get("realized_direction"),
            "evaluation_eligibility_date": assessment.get("evaluation_eligibility_date"),
            "data_revision_notes_json": canonical_json({"revisions_since_forecast_snapshot": revisions, "source_retrieved_at_utc": manifest["retrieved_at_utc"], "reason": assessment.get("reason"), "missing_sessions": assessment.get("missing_sessions", [])}),
            "observed_bar_hashes_json": canonical_json(observed),
        }
        with _connect(registry_path) as db:
            cursor = db.execute(
                f"INSERT OR IGNORE INTO outcomes ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
                tuple(row.values()),
            )
            inserted += cursor.rowcount == 1
    return {
        "evaluation_snapshot_identifier": archived["snapshot_id"],
        "evaluation_manifest_sha256": archived["manifest_sha256"],
        "source_retrieved_at_utc": manifest["retrieved_at_utc"],
        "forecast_records_seen": len(forecasts), "new_outcomes_inserted": inserted,
        "complete_outcomes": complete, "incomplete_mature_outcomes": incomplete,
        "not_yet_mature": not_mature, "skipped_not_later_snapshot": skipped_not_later,
        "note": "Incomplete outcomes are immutable assessments and may be reassessed against a later snapshot; incomplete rows are never filled or silently treated as complete.",
    }


def insert_assessment_for_test(registry_path: str | Path, row: dict) -> bool:
    """Typed helper for deterministic unit tests and local research tooling."""
    initialize_registry(registry_path)
    with _connect(registry_path) as db:
        columns = tuple(row)
        cursor = db.execute(
            f"INSERT OR IGNORE INTO outcomes ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            tuple(row[column] for column in columns),
        )
        return cursor.rowcount == 1
