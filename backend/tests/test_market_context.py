"""Reference and point-in-time tests for market context indicators."""

import unittest
from datetime import date
from statistics import mean, stdev

from app.services.market_context import SECTOR_ETF_MAP, calculate_event_study, calculate_market_context


def bars(closes, *, offset=0, volume=1000):
    rows = []
    for index, close in enumerate(closes):
        day = date(2024, 1, 1).fromordinal(date(2024, 1, 1).toordinal() + index)
        rows.append({"date": day.isoformat(), "open": close - 0.5, "high": close + 1,
                     "low": close - 1, "close": close, "volume": volume})
    return rows


class MarketContextTest(unittest.TestCase):
    def test_indicators_match_independent_reference_values(self):
        data = bars([float(i) for i in range(1, 221)])
        result = calculate_market_context("TEST", data, as_of=date.fromisoformat(data[-1]["date"]))
        indicators = result["indicators"]
        self.assertAlmostEqual(indicators["sma_20"]["value"], sum(range(201, 221)) / 20)
        self.assertAlmostEqual(indicators["ema_12"]["value"], 214.5)
        self.assertAlmostEqual(indicators["rsi_14"]["value"], 100.0)
        self.assertAlmostEqual(indicators["momentum_20d"]["value"], 20 / 200)
        self.assertEqual(result["regime"]["label"], "uptrend")
        self.assertIsNone(result["regime"]["probability"])

    def test_as_of_cutoff_excludes_future_bars(self):
        data = bars([float(i) for i in range(1, 221)])
        cutoff = date.fromisoformat(data[199]["date"])
        result = calculate_market_context("TEST", data, as_of=cutoff)
        self.assertEqual(result["observations"], 200)
        self.assertEqual(result["latest_observation_date"], cutoff.isoformat())
        self.assertEqual(result["indicators"]["sma_200"]["value"], sum(range(1, 201)) / 200)
        self.assertLessEqual(date.fromisoformat(result["indicators"]["sma_200"]["as_of_date"]), cutoff)

    def test_insufficient_history_and_missing_values_are_explicit(self):
        data = bars([10.0, 11.0, 12.0]) + [{"date": "2024-01-04", "close": None}]
        result = calculate_market_context("TEST", data)
        self.assertEqual(result["status"], "available")
        self.assertIsNone(result["indicators"]["sma_20"]["value"])
        self.assertEqual(result["regime"]["label"], "insufficient_history")

    def test_metric_freshness_is_relative_to_as_of_cutoff(self):
        data = [{"date": "2024-01-08", "close": 10.0}]
        fresh = calculate_market_context("TEST", data, as_of=date(2024, 1, 10))
        stale = calculate_market_context("TEST", data, as_of=date(2024, 1, 20))
        self.assertEqual(fresh["indicators"]["momentum_20d"]["freshness"], "fresh")
        self.assertEqual(stale["indicators"]["momentum_20d"]["freshness"], "stale")
        unavailable = stale["indicators"]["sma_20"]
        self.assertEqual(unavailable["freshness"], "stale")

    def test_benchmark_uses_common_sessions_and_adjusted_return_difference(self):
        stock = bars([float(i) for i in range(100, 130)])
        benchmark = bars([float(i) for i in range(200, 230)])
        result = calculate_market_context("TEST", stock, benchmark)
        relative = result["indicators"]["relative_return_20d_vs_sp500"]["value"]
        expected = (129 / 109 - 1) - (229 / 209 - 1)
        self.assertAlmostEqual(relative, expected)
        self.assertIsNotNone(result["indicators"]["correlation_20d_vs_sp500"]["value"])

    def test_documented_sector_etf_proxy_is_used_without_claiming_sector_index(self):
        stock = bars([float(i) for i in range(100, 130)])
        sector = bars([float(i) for i in range(200, 230)])
        result = calculate_market_context("TEST", stock, sector= "Financials", sector_points=sector)
        self.assertEqual(SECTOR_ETF_MAP["Financials"], "XLF")
        self.assertEqual(result["sector_benchmark"]["ticker"], "XLF")
        self.assertIn("not a sector index", result["sector_benchmark"]["proxy_limitations"])
        self.assertAlmostEqual(result["indicators"]["relative_return_20d_vs_sector"]["value"], (129 / 109 - 1) - (229 / 209 - 1))

    def test_adjusted_ohlc_drives_atr(self):
        data = bars([float(i) for i in range(1, 20)])
        result = calculate_market_context("TEST", data)
        self.assertAlmostEqual(result["indicators"]["atr_14"]["value"], 2.0)

    def test_macd_bollinger_volatility_and_volume_match_reference_calculations(self):
        data = bars([100 + i * 0.4 + (i % 7) * 0.8 for i in range(260)])
        data[-1]["volume"] = 3000
        closes = [bar["close"] for bar in data]
        def reference_ema(values, window):
            result = mean(values[:window])
            alpha = 2 / (window + 1)
            output = [None] * (window - 1) + [result]
            for value in values[window:]:
                result = value * alpha + result * (1 - alpha)
                output.append(result)
            return output

        fast, slow = reference_ema(closes, 12), reference_ema(closes, 26)
        macd = [left - right for left, right in zip(fast, slow) if left is not None and right is not None]
        signal = reference_ema(macd, 9)[-1]
        return_series = [right / left - 1 for left, right in zip(closes[-21:-1], closes[-20:])]
        result = calculate_market_context("TEST", data)
        indicators = result["indicators"]
        self.assertAlmostEqual(indicators["macd"]["value"], macd[-1])
        self.assertAlmostEqual(indicators["macd_signal"]["value"], signal)
        self.assertAlmostEqual(indicators["macd_histogram"]["value"], macd[-1] - signal)
        self.assertAlmostEqual(indicators["bollinger_middle"]["value"], mean(closes[-20:]))
        self.assertAlmostEqual(indicators["bollinger_upper"]["value"], mean(closes[-20:]) + 2 * stdev(closes[-20:]))
        self.assertAlmostEqual(indicators["bollinger_lower"]["value"], mean(closes[-20:]) - 2 * stdev(closes[-20:]))
        self.assertAlmostEqual(indicators["historical_volatility_20d"]["value"], stdev(return_series) * (252 ** 0.5))
        expected_volume_ratio = 3000 / mean([1000] * 19 + [3000])
        self.assertAlmostEqual(indicators["volume_vs_20d_average"]["value"], expected_volume_ratio)
        self.assertTrue(indicators["volume_anomaly"]["value"])

    def test_event_study_aligns_premarket_and_intraday_without_lookahead(self):
        stock = [
            {"date": day, "close": close}
            for day, close in (("2024-01-08", 100), ("2024-01-09", 102), ("2024-01-10", 105), ("2024-01-11", 106), ("2024-01-15", 108))
        ]
        benchmark = [
            {"date": day, "close": close}
            for day, close in (("2024-01-08", 200), ("2024-01-09", 202), ("2024-01-10", 204), ("2024-01-11", 206), ("2024-01-15", 208))
        ]
        events = [
            {"article_id": 1, "published_at": "2024-01-08T13:00:00Z", "event_type": "earnings"},  # 08:00 ET
            {"article_id": 2, "published_at": "2024-01-08T15:00:00Z", "event_type": "guidance"},  # 10:00 ET
            {"article_id": 3, "published_at": "2024-01-08T22:00:00Z", "event_type": "after_hours"},  # 17:00 ET
            {"article_id": 4, "published_at": "2024-01-13T15:00:00Z", "event_type": "weekend"},  # Saturday
            {"article_id": 5, "published_at": "2024-01-12T15:00:00Z", "event_type": "holiday_gap"},  # weekday with no bar
        ]
        result = calculate_event_study(events, stock, benchmark, horizons=(1,), as_of=date(2024, 1, 16))
        self.assertEqual(result["events"][0]["aligned_session"], "2024-01-08")
        self.assertEqual(result["events"][0]["publication_period_et"], "premarket")
        self.assertEqual(result["events"][1]["publication_period_et"], "intraday")
        self.assertEqual(result["events"][2]["publication_period_et"], "after_hours")
        self.assertEqual(result["events"][2]["aligned_session"], "2024-01-09")
        self.assertEqual(result["events"][3]["publication_period_et"], "weekend")
        self.assertEqual(result["events"][3]["aligned_session"], "2024-01-15")
        self.assertEqual(result["events"][4]["publication_period_et"], "market_holiday_or_no_trading_bar")
        self.assertAlmostEqual(result["events"][0]["returns"]["1_session"]["stock_return"], 0.02)
        self.assertTrue(result["events"][0]["overlaps_nearby_event"])
        self.assertFalse(any("causal" in item.lower() for item in result["method"].split()))

    def test_event_study_drops_events_after_as_of(self):
        result = calculate_event_study(
            [{"article_id": 3, "published_at": "2024-01-09T15:00:00Z"}],
            [{"date": "2024-01-08", "close": 100}], [], as_of=date(2024, 1, 8),
        )
        self.assertEqual(result["event_count"], 0)


if __name__ == "__main__":
    unittest.main()
