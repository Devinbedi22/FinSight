"""Bounded multi-company price comparison using the existing market provider."""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite, sqrt
from statistics import stdev
from threading import Lock
from time import monotonic
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Mapping

from app.services.market import PRICE_HISTORY_PERIODS, get_company_price_history

BENCHMARK_TICKER = "SPY"
COMPARISON_SOURCE = "Yahoo Finance via yfinance (auto-adjusted daily OHLCV; unofficial and delayed)"
_cache_lock = Lock()
_cache: dict[tuple[tuple[str, ...], str], tuple[float, dict]] = {}
_CACHE_TTL_SECONDS = 60
_CACHE_MAX_ENTRIES = 64


def build_comparison(
    tickers: list[str], histories: Mapping[str, list[dict]], benchmark_points: list[dict], *,
    period: str, retrieved_at: str | None = None,
) -> dict:
    """Normalize selected auto-adjusted closes on common observed sessions."""
    if not 2 <= len(tickers) <= 4 or len(set(tickers)) != len(tickers):
        raise ValueError("Select 2 to 4 distinct companies.")
    if period not in PRICE_HISTORY_PERIODS - {"max"}:
        raise ValueError("Unsupported comparison period.")

    prepared: dict[str, dict[str, float]] = {}
    for ticker in tickers:
        by_date: dict[str, float] = {}
        for point in histories.get(ticker, []):
            day, close = point.get("date"), point.get("close")
            try:
                value = float(close)
            except (TypeError, ValueError):
                continue
            if isinstance(day, str) and len(day) == 10 and isfinite(value) and value > 0:
                by_date[day] = value
        prepared[ticker] = by_date

    nonempty = [set(series) for series in prepared.values() if series]
    common_dates = sorted(set.intersection(*nonempty)) if len(nonempty) == len(tickers) else []
    # A chart can show one common observation, but return/risk metrics need at
    # least two. No unobserved session is synthesized or forward-filled.
    chart: list[dict] = []
    if common_dates:
        first = common_dates[0]
        benchmark_by_date = _valid_closes(benchmark_points)
        benchmark_base_day = next((day for day in common_dates if day in benchmark_by_date), None)
        benchmark_base = benchmark_by_date.get(benchmark_base_day) if benchmark_base_day else None
        for day in common_dates:
            row = {"date": day}
            for ticker, series in prepared.items():
                row[ticker] = round(series[day] / series[first] * 100, 6)
            row[BENCHMARK_TICKER] = (
                round(benchmark_by_date[day] / benchmark_base * 100, 6)
                if benchmark_base and benchmark_base_day and day >= benchmark_base_day and day in benchmark_by_date else None
            )
            chart.append(row)

    benchmark_by_date = _valid_closes(benchmark_points)
    benchmark_common_dates = [day for day in common_dates if day in benchmark_by_date]
    observed_span_dates = set().union(*(set(series) for series in prepared.values())) if prepared else set()
    if common_dates:
        observed_span_dates = {day for day in observed_span_dates if common_dates[0] <= day <= common_dates[-1]}
    dropped_observed_sessions = max(0, len(observed_span_dates) - len(common_dates))
    result_companies = []
    for ticker, series in prepared.items():
        selected_dates = common_dates
        values = [series[day] for day in selected_dates]
        returns = [right / left - 1 for left, right in zip(values, values[1:]) if left > 0]
        cumulative = values[-1] / values[0] - 1 if len(values) >= 2 else None
        annualized_volatility = stdev(returns) * sqrt(252) if len(returns) >= 2 and dropped_observed_sessions == 0 else None
        peak = values[0] if values else None
        drawdowns = []
        for value in values:
            peak = max(peak, value) if peak is not None else value
            drawdowns.append(value / peak - 1 if peak else 0.0)
        max_drawdown = min(drawdowns) if len(values) >= 2 else None

        relative_return = None
        if len(benchmark_common_dates) >= 2:
            start, end = benchmark_common_dates[0], benchmark_common_dates[-1]
            stock_start, stock_end = series.get(start), series.get(end)
            if stock_start and stock_end:
                stock_period_return = stock_end / stock_start - 1
                benchmark_return = benchmark_by_date[end] / benchmark_by_date[start] - 1
                relative_return = stock_period_return - benchmark_return

        result_companies.append({
            "ticker": ticker,
            "status": "available" if series else "unavailable",
            "observation_count": len(series),
            "common_session_count": len(common_dates),
            "dropped_observed_sessions": dropped_observed_sessions,
            "first_common_session": common_dates[0] if common_dates else None,
            "last_common_session": common_dates[-1] if common_dates else None,
            "cumulative_return": cumulative,
            "annualized_volatility": annualized_volatility,
            "maximum_drawdown": max_drawdown,
            "benchmark_relative_return": relative_return,
            "benchmark_observation_start": benchmark_common_dates[0] if benchmark_common_dates else None,
            "benchmark_observation_end": benchmark_common_dates[-1] if benchmark_common_dates else None,
        })

    return {
        "status": "available" if len(common_dates) >= 2 else "insufficient_common_history",
        "tickers": tickers,
        "period": period,
        "chart": chart,
        "common_session_count": len(common_dates),
        "companies": result_companies,
        "benchmark": {
            "ticker": BENCHMARK_TICKER,
            "source": COMPARISON_SOURCE,
            "observation_count": len(benchmark_by_date),
            "common_session_count": len(benchmark_common_dates),
        },
        "source": COMPARISON_SOURCE,
        "adjustment": "Yahoo Finance auto_adjust=True; historical closes are adjusted OHLCV, not current quotes.",
        "methodology": {
            "normalization": "Each company adjusted close is indexed to 100 at the first session present for every selected company. SPY is independently indexed to its first available session within that common set; dates are not forward-filled.",
            "cumulative_return": "Last / first adjusted close - 1 on common company sessions.",
            "annualized_volatility": "Sample standard deviation of close-to-close returns on common company sessions × sqrt(252); unavailable with fewer than 3 closes or when observed selected-company session gaps prevent a contiguous comparison.",
            "maximum_drawdown": "Minimum close / running peak - 1 over common company sessions.",
            "benchmark_relative_return": "Company cumulative return minus SPY cumulative return on the first and last company-common sessions where SPY is also observed.",
            "coverage": "Dropped sessions count only dates observed in at least one selected company during the common-date span. Missing SPY dates do not remove company chart rows.",
        },
        "retrieved_at": retrieved_at or datetime.now(timezone.utc).isoformat(),
    }


def _valid_closes(points: list[dict]) -> dict[str, float]:
    result = {}
    for point in points:
        day = point.get("date")
        try:
            close = float(point.get("close"))
        except (TypeError, ValueError):
            continue
        if isinstance(day, str) and len(day) == 10 and isfinite(close) and close > 0:
            result[day] = close
    return result


def get_company_comparison(tickers: list[str], period: str) -> dict:
    """Fetch at most four stocks plus SPY, with a short process-local cache."""
    if period not in PRICE_HISTORY_PERIODS - {"max"}:
        raise ValueError("Unsupported comparison period.")
    cache_key = (tuple(tickers), period)
    now = monotonic()
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

    symbols = [*tickers, BENCHMARK_TICKER]
    histories: dict[str, list[dict]] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="comparison") as executor:
        futures = {executor.submit(get_company_price_history, symbol, period): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                histories[symbol] = future.result()
            except Exception:
                histories[symbol] = []
                errors[symbol] = "Price history provider is temporarily unavailable."

    result = build_comparison(
        tickers,
        {ticker: histories.get(ticker, []) for ticker in tickers},
        histories.get(BENCHMARK_TICKER, []),
        period=period,
    )
    result["provider_errors"] = errors
    if result["status"] == "available":
        with _cache_lock:
            if len(_cache) >= _CACHE_MAX_ENTRIES:
                oldest = min(_cache, key=lambda key: _cache[key][0])
                _cache.pop(oldest, None)
            _cache[cache_key] = (monotonic(), result)
    return result
