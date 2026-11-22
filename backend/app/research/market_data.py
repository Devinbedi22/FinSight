"""Local Yahoo Finance snapshot validation and import for offline research."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

MARKET_SNAPSHOT_SCHEMA = "finsight.market-snapshot.v1"
STOCK_TICKERS = ("AAPL", "MSFT", "NVDA", "AMZN", "TSLA")
BENCHMARK_TICKER = "SPY"
SECTOR_PROXY_BY_TICKER = {
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK",
    "AMZN": "XLY", "TSLA": "XLY",
}
GICS_SECTOR_BY_TICKER = {
    "AAPL": "Information Technology", "MSFT": "Information Technology",
    "NVDA": "Information Technology", "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary",
}
REQUIRED_TICKERS = (*STOCK_TICKERS, BENCHMARK_TICKER, "XLK", "XLY")
CSV_COLUMNS = (
    "date", "ticker", "raw_open", "raw_high", "raw_low", "raw_close",
    "raw_adj_close", "raw_volume", "dividends", "stock_splits",
    "adjustment_factor", "adjusted_open", "adjusted_high", "adjusted_low",
    "adjusted_close", "adjusted_volume",
)


class MarketDataImportError(ValueError):
    """A local provider snapshot failed provenance, integrity, or quality checks."""


def _float(value: Any) -> float | None:
    if value in (None, "", "nan", "NaN"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_series_rows(ticker: str, rows: list[dict]) -> dict:
    if not rows:
        raise MarketDataImportError(f"No rows found for {ticker}.")
    dates = [row.get("date", "") for row in rows]
    if any(not value for value in dates):
        raise MarketDataImportError(f"{ticker} has an empty trading date.")
    from datetime import date
    try:
        for value in dates:
            date.fromisoformat(value)
    except ValueError as exc:
        raise MarketDataImportError(f"{ticker} has an invalid ISO trading date.") from exc
    if dates != sorted(dates):
        raise MarketDataImportError(f"{ticker} dates are not sorted ascending.")
    if len(dates) != len(set(dates)):
        raise MarketDataImportError(f"{ticker} has duplicate trading dates.")
    missing_prices = []
    invalid_ohlc = []
    missing_volume = 0
    invalid_volume = []
    adjustment_mismatches = []
    for row in rows:
        values = {name: _float(row.get(name)) for name in ("adjusted_open", "adjusted_high", "adjusted_low", "adjusted_close")}
        if any(value is None or value <= 0 for value in values.values()):
            missing_prices.append(row["date"])
        elif (
            values["adjusted_high"] + max(values["adjusted_high"], values["adjusted_open"], values["adjusted_close"]) * 1e-12
            < max(values["adjusted_open"], values["adjusted_close"])
            or values["adjusted_low"] - max(values["adjusted_low"], values["adjusted_open"], values["adjusted_close"]) * 1e-12
            > min(values["adjusted_open"], values["adjusted_close"])
        ):
            # Adjusted OHLC is computed by multiplying provider floats by an
            # adjustment factor. Permit only machine-scale rounding at bounds.
            invalid_ohlc.append(row["date"])
        volume = _float(row.get("adjusted_volume"))
        if volume is None:
            missing_volume += 1
        elif volume < 0:
            invalid_volume.append(row["date"])
        factor = _float(row.get("adjustment_factor"))
        raw_close = _float(row.get("raw_close"))
        raw_adjusted_close = _float(row.get("raw_adj_close"))
        reconciles = factor is not None and factor > 0 and raw_close is not None and raw_adjusted_close is not None and math.isclose(raw_close * factor, raw_adjusted_close, rel_tol=1e-6, abs_tol=1e-6)
        for raw_column, adjusted_column in (("raw_open", "adjusted_open"), ("raw_high", "adjusted_high"), ("raw_low", "adjusted_low")):
            raw_value, adjusted_value = _float(row.get(raw_column)), _float(row.get(adjusted_column))
            reconciles = reconciles and raw_value is not None and adjusted_value is not None and math.isclose(raw_value * factor, adjusted_value, rel_tol=1e-6, abs_tol=1e-6) if factor is not None else False
        if not reconciles:
            adjustment_mismatches.append(row["date"])
    if missing_prices:
        raise MarketDataImportError(f"{ticker} has invalid or missing adjusted OHLC on {len(missing_prices)} rows.")
    if invalid_ohlc:
        raise MarketDataImportError(f"{ticker} violates adjusted OHLC high/low bounds on {len(invalid_ohlc)} rows.")
    if invalid_volume:
        raise MarketDataImportError(f"{ticker} has negative adjusted volume on {len(invalid_volume)} rows.")
    if adjustment_mismatches:
        raise MarketDataImportError(f"{ticker} adjustment factor does not reconcile with Adj Close on {len(adjustment_mismatches)} rows.")
    gaps = []
    for previous, current in zip(dates, dates[1:]):
        days = (date.fromisoformat(current) - date.fromisoformat(previous)).days
        if days > 4:
            gaps.append({"from": previous, "to": current, "calendar_days": days})
    return {
        "ticker": ticker, "row_count": len(rows), "coverage_start": dates[0], "coverage_end": dates[-1],
        "missing_volume_rows": missing_volume,
        "corporate_action_rows": sum(1 for row in rows if _float(row.get("dividends")) not in (None, 0) or _float(row.get("stock_splits")) not in (None, 0, 1)),
        "adjustment_factor_range": [
            min(_float(row["adjustment_factor"]) for row in rows),
            max(_float(row["adjustment_factor"]) for row in rows),
        ],
        "long_calendar_gaps_over_4_days": gaps,
    }


def load_market_snapshot(snapshot_dir: str | Path, *, verify_hashes: bool = True) -> dict:
    """Read a downloaded snapshot, verify manifest/file hashes and normalized prices."""
    root = Path(snapshot_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise MarketDataImportError(f"Snapshot manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != MARKET_SNAPSHOT_SCHEMA:
        raise MarketDataImportError("Unsupported market snapshot schema.")
    if manifest.get("source") != "Yahoo Finance via yfinance":
        raise MarketDataImportError("Snapshot source is not the declared Yahoo Finance downloader.")
    from datetime import date, datetime
    retrieved = manifest.get("retrieved_at_utc")
    try:
        retrieved_at = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
        requested_start = date.fromisoformat(manifest["requested_start"])
        requested_end = date.fromisoformat(manifest["requested_end_exclusive"]) if manifest.get("requested_end_exclusive") else None
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise MarketDataImportError("Snapshot manifest has invalid retrieval or requested date metadata.") from exc
    if retrieved_at.tzinfo is None:
        raise MarketDataImportError("Manifest retrieval timestamp must include a timezone.")
    series: dict[str, list[dict]] = {}
    reports = {}
    for ticker, record in manifest.get("series", {}).items():
        path = root / record.get("file", "")
        if not path.is_file():
            raise MarketDataImportError(f"Snapshot file missing for {ticker}.")
        if verify_hashes and file_sha256(path) != record.get("sha256"):
            raise MarketDataImportError(f"Snapshot SHA-256 mismatch for {ticker}.")
        with path.open("r", newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if not set(CSV_COLUMNS).issubset(reader.fieldnames or []):
                raise MarketDataImportError(f"{ticker} CSV is missing required columns.")
            raw_rows = list(reader)
        if any(row.get("ticker") != ticker for row in raw_rows):
            raise MarketDataImportError(f"Ticker column mismatch in {ticker} CSV.")
        if any(date.fromisoformat(row["date"]) < requested_start or (requested_end and date.fromisoformat(row["date"]) >= requested_end) for row in raw_rows):
            raise MarketDataImportError(f"{ticker} rows fall outside the requested date interval.")
        if record.get("row_count") is not None and int(record["row_count"]) != len(raw_rows):
            raise MarketDataImportError(f"Manifest row count mismatch for {ticker}.")
        if raw_rows and (record.get("coverage_start") not in (None, raw_rows[0]["date"]) or record.get("coverage_end") not in (None, raw_rows[-1]["date"])):
            raise MarketDataImportError(f"Manifest coverage dates mismatch for {ticker}.")
        reports[ticker] = validate_series_rows(ticker, raw_rows)
        series[ticker] = [{
            "date": row["date"], "open": _float(row.get("adjusted_open")),
            "high": _float(row.get("adjusted_high")), "low": _float(row.get("adjusted_low")),
            "close": _float(row.get("adjusted_close")),
            "volume": _float(row.get("adjusted_volume")),
        } for row in raw_rows]
    if BENCHMARK_TICKER not in series:
        raise MarketDataImportError(f"Required S&P 500 proxy {BENCHMARK_TICKER} is absent.")
    benchmark_dates = {row["date"] for row in series[BENCHMARK_TICKER]}
    for ticker in STOCK_TICKERS:
        if ticker not in series:
            continue
        dates = {row["date"] for row in series[ticker]}
        reports[ticker]["sessions_without_benchmark_bar"] = len(dates - benchmark_dates)
        reports[ticker]["benchmark_sessions_without_stock_bar"] = len(benchmark_dates - dates)
    present_research_stocks = [ticker for ticker in STOCK_TICKERS if ticker in series]
    if not present_research_stocks:
        raise MarketDataImportError("No research stock symbols are present in this snapshot.")
    return {"manifest": manifest, "series": series, "quality_report": reports}
