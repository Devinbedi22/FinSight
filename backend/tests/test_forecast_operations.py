import csv
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import shutil

import pytest

from app.research.forecast_operations import (
    DownloadWorkflowError,
    SnapshotValidationError,
    audit_registry,
    backup_registry,
    completed_session_cutoff,
    inspect_snapshot,
    registry_status,
    update_registry,
)
from app.research.market_data import CSV_COLUMNS, REQUIRED_TICKERS, file_sha256
from app.research.forecast_tracking import initialize_registry


def _full_snapshot(tmp_path, name="snapshot", *, retrieved="2026-01-23T22:00:00+00:00", omit_aapl=None, omit_spy=None, download_failures=None):
    root = tmp_path / name
    root.mkdir()
    dates = [date(2026, 1, 12) + timedelta(days=i) for i in range(12) if (date(2026, 1, 12) + timedelta(days=i)).weekday() < 5]
    manifest = {
        "schema_version": "finsight.market-snapshot.v1", "source": "Yahoo Finance via yfinance",
        "retrieved_at_utc": retrieved, "requested_start": dates[0].isoformat(),
        "requested_end_exclusive": None, "series": {}, "download_failures": download_failures or {},
    }
    for ticker in REQUIRED_TICKERS:
        skipped = omit_aapl if ticker == "AAPL" else omit_spy if ticker == "SPY" else None
        rows = []
        path = root / f"{ticker}.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for index, day in enumerate(d for d in dates if d.isoformat() != skipped):
                price = 100.0 + index
                row = {
                    "date": day.isoformat(), "ticker": ticker,
                    "raw_open": price, "raw_high": price + 2, "raw_low": price - 2, "raw_close": price + 1,
                    "raw_adj_close": price + 1, "raw_volume": 1000, "dividends": 0, "stock_splits": 0,
                    "adjustment_factor": 1, "adjusted_open": price, "adjusted_high": price + 2,
                    "adjusted_low": price - 2, "adjusted_close": price + 1, "adjusted_volume": 1000,
                }
                writer.writerow(row)
                rows.append(row)
        manifest["series"][ticker] = {
            "file": path.name, "sha256": file_sha256(path), "row_count": len(rows),
            "coverage_start": rows[0]["date"], "coverage_end": rows[-1]["date"],
        }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return root


def _weekend_now():
    return datetime(2026, 1, 24, 18, 0, tzinfo=timezone.utc)  # Saturday in New York


def _mock_downloader(snapshot):
    def download(start, end, output_root, *, refresh=False):
        assert start == "2010-01-01" and end is None and refresh is True
        return snapshot
    return download


def test_cutoff_never_accepts_today_before_close_buffer():
    before_close = datetime(2026, 1, 23, 20, 0, tzinfo=timezone.utc)  # 15:00 ET
    cutoff, eligible = completed_session_cutoff(before_close)
    assert cutoff == date(2026, 1, 22)
    assert eligible is False

    after_close = datetime(2026, 1, 23, 22, 0, tzinfo=timezone.utc)  # 17:00 ET
    cutoff, eligible = completed_session_cutoff(after_close)
    assert cutoff == date(2026, 1, 23)
    assert eligible is True


def test_snapshot_session_gaps_are_reported_without_inventing_market_closures(tmp_path):
    dates = [date(2026, 1, 12) + timedelta(days=i) for i in range(12) if (date(2026, 1, 12) + timedelta(days=i)).weekday() < 5]
    snapshot = _full_snapshot(tmp_path, omit_aapl=dates[2].isoformat())
    result = inspect_snapshot(snapshot, now=_weekend_now())
    assert result["valid"] is True
    assert len(result["stock_benchmark_alignment"]["AAPL"]["missing_stock_on_benchmark_sessions"]) == 1
    assert any("AAPL is missing" in warning for warning in result["warnings"])
    assert result["independent_exchange_calendar_available"] is False
    assert all(
        gap["status"] == "unconfirmed_gap_not_assumed_market_closure"
        for series in result["coverage"].values()
        for gap in series["suspicious_calendar_gaps"]
    )


def test_missing_benchmark_session_rejects_snapshot(tmp_path):
    dates = [date(2026, 1, 12) + timedelta(days=i) for i in range(12) if (date(2026, 1, 12) + timedelta(days=i)).weekday() < 5]
    snapshot = _full_snapshot(tmp_path, omit_spy=dates[2].isoformat())
    result = inspect_snapshot(snapshot, now=_weekend_now())
    assert result["valid"] is False
    assert any("benchmark bars missing" in error for error in result["fatal_errors"])


def test_update_is_idempotent_and_does_not_create_weekend_forecast(tmp_path):
    snapshot = _full_snapshot(tmp_path)
    registry, store = tmp_path / "registry.sqlite3", tmp_path / "store"
    evaluation_calls = []
    def evaluator(path, db_path, store_root, *, as_of_session):
        evaluation_calls.append((Path(path), as_of_session))
        return {"new_outcomes_inserted": 0}
    def forecaster(*args, **kwargs):
        raise AssertionError("weekend update must not backdate a forecast")

    one = update_registry(registry, store, tmp_path / "phase5c.json", now=_weekend_now(), downloader=_mock_downloader(snapshot), evaluator=evaluator, forecaster=forecaster)
    two = update_registry(registry, store, tmp_path / "phase5c.json", now=_weekend_now(), downloader=_mock_downloader(snapshot), evaluator=evaluator, forecaster=forecaster)
    assert one["snapshot_registered"]["already_registered"] is False
    assert two["snapshot_registered"]["already_registered"] is True
    assert len(evaluation_calls) == 2
    assert one["forecast_skipped_reason"] is not None
    with sqlite3.connect(registry) as db:
        assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM snapshot_revisions").fetchone()[0] == 0
    assert len(list((store / "backups").glob("forecast_registry_backup_*.sqlite3"))) == 2


def test_update_calls_forecaster_only_for_a_new_completed_current_session(tmp_path):
    snapshot = _full_snapshot(tmp_path)
    registry, store = tmp_path / "registry.sqlite3", tmp_path / "store"
    after_close = datetime(2026, 1, 23, 22, 0, tzinfo=timezone.utc)
    forecast_calls = []
    def forecaster(path, db_path, store_root, phase5c_path, **kwargs):
        forecast_calls.append((Path(path), kwargs))
        with sqlite3.connect(db_path) as db:
            assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
        assert len(list((Path(store_root) / "backups").glob("forecast_registry_backup_*.sqlite3"))) == 1
        return {"forecast_count": 60, "inserted_count": 60}
    result = update_registry(
        registry, store, tmp_path / "phase5c.json", now=after_close,
        downloader=_mock_downloader(snapshot),
        evaluator=lambda *a, **k: {"new_outcomes_inserted": 0},
        forecaster=forecaster,
    )
    assert len(forecast_calls) == 1
    assert forecast_calls[0][1]["as_of_session"] == date(2026, 1, 23)
    assert result["new_forecasts"]["inserted_count"] == 60
    assert result["forecast_skipped_reason"] is None


def test_interrupted_update_recovers_on_rerun_without_duplicate_snapshot(tmp_path):
    snapshot = _full_snapshot(tmp_path)
    registry, store = tmp_path / "registry.sqlite3", tmp_path / "store"
    def interrupted(*args, **kwargs):
        raise RuntimeError("simulated stop after snapshot registration")
    with pytest.raises(RuntimeError, match="simulated stop"):
        update_registry(registry, store, tmp_path / "phase5c.json", now=_weekend_now(), downloader=_mock_downloader(snapshot), evaluator=interrupted)
    with sqlite3.connect(registry) as db:
        assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
    result = update_registry(registry, store, tmp_path / "phase5c.json", now=_weekend_now(), downloader=_mock_downloader(snapshot), evaluator=lambda *a, **k: {"new_outcomes_inserted": 0}, forecaster=lambda *a, **k: None)
    assert result["snapshot_registered"]["already_registered"] is True
    with sqlite3.connect(registry) as db:
        assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1


def test_update_recovers_verified_orphan_archive_from_interrupted_commit(tmp_path):
    snapshot = _full_snapshot(tmp_path)
    registry, store = tmp_path / "registry.sqlite3", tmp_path / "store"
    manifest_hash = file_sha256(snapshot / "manifest.json")
    orphan = store / "snapshots" / f"yahoo-{manifest_hash[:20]}"
    orphan.mkdir(parents=True)
    shutil.copy2(snapshot / "manifest.json", orphan / "manifest.json")
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["series"].values():
        shutil.copy2(snapshot / item["file"], orphan / item["file"])
    result = update_registry(
        registry, store, tmp_path / "phase5c.json", now=_weekend_now(),
        downloader=_mock_downloader(snapshot),
        evaluator=lambda *a, **k: {"new_outcomes_inserted": 0},
        forecaster=lambda *a, **k: None,
    )
    assert len(result["recovered_orphan_snapshots"]) == 1
    assert result["snapshot_registered"]["already_registered"] is True
    with sqlite3.connect(registry) as db:
        assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1


def test_stale_snapshot_is_rejected_and_current_day_is_excluded_before_buffer(tmp_path):
    snapshot = _full_snapshot(tmp_path)
    stale_now = datetime(2026, 2, 10, 22, 0, tzinfo=timezone.utc)
    stale = inspect_snapshot(snapshot, now=stale_now)
    assert stale["valid"] is False
    assert any("is stale" in error for error in stale["fatal_errors"])

    snapshot_with_today = _full_snapshot(tmp_path, "today")
    before_close = datetime(2026, 1, 23, 20, 0, tzinfo=timezone.utc)
    result = inspect_snapshot(snapshot_with_today, now=before_close)
    assert result["valid"] is True
    assert result["latest_common_session"] == "2026-01-22"
    assert len(result["current_date_rows_excluded"]) == len(REQUIRED_TICKERS)


def test_failed_download_or_invalid_snapshot_leaves_registry_unchanged(tmp_path):
    snapshot = _full_snapshot(tmp_path)
    registry, store = tmp_path / "registry.sqlite3", tmp_path / "store"
    initialize_registry(registry)
    before = registry_status(registry)
    def fail(*args, **kwargs):
        raise OSError("network blocked")
    with pytest.raises(DownloadWorkflowError):
        update_registry(registry, store, tmp_path / "phase5c.json", now=_weekend_now(), downloader=fail)
    invalid = _full_snapshot(tmp_path, "invalid", download_failures={"NVDA": {"error_type": "Timeout", "message": "unavailable"}})
    with pytest.raises(SnapshotValidationError, match="registry remains unchanged"):
        update_registry(registry, store, tmp_path / "phase5c.json", now=_weekend_now(), downloader=_mock_downloader(invalid))
    after = registry_status(registry)
    assert after["total_forecasts"] == before["total_forecasts"]
    assert after["latest_successful_snapshot"] == before["latest_successful_snapshot"]
    assert not (store / "backups").exists()


def test_backup_is_sqlite_consistent_and_never_overwrites(tmp_path):
    registry = tmp_path / "registry.sqlite3"
    initialize_registry(registry)
    with sqlite3.connect(registry) as db:
        db.execute("INSERT INTO registry_metadata(key,value_json,created_at_utc) VALUES('test','{}','now')")
    first = backup_registry(registry, tmp_path / "backups")
    second = backup_registry(registry, tmp_path / "backups")
    assert first["path"] != second["path"]
    assert first["integrity_check"] == "ok"
    assert first["sha256"] == file_sha256(Path(first["path"]))
    with sqlite3.connect(first["path"]) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT value_json FROM registry_metadata WHERE key='test'").fetchone()[0] == "{}"


def test_status_shows_empty_performance_until_outcomes_mature(tmp_path):
    registry = tmp_path / "registry.sqlite3"
    initialize_registry(registry)
    status = registry_status(registry)
    assert status["total_forecasts"] == 0
    assert status["pending_forecasts"] == 0
    assert status["matured_forecasts"] == 0
    assert status["performance"] == []
    assert "small" in status["performance_note"]


def test_audit_detects_phase5c_reference_and_snapshot_integrity(tmp_path):
    # Empty valid registries still report the absent historical reference clearly.
    registry = tmp_path / "registry.sqlite3"
    initialize_registry(registry)
    phase5c = tmp_path / "phase5c.json"
    phase5c.write_text("{}", encoding="utf-8")
    result = audit_registry(registry, phase5c)
    assert result["checks"]["append_only_triggers_present"]
    assert result["checks"]["training_labels_strictly_before_anchor"]
    assert result["checks"]["forecast_unique_keys"]
    assert result["phase5c_reference"]["registered"] is False
    assert result["valid"] is False
