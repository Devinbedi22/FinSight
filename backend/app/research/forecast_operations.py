"""Operational update, snapshot checks, backups, and status for Phase 5D."""

from __future__ import annotations

from collections import defaultdict
from contextlib import redirect_stdout
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import uuid
from zoneinfo import ZoneInfo

from app.research.forecast_tracking import (
    MODEL_DEFINITIONS,
    _connect,
    _utc_now,
    create_forward_predictions,
    evaluate_forward_outcomes,
    initialize_registry,
    latest_common_anchor,
    register_snapshot,
    stable_sha256,
)
from app.research.market_data import (
    BENCHMARK_TICKER,
    REQUIRED_TICKERS,
    STOCK_TICKERS,
    file_sha256,
    load_market_snapshot,
)


NEW_YORK = ZoneInfo("America/New_York")
US_CLOSE_BUFFER = time(16, 15)
MAX_COMMON_SESSION_LAG_DAYS = 4
MIN_STATUS_OUTCOMES = 30
MIN_STATUS_ANCHORS = 5


class SnapshotValidationError(ValueError):
    """A downloaded snapshot should not be added to the forecast registry."""


class DownloadWorkflowError(RuntimeError):
    """The existing downloader did not produce a complete fresh snapshot."""


def completed_session_cutoff(now: datetime | None = None) -> tuple[date, bool]:
    """Return conservative data cutoff and whether today's session can be used.

    Without an exchange calendar, today's daily bar is not trusted until 16:15
    America/New_York. This deliberately delays early-close days by 75 minutes.
    """
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("Operational clock must include a timezone.")
    eastern = instant.astimezone(NEW_YORK)
    current_is_eligible = eastern.weekday() < 5 and eastern.time().replace(tzinfo=None) >= US_CLOSE_BUFFER
    cutoff = eastern.date() if current_is_eligible else eastern.date() - timedelta(days=1)
    return cutoff, current_is_eligible


def inspect_snapshot(snapshot_dir: str | Path, *, now: datetime | None = None) -> dict:
    """Validate completeness and report session coverage without inventing a calendar."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("Snapshot inspection clock must include a timezone.")
    cutoff, current_session_eligible = completed_session_cutoff(instant)
    root = Path(snapshot_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    fatal = []
    missing_symbols = sorted(set(REQUIRED_TICKERS) - set(manifest.get("series", {})))
    if missing_symbols:
        fatal.append(f"required series missing: {', '.join(missing_symbols)}")
    failures = manifest.get("download_failures") or {}
    if failures:
        fatal.append(f"provider download failures: {', '.join(sorted(failures))}")
    if manifest.get("quality_validation_error"):
        fatal.append(f"snapshot quality validation failed: {manifest['quality_validation_error']}")
    try:
        loaded = load_market_snapshot(root, verify_hashes=True)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fatal.append(f"snapshot verification failed: {type(exc).__name__}: {exc}")
        return {
            "valid": False, "fatal_errors": fatal, "warnings": [],
            "snapshot_id": None, "manifest_sha256": None,
            "latest_common_session": None, "coverage": {},
        }

    series = loaded["series"]
    dates = {ticker: {point["date"] for point in points} for ticker, points in series.items()}
    coverage = {}
    warnings = []
    for ticker, points in sorted(series.items()):
        ordered = sorted(dates[ticker])
        gaps = []
        for previous, current in zip(ordered, ordered[1:]):
            gap_days = (date.fromisoformat(current) - date.fromisoformat(previous)).days
            if gap_days > 4:
                gaps.append({"from": previous, "to": current, "calendar_days": gap_days, "status": "unconfirmed_gap_not_assumed_market_closure"})
        coverage[ticker] = {
            "row_count": len(points), "coverage_start": ordered[0] if ordered else None,
            "coverage_end": ordered[-1] if ordered else None, "suspicious_calendar_gaps": gaps,
        }
        if gaps:
            warnings.append(f"{ticker} has {len(gaps)} calendar gap(s) over four days; no closure is inferred without an independent calendar.")

    benchmark_dates = dates.get(BENCHMARK_TICKER, set())
    missing_benchmark = sorted(set.union(*(dates.get(ticker, set()) for ticker in REQUIRED_TICKERS if ticker != BENCHMARK_TICKER)) - benchmark_dates)
    if missing_benchmark:
        fatal.append(f"benchmark bars missing on {len(missing_benchmark)} sessions present in other series")
    stock_mismatches = {}
    for ticker in STOCK_TICKERS:
        stock_dates = dates.get(ticker, set())
        in_coverage = {day for day in benchmark_dates if coverage.get(ticker, {}).get("coverage_start") <= day <= coverage.get(ticker, {}).get("coverage_end")} if coverage.get(ticker, {}).get("coverage_start") and coverage.get(ticker, {}).get("coverage_end") else set()
        missing_stock = sorted(in_coverage - stock_dates)
        stock_only = sorted(stock_dates - benchmark_dates)
        stock_mismatches[ticker] = {"missing_stock_on_benchmark_sessions": missing_stock, "stock_sessions_without_benchmark_bar": stock_only}
        if missing_stock:
            warnings.append(f"{ticker} is missing {len(missing_stock)} bar(s) on observed SPY sessions within its coverage.")
        if stock_only:
            warnings.append(f"{ticker} has {len(stock_only)} date(s) without an SPY bar; these are not assumed to be closures.")

    # Require an aligned latest anchor across every stock, SPY, and sector proxy.
    latest = None
    try:
        latest = latest_common_anchor(series, as_of_session=cutoff)
    except ValueError as exc:
        fatal.append(str(exc))
    lag = (cutoff - latest).days if latest else None
    if latest and lag is not None and lag > MAX_COMMON_SESSION_LAG_DAYS:
        fatal.append(f"latest common session {latest.isoformat()} is stale by {lag} calendar days relative to {cutoff.isoformat()}")
    eastern = instant.astimezone(NEW_YORK)
    current_rows = sorted(ticker for ticker, ticker_dates in dates.items() if eastern.date().isoformat() in ticker_dates)
    current_partial_excluded = bool(current_rows and not current_session_eligible)
    if current_partial_excluded:
        warnings.append("Current-date bars are excluded because the 16:15 America/New_York completeness buffer has not elapsed.")
    if not current_session_eligible and eastern.weekday() < 5:
        warnings.append("No forecast will be generated before the close buffer; evaluation uses data only through the prior calendar date.")
    if len(set(dates.get(BENCHMARK_TICKER, set()))) == 0:
        fatal.append("No benchmark sessions are available.")

    return {
        "valid": not fatal, "fatal_errors": fatal, "warnings": sorted(set(warnings)),
        "snapshot_id": f"yahoo-{file_sha256(root / 'manifest.json')[:20]}",
        "manifest_sha256": file_sha256(root / "manifest.json"),
        "source": manifest.get("source"), "retrieved_at_utc": manifest.get("retrieved_at_utc"),
        "quality_validation_error": manifest.get("quality_validation_error"),
        "cutoff_session": cutoff.isoformat(),
        "latest_common_session": latest.isoformat() if latest else None,
        "calendar_days_since_common_session": lag,
        "current_session_eligible": current_session_eligible,
        "current_date_rows_excluded": current_rows if current_partial_excluded else [],
        "coverage": coverage, "stock_benchmark_alignment": stock_mismatches,
        "missing_benchmark_sessions_seen_in_other_series": missing_benchmark,
        "independent_exchange_calendar_available": False,
    }


def backup_registry(registry_path: str | Path, backup_dir: str | Path) -> dict:
    """Create a consistent SQLite backup and verify it before publishing the file."""
    source_path = Path(registry_path)
    initialize_registry(source_path)
    destination_dir = Path(backup_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    suffix = uuid.uuid4().hex[:8]
    final_path = destination_dir / f"forecast_registry_backup_{stamp}_{suffix}.sqlite3"
    temporary_path = destination_dir / f".{final_path.name}.partial"
    if final_path.exists() or temporary_path.exists():
        raise FileExistsError("Refusing to overwrite an existing registry backup.")

    source = sqlite3.connect(source_path, timeout=30)
    destination = sqlite3.connect(temporary_path)
    try:
        source.backup(destination)
        integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise sqlite3.DatabaseError(f"Backup integrity check failed: {integrity}")
        table_names = ("snapshots", "snapshot_bars", "snapshot_revisions", "forecasts", "outcomes", "research_references")
        source_counts = {table: source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in table_names}
        backup_counts = {table: destination.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in table_names}
        if source_counts != backup_counts:
            raise sqlite3.DatabaseError("Backup row counts do not match the live registry.")
        destination.commit()
    finally:
        destination.close()
        source.close()
    if final_path.exists():
        raise FileExistsError("Refusing to overwrite an existing registry backup.")
    os.rename(temporary_path, final_path)
    return {
        "path": str(final_path), "sha256": file_sha256(final_path),
        "integrity_check": "ok", "table_counts": source_counts,
    }


def _latest_outcomes(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(
        """
        WITH ranked AS (
          SELECT o.*, s.retrieved_at_utc,
                 ROW_NUMBER() OVER (PARTITION BY o.forecast_id ORDER BY s.retrieved_at_utc DESC, o.evaluated_at_utc DESC) AS rn
          FROM outcomes o JOIN snapshots s ON s.snapshot_id=o.evaluation_snapshot_identifier
        )
        SELECT r.*, f.ticker, f.target_name, f.prediction_horizon, f.model_identifier,
               f.forecast_anchor_session, f.predicted_return, f.predicted_direction
        FROM ranked r JOIN forecasts f ON f.forecast_id=r.forecast_id WHERE r.rn=1
        """
    ).fetchall()
    return [dict(row) for row in rows]


def registry_status(registry_path: str | Path) -> dict:
    initialize_registry(registry_path)
    with _connect(registry_path) as db:
        forecast_count = db.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
        outcome_count = db.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
        incomplete_assessments = db.execute("SELECT COUNT(*) FROM outcomes WHERE outcome_status!='complete'").fetchone()[0]
        latest_snapshot = db.execute("SELECT * FROM snapshots ORDER BY retrieved_at_utc DESC, snapshot_id DESC LIMIT 1").fetchone()
        latest_anchor_row = db.execute("SELECT MAX(forecast_anchor_session) AS anchor FROM forecasts").fetchone()
        latest_outcomes = _latest_outcomes(db)
        revisions = db.execute("SELECT COUNT(*) FROM snapshot_revisions").fetchone()[0]

    completed_ids = {row["forecast_id"] for row in latest_outcomes if row["outcome_status"] == "complete"}
    incomplete_ids = {row["forecast_id"] for row in latest_outcomes if row["outcome_status"] != "complete"}
    groups = defaultdict(list)
    for row in latest_outcomes:
        if row["outcome_status"] == "complete" and row["realized_target_return"] is not None:
            groups[(row["model_identifier"], row["prediction_horizon"], row["target_name"])].append(row)
    performance = []
    for (model, horizon, target), rows in sorted(groups.items()):
        errors = [float(row["realized_target_return"]) - float(row["predicted_return"]) for row in rows]
        directional = [int((float(row["predicted_return"]) > 0) == (float(row["realized_target_return"]) > 0)) for row in rows]
        n, anchors = len(rows), len({row["forecast_anchor_session"] for row in rows})
        performance.append({
            "model_identifier": model, "horizon": horizon, "target": target,
            "sample_count": n, "distinct_forecast_anchors": anchors,
            "mae": sum(abs(value) for value in errors) / n,
            "directional_accuracy": sum(directional) / n,
            "sample_assessment": "descriptive_only" if n >= MIN_STATUS_OUTCOMES and anchors >= MIN_STATUS_ANCHORS else "too_small_for_meaningful_conclusions",
        })
    latest_snapshot_data = None
    if latest_snapshot:
        notes = json.loads(latest_snapshot["quality_notes_json"])
        latest_snapshot_data = {
            "snapshot_id": latest_snapshot["snapshot_id"],
            "manifest_sha256": latest_snapshot["manifest_sha256"],
            "source": latest_snapshot["source"],
            "retrieved_at_utc": latest_snapshot["retrieved_at_utc"],
            "registry_status": "registered_with_warning" if notes.get("manifest_quality_validation_error") else "registered",
            "quality_warning": notes.get("manifest_quality_validation_error"),
        }
    return {
        "total_forecasts": forecast_count,
        "pending_forecasts": forecast_count - len(completed_ids),
        "matured_forecasts": len(completed_ids),
        "currently_incomplete_forecasts": len(incomplete_ids),
        "incomplete_outcome_assessments_total": incomplete_assessments,
        "outcome_assessments_total": outcome_count,
        "latest_forecast_anchor": latest_anchor_row["anchor"],
        "latest_successful_snapshot": latest_snapshot_data,
        "detected_historical_bar_revisions": revisions,
        "performance": performance,
        "performance_note": "Outcome metrics are descriptive. Samples below 30 records or five distinct anchors are labeled too small; overlapping forecast horizons remain dependent even above that threshold.",
    }


def audit_registry(registry_path: str | Path, phase5c_path: str | Path) -> dict:
    """Read-only integrity audit of append-only controls and provenance links."""
    initialize_registry(registry_path)
    with _connect(registry_path) as db:
        trigger_names = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        required_triggers = {
            "forecasts_no_update", "forecasts_no_delete", "outcomes_no_update", "outcomes_no_delete",
            "snapshots_no_update", "snapshots_no_delete", "snapshot_bars_no_update", "snapshot_bars_no_delete",
            "revisions_no_update", "revisions_no_delete", "references_no_update", "references_no_delete",
        }
        forecast_rows = [dict(row) for row in db.execute("SELECT * FROM forecasts")]
        snapshot_rows = [dict(row) for row in db.execute("SELECT * FROM snapshots")]
        outcome_count = db.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
        reference = db.execute("SELECT * FROM research_references WHERE reference_id='phase5c_final_holdout'").fetchone()
        bad_cutoffs = [row["forecast_id"] for row in forecast_rows if row["training_label_cutoff"] >= row["forecast_anchor_session"]]
        bad_feature_hashes = []
        bad_model_hashes = []
        bad_information_cutoffs = []
        bad_creation_order = []
        for row in forecast_rows:
            if hashlib.sha256(row["feature_values_json"].encode("utf-8")).hexdigest() != row["feature_values_sha256"]:
                bad_feature_hashes.append(row["forecast_id"])
            try:
                parameters = json.loads(row["model_parameters_json"])
                if stable_sha256(parameters) != row["model_parameters_sha256"]:
                    bad_model_hashes.append(row["forecast_id"])
            except (TypeError, ValueError, json.JSONDecodeError):
                bad_model_hashes.append(row["forecast_id"])
            if row["forecast_anchor_session"] not in row["information_cutoff"]:
                bad_information_cutoffs.append(row["forecast_id"])
            if row["training_snapshot_identifier"] != row["dataset_snapshot_identifier"]:
                bad_creation_order.append(row["forecast_id"])
            else:
                snap = next((item for item in snapshot_rows if item["snapshot_id"] == row["dataset_snapshot_identifier"]), None)
                if snap and row["forecast_created_at_utc"] < snap["retrieved_at_utc"]:
                    bad_creation_order.append(row["forecast_id"])
        bad_snapshots = [
            row["forecast_id"] for row in forecast_rows
            if not any(s["snapshot_id"] == row["dataset_snapshot_identifier"] and s["manifest_sha256"] == row["dataset_manifest_sha256"] for s in snapshot_rows)
        ]
        duplicate_keys = db.execute("SELECT COUNT(*) FROM (SELECT unique_key FROM forecasts GROUP BY unique_key HAVING COUNT(*)>1)").fetchone()[0]
        outcome_duplicate_keys = db.execute("SELECT COUNT(*) FROM (SELECT forecast_id,evaluation_snapshot_identifier FROM outcomes GROUP BY forecast_id,evaluation_snapshot_identifier HAVING COUNT(*)>1)").fetchone()[0]
    snapshot_checks = []
    for row in snapshot_rows:
        path = Path(row["archive_path"])
        try:
            loaded = load_market_snapshot(path, verify_hashes=True)
            actual_hash = file_sha256(path / "manifest.json")
            valid = actual_hash == row["manifest_sha256"]
            reason = None if valid else "registry manifest hash differs from archived manifest"
        except Exception as exc:
            valid, reason = False, f"{type(exc).__name__}: {exc}"
        snapshot_checks.append({"snapshot_id": row["snapshot_id"], "valid": valid, "reason": reason})
    phase5c_check = {"registered": reference is not None, "valid": False, "registered_sha256": None, "actual_sha256": None}
    if reference:
        phase5c_check["registered_sha256"] = reference["artifact_sha256"]
        try:
            phase5c_check["actual_sha256"] = file_sha256(Path(phase5c_path))
            phase5c_check["valid"] = phase5c_check["actual_sha256"] == reference["artifact_sha256"]
        except OSError:
            phase5c_check["valid"] = False
    checks = {
        "append_only_triggers_present": required_triggers.issubset(trigger_names),
        "training_labels_strictly_before_anchor": not bad_cutoffs,
        "feature_and_model_hashes_match": not bad_feature_hashes and not bad_model_hashes,
        "information_cutoff_matches_anchor": not bad_information_cutoffs,
        "forecast_created_after_training_snapshot": not bad_creation_order,
        "snapshot_provenance_matches_forecasts": not bad_snapshots,
        "forecast_unique_keys": duplicate_keys == 0,
        "outcome_unique_forecast_snapshot_pairs": outcome_duplicate_keys == 0,
        "all_archived_snapshots_hash_verified": all(row["valid"] for row in snapshot_checks),
        "phase5c_reference_unchanged": phase5c_check["valid"],
    }
    return {
        "valid": all(checks.values()), "checks": checks,
        "forecast_count": len(forecast_rows), "snapshot_count": len(snapshot_rows),
        "outcome_count": outcome_count,
        "bad_training_cutoff_forecast_ids": bad_cutoffs,
        "bad_feature_hash_forecast_ids": bad_feature_hashes,
        "bad_model_hash_forecast_ids": bad_model_hashes,
        "bad_information_cutoff_forecast_ids": bad_information_cutoffs,
        "bad_forecast_creation_order_ids": bad_creation_order,
        "bad_snapshot_provenance_forecast_ids": bad_snapshots,
        "snapshot_hash_checks": snapshot_checks,
        "phase5c_reference": phase5c_check,
    }


def update_registry(
    registry_path: str | Path,
    store_root: str | Path,
    phase5c_path: str | Path,
    *,
    now: datetime | None = None,
    downloader=None,
    evaluator=evaluate_forward_outcomes,
    forecaster=create_forward_predictions,
) -> dict:
    """Download, validate, back up, archive, evaluate, then conditionally forecast."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("Update clock must include a timezone.")
    store = Path(store_root).resolve()
    store.mkdir(parents=True, exist_ok=True)
    registry = Path(registry_path).resolve()
    initialize_registry(registry)
    from evaluations.download_market_data import download_snapshot
    download = downloader or download_snapshot

    with tempfile.TemporaryDirectory(prefix="phase5e-download-", dir=store) as temporary:
        staging = Path(temporary) / "market_cache"
        staging.mkdir(parents=True, exist_ok=True)
        captured = io.StringIO()
        try:
            with redirect_stdout(captured):
                downloaded_path = download("2010-01-01", None, staging, refresh=True)
        except Exception as exc:
            raise DownloadWorkflowError(f"Fresh market-data download failed: {type(exc).__name__}: {exc}") from exc
        snapshot_dir = Path(downloaded_path).resolve()
        if not snapshot_dir.is_dir():
            raise DownloadWorkflowError("Downloader did not return an existing snapshot directory.")
        try:
            validation = inspect_snapshot(snapshot_dir, now=instant)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise SnapshotValidationError(f"Downloaded snapshot could not be inspected: {type(exc).__name__}: {exc}") from exc
        if not validation["valid"]:
            errors = "; ".join(validation["fatal_errors"])
            raise SnapshotValidationError(f"Snapshot rejected; registry remains unchanged: {errors}")

        # The full downloaded snapshot is copied into the immutable registry
        # archive before staging cleanup. Backup happens before its DB commit.
        backup = backup_registry(registry, store / "backups")
        # Recover archive copies left by an interruption after archive creation
        # but before the corresponding SQLite transaction committed.
        with _connect(registry) as db:
            registered_ids = {row["snapshot_id"] for row in db.execute("SELECT snapshot_id FROM snapshots")}
        recovered = []
        for candidate in sorted((store / "snapshots").glob("yahoo-*")) if (store / "snapshots").exists() else []:
            if not candidate.is_dir() or candidate.name in registered_ids:
                continue
            try:
                old = load_market_snapshot(candidate, verify_hashes=True)
                old_manifest = old["manifest"]
                if set(REQUIRED_TICKERS) - set(old_manifest.get("series", {})) or old_manifest.get("download_failures") or old_manifest.get("quality_validation_error"):
                    continue
                recovered.append(register_snapshot(candidate, registry, store))
            except (OSError, ValueError, KeyError, TypeError):
                # Leave an unverified orphan untouched for manual inspection.
                continue
        registered = register_snapshot(snapshot_dir, registry, store)
        archive_path = registered["archive_path"]
        cutoff = date.fromisoformat(validation["cutoff_session"])
        outcome_report = evaluator(archive_path, registry, store, as_of_session=cutoff)

        eastern = instant.astimezone(NEW_YORK)
        anchor = validation["latest_common_session"]
        anchor_rows = 0
        forecast_report = None
        forecast_skipped_reason = None
        if anchor:
            with _connect(registry) as db:
                anchor_rows = db.execute("SELECT COUNT(*) FROM forecasts WHERE forecast_anchor_session=?", (anchor,)).fetchone()[0]
        can_create = (
            validation["current_session_eligible"]
            and eastern.weekday() < 5
            and anchor == eastern.date().isoformat()
        )
        expected_rows = len(STOCK_TICKERS) * 2 * 2 * len(MODEL_DEFINITIONS)
        if not can_create:
            forecast_skipped_reason = "No newly completed common session for the current US market date; no backdated forecast was created."
        elif anchor_rows >= expected_rows:
            forecast_skipped_reason = f"Anchor {anchor} already has {anchor_rows} forecast records."
        else:
            # If interrupted after partial inserts, semantic uniqueness makes
            # the retry fill missing model rows without changing existing ones.
            forecast_report = forecaster(
                archive_path, registry, store, phase5c_path,
                created_at_utc=instant.astimezone(timezone.utc).isoformat(),
                as_of_session=cutoff,
            )
        return {
            "status": "updated",
            "snapshot": {key: validation.get(key) for key in (
                "snapshot_id", "manifest_sha256", "retrieved_at_utc", "cutoff_session",
                "latest_common_session", "calendar_days_since_common_session",
            )},
            "snapshot_registered": registered,
            "recovered_orphan_snapshots": recovered,
            "session_validation": {
                "missing_stock_bar_counts": {
                    ticker: len(info["missing_stock_on_benchmark_sessions"])
                    for ticker, info in validation["stock_benchmark_alignment"].items()
                },
                "stock_dates_without_benchmark_counts": {
                    ticker: len(info["stock_sessions_without_benchmark_bar"])
                    for ticker, info in validation["stock_benchmark_alignment"].items()
                },
                "missing_benchmark_sessions_seen_elsewhere": len(validation["missing_benchmark_sessions_seen_in_other_series"]),
                "suspicious_gap_counts": {
                    ticker: len(info["suspicious_calendar_gaps"])
                    for ticker, info in validation["coverage"].items()
                },
                "independent_exchange_calendar_available": validation["independent_exchange_calendar_available"],
                "current_date_rows_excluded": validation["current_date_rows_excluded"],
            },
            "snapshot_warnings": validation["warnings"],
            "backup": backup,
            "outcome_evaluation": outcome_report,
            "new_forecasts": forecast_report,
            "forecast_skipped_reason": forecast_skipped_reason,
            "forecast_rows_before_anchor_update": anchor_rows,
            "download_log_summary": "Existing Phase 5B downloader completed; detailed per-symbol progress was captured.",
        }
