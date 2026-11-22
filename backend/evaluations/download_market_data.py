"""Download a small manual Yahoo Finance research snapshot outside the sandbox."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import sys
import time

import pandas as pd
import yfinance as yf

from app.research.market_data import CSV_COLUMNS, MARKET_SNAPSHOT_SCHEMA, REQUIRED_TICKERS, file_sha256, load_market_snapshot


def _safe_file_symbol(symbol: str) -> str:
    return symbol.replace("^", "INDEX_").replace("/", "_")


def normalize_history(symbol: str, history: pd.DataFrame) -> list[dict]:
    """Preserve raw OHLC/actions and derive retrospective adjusted OHLCV fields."""
    if history is None or history.empty:
        return []
    frame = history.sort_index().copy()
    needed = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
    if not needed.issubset(frame.columns):
        raise ValueError(f"Provider response missing columns: {','.join(sorted(needed - set(frame.columns)))}")
    split_values = [float(value) if pd.notna(value) else 0.0 for value in frame.get("Stock Splits", pd.Series(0.0, index=frame.index)).tolist()]
    future_split_multipliers = [1.0] * len(frame)
    split_multiplier = 1.0
    for index in range(len(frame) - 1, -1, -1):
        future_split_multipliers[index] = split_multiplier
        action = split_values[index]
        if action > 0 and action != 1:
            split_multiplier *= action
    rows = []
    for index, (_, row) in enumerate(frame.iterrows()):
        raw_close = float(row["Close"]) if pd.notna(row["Close"]) else None
        adjusted_close = float(row["Adj Close"]) if pd.notna(row["Adj Close"]) else None
        factor = adjusted_close / raw_close if adjusted_close and raw_close else None
        def adjusted(column: str) -> float | None:
            raw = row.get(column)
            return float(raw) * factor if pd.notna(raw) and factor is not None else None
        raw_volume = float(row["Volume"]) if pd.notna(row["Volume"]) else None
        dividends = row.get("Dividends", 0.0)
        split = row.get("Stock Splits", 0.0)
        trading_date = row.name.date().isoformat() if hasattr(row.name, "date") else str(row.name)[:10]
        rows.append({
            "date": trading_date, "ticker": symbol,
            "raw_open": row.get("Open"), "raw_high": row.get("High"), "raw_low": row.get("Low"),
            "raw_close": raw_close, "raw_adj_close": adjusted_close, "raw_volume": raw_volume,
            "dividends": float(dividends) if pd.notna(dividends) else 0.0,
            "stock_splits": float(split) if pd.notna(split) else 0.0,
            "adjustment_factor": factor,
            "adjusted_open": adjusted("Open"), "adjusted_high": adjusted("High"),
            "adjusted_low": adjusted("Low"), "adjusted_close": adjusted_close,
            "adjusted_volume": raw_volume * future_split_multipliers[index] if raw_volume is not None else None,
        })
    return rows


def _write_series(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        import csv
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in CSV_COLUMNS})


def _find_cached_snapshot(root: Path, start: str, end: str | None) -> Path | None:
    if not root.is_dir():
        return None
    for candidate in sorted(root.glob("snapshot_*"), reverse=True):
        try:
            manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
            if manifest.get("requested_start") == start and manifest.get("requested_end_exclusive") == end:
                if set(REQUIRED_TICKERS).issubset(manifest.get("series", {})):
                    load_market_snapshot(candidate)
                    return candidate
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return None


def download_snapshot(start: str, end: str | None, output_root: Path, *, refresh: bool = False) -> Path:
    date.fromisoformat(start)
    if end:
        date.fromisoformat(end)
        if end <= start:
            raise ValueError("--end is exclusive and must be after --start")
    if not refresh:
        cached = _find_cached_snapshot(output_root, start, end)
        if cached:
            print(f"cache_reused={cached}")
            return cached
    retrieved_at = datetime.now(timezone.utc).isoformat()
    snapshot = output_root / ("snapshot_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    snapshot.mkdir(parents=True, exist_ok=False)
    # yfinance stores exchange timezone metadata in SQLite. Point it at the
    # workspace cache so restricted Windows profiles do not fail before the
    # provider request is attempted.
    yf_cache = output_root / ".yfinance-cache"
    yf_cache.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(yf_cache))
    records, failures = {}, {}
    for symbol in REQUIRED_TICKERS:
        try:
            history = yf.Ticker(symbol).history(
                start=start, end=end, interval="1d", auto_adjust=False,
                actions=True, timeout=25, raise_errors=True,
            )
            rows = normalize_history(symbol, history)
            if not rows:
                raise ValueError("Provider returned no daily observations")
            filename = _safe_file_symbol(symbol) + ".csv"
            path = snapshot / filename
            _write_series(path, rows)
            records[symbol] = {
                "file": filename, "sha256": file_sha256(path),
                "row_count": len(rows), "coverage_start": rows[0]["date"],
                "coverage_end": rows[-1]["date"],
            }
            print(f"downloaded={symbol} rows={len(rows)} coverage={rows[0]['date']}..{rows[-1]['date']}")
        except Exception as exc:
            failures[symbol] = {"error_type": type(exc).__name__, "message": str(exc)[:300]}
            print(f"download_failed={symbol} error_type={type(exc).__name__}")
        time.sleep(0.15)
    manifest = {
        "schema_version": MARKET_SNAPSHOT_SCHEMA,
        "source": "Yahoo Finance via yfinance",
        "retrieved_at_utc": retrieved_at,
        "requested_start": start,
        "requested_end_exclusive": end,
        "provider_timezone": "Exchange-local trading dates as returned by yfinance",
        "yfinance_version": importlib.metadata.version("yfinance"),
        "adjustments": {
            "raw_fields_preserved": True,
            "adjusted_ohlc": "Raw OHLC multiplied by provider Adj Close / raw Close. The provider adjustment may retrospectively include splits, distributions, and revisions.",
            "adjusted_volume": "Raw volume multiplied by split ratios from later split dates only; volume is not dividend-adjusted.",
            "corporate_actions": "Dividends and Stock Splits columns are retained from provider output.",
        },
        "fixed_research_universe": list(REQUIRED_TICKERS),
        "security_roles": {
            "stocks": ["AAPL", "MSFT", "NVDA", "AMZN", "TSLA"],
            "benchmark_proxy": "SPY",
            "sector_proxies": {"XLK": ["AAPL", "MSFT", "NVDA"], "XLY": ["AMZN", "TSLA"]},
        },
        "series": records,
        "download_failures": failures,
    }
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    if records:
        try:
            imported = load_market_snapshot(snapshot)
            manifest["quality_report"] = imported["quality_report"]
            (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as exc:
            manifest["quality_validation_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"snapshot={snapshot}")
    print(f"series_downloaded={len(records)}/{len(REQUIRED_TICKERS)}")
    print(f"failures={len(failures)}")
    if len(records) != len(REQUIRED_TICKERS):
        print("Snapshot is partial; the real-data evaluator will report excluded symbols or fail if SPY is absent.")
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="Inclusive YYYY-MM-DD")
    parser.add_argument("--end", help="Exclusive YYYY-MM-DD; defaults to latest provider data")
    parser.add_argument("--output-root", default=str(Path(__file__).resolve().parents[1] / "data" / "market_cache" / "phase5b"))
    parser.add_argument("--refresh", action="store_true", help="Download a new immutable snapshot instead of reusing a matching cached one")
    args = parser.parse_args()
    try:
        download_snapshot(args.start, args.end, Path(args.output_root), refresh=args.refresh)
    except Exception as exc:
        print(f"download_workflow_failed={type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
