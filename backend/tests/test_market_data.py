"""Deterministic local-snapshot validation tests; fixtures are not market data."""

import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from app.research.market_data import (
    CSV_COLUMNS,
    MARKET_SNAPSHOT_SCHEMA,
    MarketDataImportError,
    load_market_snapshot,
    validate_series_rows,
)
from evaluations.download_market_data import normalize_history


def provider_fixture(symbol="AAPL"):
    index = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
    return pd.DataFrame({
        "Open": [100.0, 25.0, 26.0], "High": [102.0, 26.0, 27.0],
        "Low": [99.0, 24.0, 25.0], "Close": [100.0, 25.0, 26.0],
        "Adj Close": [50.0, 25.0, 26.0], "Volume": [1000.0, 4000.0, 4200.0],
        "Dividends": [0.0, 0.0, 0.0], "Stock Splits": [0.0, 2.0, 0.0],
    }, index=index)


def local_rows(ticker, dates):
    return [{
        "date": day, "ticker": ticker,
        "raw_open": 10, "raw_high": 11, "raw_low": 9, "raw_close": 10,
        "raw_adj_close": 10, "raw_volume": 100, "dividends": 0, "stock_splits": 0,
        "adjustment_factor": 1, "adjusted_open": 10, "adjusted_high": 11,
        "adjusted_low": 9, "adjusted_close": 10, "adjusted_volume": 100,
    } for day in dates]


class MarketDataTest(unittest.TestCase):
    def test_provider_adjustment_and_split_volume_normalization(self):
        rows = normalize_history("AAPL", provider_fixture())
        self.assertEqual(rows[0]["adjusted_open"], 50.0)
        self.assertEqual(rows[0]["adjusted_close"], 50.0)
        self.assertEqual(rows[0]["adjusted_volume"], 2000.0)
        self.assertEqual(rows[1]["adjusted_volume"], 4000.0)
        self.assertEqual(rows[1]["stock_splits"], 2.0)

    def test_quality_validation_rejects_duplicate_and_bad_ohlc(self):
        rows = local_rows("AAPL", ["2024-01-02", "2024-01-03"])
        with self.assertRaisesRegex(MarketDataImportError, "duplicate"):
            validate_series_rows("AAPL", [rows[0], rows[0]])
        bad = [dict(row) for row in rows]
        bad[0]["adjusted_high"] = 8
        with self.assertRaisesRegex(MarketDataImportError, "high/low bounds"):
            validate_series_rows("AAPL", bad)

    def test_quality_validation_allows_only_floating_point_ohlc_bound_rounding(self):
        rows = local_rows("AAPL", ["2024-01-02"])
        rows[0]["raw_high"] = 10
        rows[0]["adjusted_high"] = 10 - 1e-14
        self.assertEqual(validate_series_rows("AAPL", rows)["row_count"], 1)
        rows[0]["adjusted_high"] = 10 - 1e-6
        with self.assertRaisesRegex(MarketDataImportError, "high/low bounds"):
            validate_series_rows("AAPL", rows)

    def test_snapshot_import_checks_hash_and_reports_benchmark_session_gaps(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            series = {
                "SPY": local_rows("SPY", ["2024-01-02", "2024-01-03", "2024-01-04"]),
                "AAPL": local_rows("AAPL", ["2024-01-02", "2024-01-04"]),
            }
            records = {}
            for ticker, rows in series.items():
                filename = f"{ticker}.csv"
                path = root / filename
                with path.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
                    writer.writeheader()
                    writer.writerows(rows)
                records[ticker] = {"file": filename, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            (root / "manifest.json").write_text(json.dumps({
                "schema_version": MARKET_SNAPSHOT_SCHEMA,
                "source": "Yahoo Finance via yfinance",
                "retrieved_at_utc": datetime.now().astimezone().isoformat(),
                "requested_start": "2024-01-02",
                "requested_end_exclusive": "2024-01-05",
                "series": records,
            }), encoding="utf-8")
            loaded = load_market_snapshot(root)
            self.assertEqual(loaded["quality_report"]["AAPL"]["benchmark_sessions_without_stock_bar"], 1)
            self.assertEqual(loaded["series"]["AAPL"][0]["close"], 10.0)
            with (root / "AAPL.csv").open("a", encoding="utf-8") as stream:
                stream.write("tamper")
            with self.assertRaisesRegex(MarketDataImportError, "SHA-256"):
                load_market_snapshot(root)


if __name__ == "__main__":
    unittest.main()
