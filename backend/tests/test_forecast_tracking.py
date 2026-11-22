import csv
from datetime import date, timedelta
import hashlib
import json
import sqlite3

import pytest

from app.research.forecast_tracking import (
    assess_outcome,
    initialize_registry,
    insert_assessment_for_test,
    insert_forecast,
    record_phase5c_reference,
    register_snapshot,
    stable_sha256,
)
from app.research.market_data import CSV_COLUMNS, file_sha256


def _snapshot(tmp_path, name, retrieved, *, close_adjustment=0.0):
    folder = tmp_path / name
    folder.mkdir()
    days = [date(2026, 1, 5) + timedelta(days=i) for i in range(0, 20) if (date(2026, 1, 5) + timedelta(days=i)).weekday() < 5]
    manifest = {
        "schema_version": "finsight.market-snapshot.v1",
        "source": "Yahoo Finance via yfinance",
        "retrieved_at_utc": retrieved,
        "requested_start": days[0].isoformat(),
        "requested_end_exclusive": None,
        "series": {},
    }
    for ticker in ("AAPL", "SPY"):
        path = folder / f"{ticker}.csv"
        rows = []
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for index, day in enumerate(days):
                value = 100.0 + index + close_adjustment
                row = {
                    "date": day.isoformat(), "ticker": ticker,
                    "raw_open": value, "raw_high": value + 2, "raw_low": value - 2, "raw_close": value + 1,
                    "raw_adj_close": value + 1, "raw_volume": 1000, "dividends": 0,
                    "stock_splits": 0, "adjustment_factor": 1,
                    "adjusted_open": value, "adjusted_high": value + 2, "adjusted_low": value - 2,
                    "adjusted_close": value + 1, "adjusted_volume": 1000,
                }
                writer.writerow(row)
                rows.append(row)
        manifest["series"][ticker] = {
            "file": path.name, "sha256": file_sha256(path), "row_count": len(rows),
            "coverage_start": rows[0]["date"], "coverage_end": rows[-1]["date"],
        }
    (folder / "manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return folder, days


def _record(snapshot_id):
    return {
        "forecast_id": "forecast-a", "unique_key": "semantic-key-a", "ticker": "AAPL",
        "target_name": "stock_return", "forecast_created_at_utc": "2026-02-01T12:00:00+00:00",
        "forecast_anchor_session": "2026-01-20", "information_cutoff": "2026-01-20 after close",
        "model_identifier": "zero_return", "model_version": "research_baseline_v1",
        "model_parameters_json": "{}", "model_parameters_sha256": stable_sha256({}),
        "feature_schema_version": "finsight.forecast.dataset.v1", "feature_values_json": "{}",
        "feature_values_sha256": hashlib.sha256(b"{}").hexdigest(),
        "dataset_snapshot_identifier": snapshot_id, "dataset_manifest_sha256": "manifest-hash",
        "source": "Yahoo Finance via yfinance", "source_retrieved_at_utc": "2026-01-21T00:00:00+00:00",
        "prediction_horizon": 5, "predicted_return": 0.0, "predicted_direction": 0,
        "prediction_status": "pending", "evaluation_eligibility_date": None,
        "training_row_count": 1000, "training_anchor_start": "2015-01-01",
        "training_anchor_end": "2025-12-01", "training_label_cutoff": "2026-01-19",
        "training_snapshot_identifier": snapshot_id, "created_at_utc": "2026-02-01T12:00:00+00:00",
    }


def test_forecasts_are_immutable_and_duplicate_prevented(tmp_path):
    snapshot, _ = _snapshot(tmp_path, "snap", "2026-01-21T00:00:00+00:00")
    registry, store = tmp_path / "registry.sqlite3", tmp_path / "store"
    registered = register_snapshot(snapshot, registry, store)
    record = _record(registered["snapshot_id"])
    assert insert_forecast(registry, record) is True
    assert insert_forecast(registry, record) is False
    with sqlite3.connect(registry) as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("UPDATE forecasts SET predicted_return=1 WHERE forecast_id='forecast-a'")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("DELETE FROM forecasts WHERE forecast_id='forecast-a'")
        assert db.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0] == 1


def test_outcome_maturity_uses_future_benchmark_sessions_and_next_open(tmp_path):
    anchor = "2026-01-05"
    sessions = ["2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12"]
    series = {
        "AAPL": [{"date": anchor, "open": 10.0, "close": 11.0}] + [
            {"date": day, "open": 20.0 + i, "close": 21.0 + i} for i, day in enumerate(sessions)
        ],
        "SPY": [{"date": anchor, "open": 100.0, "close": 101.0}] + [
            {"date": day, "open": 200.0 + i, "close": 202.0 + i} for i, day in enumerate(sessions)
        ],
    }
    forecast = {"ticker": "AAPL", "forecast_anchor_session": anchor, "prediction_horizon": 5, "target_name": "stock_return"}
    result = assess_outcome(forecast, series)
    assert result["status"] == "complete"
    assert result["target_start_session"] == sessions[0]
    assert result["target_end_session"] == sessions[-1]
    assert result["evaluation_eligibility_date"] == sessions[-1]
    assert result["realized_stock_return"] == pytest.approx(25.0 / 20.0 - 1.0)

    del series["AAPL"][-1]
    incomplete = assess_outcome(forecast, series)
    assert incomplete["status"] == "incomplete_missing_stock_sessions"
    assert incomplete["missing_sessions"] == [sessions[-1]]


def test_outcome_waits_until_horizon_is_mature(tmp_path):
    series = {
        "AAPL": [{"date": "2026-01-05", "open": 10, "close": 10}, {"date": "2026-01-06", "open": 10, "close": 11}],
        "SPY": [{"date": "2026-01-05", "open": 100, "close": 100}, {"date": "2026-01-06", "open": 100, "close": 101}],
    }
    result = assess_outcome({"ticker": "AAPL", "forecast_anchor_session": "2026-01-05", "prediction_horizon": 5, "target_name": "excess_return"}, series)
    assert result["status"] == "not_mature"
    assert result["mature"] is False


def test_outcome_records_are_separate_and_immutable(tmp_path):
    snapshot, _ = _snapshot(tmp_path, "snap", "2026-01-21T00:00:00+00:00")
    registry, store = tmp_path / "registry.sqlite3", tmp_path / "store"
    registered = register_snapshot(snapshot, registry, store)
    insert_forecast(registry, _record(registered["snapshot_id"]))
    outcome = {
        "outcome_id": "outcome-a", "forecast_id": "forecast-a",
        "evaluation_snapshot_identifier": registered["snapshot_id"], "evaluation_manifest_sha256": "hash",
        "evaluated_at_utc": "2026-02-01T00:00:00+00:00", "outcome_status": "complete",
        "target_start_session": "2026-01-21", "target_end_session": "2026-01-28",
        "realized_stock_return": 0.02, "realized_benchmark_return": 0.01,
        "realized_excess_return": 0.01, "realized_target_return": 0.02,
        "realized_direction": 1, "evaluation_eligibility_date": "2026-01-28",
        "data_revision_notes_json": "{}", "observed_bar_hashes_json": "{}",
    }
    assert insert_assessment_for_test(registry, outcome)
    assert insert_assessment_for_test(registry, outcome) is False
    with sqlite3.connect(registry) as db:
        forecast = db.execute("SELECT prediction_status,predicted_return FROM forecasts WHERE forecast_id='forecast-a'").fetchone()
        assert forecast == ("pending", 0.0)
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("UPDATE outcomes SET realized_target_return=0 WHERE outcome_id='outcome-a'")


def test_snapshot_revision_is_detected_and_archived_snapshot_is_hash_verified(tmp_path):
    first, _ = _snapshot(tmp_path, "first", "2026-01-21T00:00:00+00:00")
    later, _ = _snapshot(tmp_path, "later", "2026-02-01T00:00:00+00:00", close_adjustment=0.5)
    registry, store = tmp_path / "registry.sqlite3", tmp_path / "store"
    register_snapshot(first, registry, store)
    changed = register_snapshot(later, registry, store)
    assert changed["revision_count"] > 0
    with sqlite3.connect(registry) as db:
        assert db.execute("SELECT COUNT(*) FROM snapshot_revisions").fetchone()[0] > 0
    archived = store / "snapshots" / changed["snapshot_id"] / "AAPL.csv"
    archived.write_text(archived.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        from app.research.market_data import load_market_snapshot
        load_market_snapshot(archived.parent, verify_hashes=True)


def test_phase5c_reference_hash_and_configuration_are_reproducible(tmp_path):
    artifact = tmp_path / "phase5c.json"
    artifact.write_text(json.dumps({
        "experiment_id": "fixed", "data_snapshot_manifest_sha256": "snapshot-hash",
        "experiments": [{"target_name": "stock_return", "horizon_trading_sessions": 5,
                         "holdout_period": ["2024-10-24", "2026-10-23"],
                         "selected_hyperparameters": {"ridge_regression": {"alpha": 10.0}}}],
    }), encoding="utf-8")
    registry = tmp_path / "registry.sqlite3"
    first = record_phase5c_reference(artifact, registry)
    second = record_phase5c_reference(artifact, registry)
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["snapshot_manifest_sha256"] == "snapshot-hash"
    assert second["already_registered"] is True
    with sqlite3.connect(registry) as db:
        assert db.execute("SELECT COUNT(*) FROM research_references").fetchone()[0] == 1
