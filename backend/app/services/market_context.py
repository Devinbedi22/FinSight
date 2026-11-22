"""Point-in-time technical and benchmark context from adjusted daily bars."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from math import sqrt
from statistics import mean, stdev
from typing import Iterable
from zoneinfo import ZoneInfo

from app.services.market import get_company_price_history
from app.services.universe import get_sp500_universe

TRADING_DAYS = 252
BENCHMARK_TICKER = "^GSPC"
BENCHMARK_SOURCE = "Yahoo Finance via yfinance (S&P 500 index proxy; daily adjusted bars)"
SECTOR_ETF_MAP = {
    "Communication Services": "XLC", "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP", "Energy": "XLE", "Financials": "XLF",
    "Health Care": "XLV", "Industrials": "XLI", "Information Technology": "XLK",
    "Materials": "XLB", "Real Estate": "XLRE", "Utilities": "XLU",
}


def _metric(value, unit, source, observation_date, as_of, method, *, period=None, freshness="current"):
    if observation_date:
        try:
            age_days = (date.fromisoformat(as_of) - date.fromisoformat(observation_date)).days
            freshness = "fresh" if 0 <= age_days <= 4 else "stale"
        except (TypeError, ValueError):
            freshness = "unknown"
    else:
        freshness = "unavailable"
    return {
        "value": value, "unit": unit, "source": source,
        "observation_date": observation_date, "available_at": None,
        "reporting_period": period, "as_of_date": as_of,
        "freshness": freshness, "methodology": method,
    }


def _mean(values: list[float], window: int) -> float | None:
    return mean(values[-window:]) if len(values) >= window else None


def _ema(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    result = mean(values[:window])
    alpha = 2 / (window + 1)
    for value in values[window:]:
        result = value * alpha + result * (1 - alpha)
    return result


def _ema_series(values: list[float], window: int) -> list[float | None]:
    if len(values) < window:
        return [None] * len(values)
    output: list[float | None] = [None] * (window - 1)
    result = mean(values[:window])
    output.append(result)
    alpha = 2 / (window + 1)
    for value in values[window:]:
        result = value * alpha + result * (1 - alpha)
        output.append(result)
    return output


def _sample_std(values: list[float]) -> float | None:
    return stdev(values) if len(values) >= 2 else None


def _returns(closes: list[float], window: int | None = None) -> list[float]:
    values = [current / previous - 1 for previous, current in zip(closes, closes[1:]) if previous]
    return values[-window:] if window else values


def _rsi(closes: list[float], window: int = 14) -> float | None:
    if len(closes) < window + 1:
        return None
    changes = [right - left for left, right in zip(closes, closes[1:])]
    gains = [max(change, 0) for change in changes]
    losses = [max(-change, 0) for change in changes]
    avg_gain, avg_loss = mean(gains[:window]), mean(losses[:window])
    for gain, loss in zip(gains[window:], losses[window:]):
        avg_gain = (avg_gain * (window - 1) + gain) / window
        avg_loss = (avg_loss * (window - 1) + loss) / window
    if avg_loss == 0:
        return 100.0 if avg_gain else 50.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def _regime(close: float, sma50: float | None, sma200: float | None, annual_vol: float | None) -> dict:
    if annual_vol is not None and annual_vol >= 0.35:
        label, criteria = "high_volatility", "annualized 20-session close-to-close volatility >= 35%"
    elif sma50 is not None and sma200 is not None and close > sma50 > sma200:
        label, criteria = "uptrend", "latest close > SMA 50 > SMA 200"
    elif sma50 is not None and sma200 is not None and close < sma50 < sma200:
        label, criteria = "downtrend", "latest close < SMA 50 < SMA 200"
    elif annual_vol is not None and annual_vol < 0.10:
        label, criteria = "low_volatility", "annualized 20-session close-to-close volatility < 10%"
    elif sma50 is not None and sma200 is not None:
        label, criteria = "sideways", "neither ordered uptrend nor ordered downtrend criteria hold"
    else:
        label, criteria = "insufficient_history", "SMA 50 and SMA 200 are required for trend classification"
    return {"label": label, "criteria": criteria, "probability": None}


def calculate_market_context(
    ticker: str,
    points: Iterable[dict],
    benchmark_points: Iterable[dict] = (),
    *, as_of: date | None = None, sector: str | None = None, sector_points: Iterable[dict] = (),
    benchmark_ticker: str = BENCHMARK_TICKER, benchmark_source: str | None = None,
) -> dict:
    """Calculate indicators using only observed bars dated on/before as_of.

    Prices are expected to be auto-adjusted daily bars. Volatility and return
    windows are close-to-close; ATR uses adjusted OHLC ranges.
    """
    cutoff = as_of or date.today()
    stock = sorted((p for p in points if p.get("date") and date.fromisoformat(p["date"]) <= cutoff), key=lambda p: p["date"])
    benchmark = sorted((p for p in benchmark_points if p.get("date") and date.fromisoformat(p["date"]) <= cutoff), key=lambda p: p["date"])
    sector_bars = sorted((p for p in sector_points if p.get("date") and date.fromisoformat(p["date"]) <= cutoff), key=lambda p: p["date"])
    closes = [float(p["close"]) for p in stock if p.get("close") is not None]
    stock = [p for p in stock if p.get("close") is not None]
    dates = [p["date"] for p in stock]
    latest_date = dates[-1] if dates else None
    latest = closes[-1] if closes else None
    source = "Yahoo Finance via yfinance (unofficial adjusted daily OHLCV)"

    values: dict[str, dict] = {}
    for window in (20, 50, 200):
        value = _mean(closes, window)
        values[f"sma_{window}"] = _metric(value, "USD", source, latest_date, cutoff.isoformat(), f"Arithmetic mean of last {window} adjusted daily closes", period=f"{window} trading sessions")
    for window in (12, 26, 50):
        value = _ema(closes, window)
        values[f"ema_{window}"] = _metric(value, "USD", source, latest_date, cutoff.isoformat(), f"EMA over adjusted closes; alpha=2/({window}+1), seeded by first {window}-session mean", period=f"{window} trading sessions")

    rsi = _rsi(closes)
    values["rsi_14"] = _metric(rsi, "index_0_100", source, latest_date, cutoff.isoformat(), "Wilder-smoothed 14-session gains and losses")
    macd_line = None
    signal = histogram = None
    if len(closes) >= 34:
        fast, slow = _ema_series(closes, 12), _ema_series(closes, 26)
        macd_values = [a - b for a, b in zip(fast, slow) if a is not None and b is not None]
        macd_line = macd_values[-1]
        signal = _ema(macd_values, 9)
        histogram = macd_line - signal if signal is not None else None
    values["macd"] = _metric(macd_line, "USD", source, latest_date, cutoff.isoformat(), "EMA(12) minus EMA(26); signal is EMA(9) of MACD", period="12/26/9 sessions")
    values["macd_signal"] = _metric(signal, "USD", source, latest_date, cutoff.isoformat(), "EMA(9) of MACD line", period="9 MACD observations")
    values["macd_histogram"] = _metric(histogram, "USD", source, latest_date, cutoff.isoformat(), "MACD line minus signal line")

    middle = _mean(closes, 20)
    deviation = _sample_std(closes[-20:]) if len(closes) >= 20 else None
    values["bollinger_lower"] = _metric(middle - 2 * deviation if middle is not None and deviation is not None else None, "USD", source, latest_date, cutoff.isoformat(), "20-session SMA minus 2 sample standard deviations")
    values["bollinger_middle"] = _metric(middle, "USD", source, latest_date, cutoff.isoformat(), "20-session SMA")
    values["bollinger_upper"] = _metric(middle + 2 * deviation if middle is not None and deviation is not None else None, "USD", source, latest_date, cutoff.isoformat(), "20-session SMA plus 2 sample standard deviations")

    atr = None
    if len(stock) >= 15:
        ranges = []
        for previous, bar in zip(stock, stock[1:]):
            high, low, prior_close = bar.get("high"), bar.get("low"), previous.get("close")
            if high is not None and low is not None:
                ranges.append(max(float(high) - float(low), abs(float(high) - float(prior_close)), abs(float(low) - float(prior_close))))
        if len(ranges) >= 14:
            atr = mean(ranges[:14])
            for value in ranges[14:]:
                atr = (atr * 13 + value) / 14
    values["atr_14"] = _metric(atr, "USD", source, latest_date, cutoff.isoformat(), "Wilder-smoothed true range using adjusted OHLC")
    returns20, returns252 = _returns(closes, 20), _returns(closes, 252)
    daily_vol = _sample_std(returns20) if len(returns20) >= 2 else None
    values["historical_volatility_20d"] = _metric(daily_vol * sqrt(TRADING_DAYS) if daily_vol is not None else None, "annualized_ratio", source, latest_date, cutoff.isoformat(), "Sample standard deviation of latest 20 daily close returns × sqrt(252)", period="20 trading sessions")

    volumes = [float(p["volume"]) for p in stock if p.get("volume") is not None]
    volume_mean = mean(volumes[-20:]) if len(volumes) >= 20 else None
    volume_ratio = volumes[-1] / volume_mean if volumes and volume_mean else None
    values["volume_vs_20d_average"] = _metric(volume_ratio, "multiple", source, latest_date, cutoff.isoformat(), "Latest volume divided by trailing 20-session mean volume", period="20 trading sessions")
    values["volume_anomaly"] = _metric(volume_ratio >= 2.0 if volume_ratio is not None else None, "boolean", source, latest_date, cutoff.isoformat(), "Flag when latest volume is at least 2.0× trailing 20-session mean; heuristic threshold, not a significance test", period="20 trading sessions")
    values["momentum_20d"] = _metric(closes[-1] / closes[-21] - 1 if len(closes) >= 21 else None, "ratio", source, latest_date, cutoff.isoformat(), "Latest adjusted close / close 20 sessions earlier - 1", period="20 trading sessions")
    values["momentum_252d"] = _metric(closes[-1] / closes[-253] - 1 if len(closes) >= 253 else None, "ratio", source, latest_date, cutoff.isoformat(), "Latest adjusted close / close 252 sessions earlier - 1", period="252 trading sessions")

    benchmark_by_date = {p["date"]: float(p["close"]) for p in benchmark if p.get("close") is not None}
    shared = [(p["date"], float(p["close"]), benchmark_by_date[p["date"]]) for p in stock if p["date"] in benchmark_by_date]
    relative = None
    correlation = None
    rolling_vol_relative = None
    if len(shared) >= 21:
        s0, b0 = shared[-21][1], shared[-21][2]
        relative = (shared[-1][1] / s0 - 1) - (shared[-1][2] / b0 - 1)
        stock_ret = _returns([item[1] for item in shared], 20)
        bench_ret = _returns([item[2] for item in shared], 20)
        if len(stock_ret) >= 2:
            from statistics import correlation as _correlation
            correlation = _correlation(stock_ret, bench_ret)
            stock_sd, bench_sd = _sample_std(stock_ret), _sample_std(bench_ret)
            rolling_vol_relative = (stock_sd / bench_sd) if stock_sd is not None and bench_sd else None
    selected_benchmark_source = benchmark_source or f"Yahoo Finance via yfinance ({benchmark_ticker} adjusted daily benchmark proxy)"
    values["relative_return_20d_vs_sp500"] = _metric(relative, "percentage_points", selected_benchmark_source, shared[-1][0] if shared else None, cutoff.isoformat(), "Stock 20-session return minus S&P 500 proxy return on common observed sessions", period="20 trading sessions")
    values["correlation_20d_vs_sp500"] = _metric(correlation, "correlation_-1_1", selected_benchmark_source, shared[-1][0] if shared else None, cutoff.isoformat(), "Pearson correlation of daily returns on latest 20 common sessions", period="20 trading sessions")
    values["relative_volatility_20d_vs_sp500"] = _metric(rolling_vol_relative, "multiple", selected_benchmark_source, shared[-1][0] if shared else None, cutoff.isoformat(), "Stock return standard deviation / S&P 500 proxy return standard deviation", period="20 trading sessions")
    sector_ticker = SECTOR_ETF_MAP.get(sector or "")
    sector_by_date = {p["date"]: float(p["close"]) for p in sector_bars if p.get("close") is not None}
    sector_shared = [(p["date"], float(p["close"]), sector_by_date[p["date"]]) for p in stock if p["date"] in sector_by_date]
    sector_relative = sector_vol_relative = None
    if len(sector_shared) >= 21:
        sector_relative = (sector_shared[-1][1] / sector_shared[-21][1] - 1) - (sector_shared[-1][2] / sector_shared[-21][2] - 1)
        stock_sector_returns = _returns([item[1] for item in sector_shared], 20)
        etf_returns = _returns([item[2] for item in sector_shared], 20)
        stock_sd, etf_sd = _sample_std(stock_sector_returns), _sample_std(etf_returns)
        sector_vol_relative = stock_sd / etf_sd if stock_sd is not None and etf_sd else None
    sector_source = f"Yahoo Finance via yfinance ({sector_ticker} SPDR Select Sector ETF proxy)" if sector_ticker else "Unavailable: no documented sector proxy mapping"
    values["relative_return_20d_vs_sector"] = _metric(sector_relative, "percentage_points", sector_source, sector_shared[-1][0] if sector_shared else None, cutoff.isoformat(), "Stock 20-session return minus mapped sector ETF proxy return on common sessions", period="20 trading sessions")
    values["relative_volatility_20d_vs_sector"] = _metric(sector_vol_relative, "multiple", sector_source, sector_shared[-1][0] if sector_shared else None, cutoff.isoformat(), "Stock return standard deviation / mapped sector ETF proxy return standard deviation", period="20 trading sessions")
    regime = _regime(latest, values["sma_50"]["value"], values["sma_200"]["value"], values["historical_volatility_20d"]["value"])
    return {
        "ticker": ticker.upper(), "sector": sector, "as_of_date": cutoff.isoformat(),
        "status": "available" if latest is not None else "insufficient_history",
        "freshness_rule": "Fresh when latest observation is 0–4 calendar days before as_of_date; otherwise stale. No observation is unavailable.",
        "latest_observation_date": latest_date, "observations": len(stock),
        "price_adjustment": "auto_adjusted", "source": source,
        "benchmark": {"ticker": benchmark_ticker, "name": "S&P 500 proxy", "source": selected_benchmark_source, "proxy_limitations": "Benchmark proxy returns depend on the supplied instrument. An adjusted ETF series includes its provider adjustment, tracking effects, and fees; an index series may be price-only."},
        "sector_benchmark": {"ticker": sector_ticker, "name": f"SPDR Select Sector ETF {sector_ticker}" if sector_ticker else None, "proxy_limitations": "ETF proxy for a GICS sector; includes fund fees/tracking effects and is not a sector index." if sector_ticker else "No reliable sector mapping available."},
        "indicators": values, "regime": regime,
        "limitations": ["Metrics are descriptive and do not predict returns.", "Unavailable metrics remain null when history is insufficient.", "Yahoo Finance via yfinance is unofficial; adjusted daily bars may be revised for corporate actions.", "Sector-relative return is omitted because no reliable sector index source is configured."],
    }


def get_company_market_context(ticker: str, as_of: date | None = None) -> dict:
    universe_row = next((row for row in get_sp500_universe() if row["ticker"].upper() == ticker.upper()), None)
    if universe_row is None:
        raise ValueError("Ticker is not an S&P 500 constituent")
    cutoff = as_of or date.today()
    # Pull a long bounded history so 252-session measures are available where data supports them.
    history = get_company_price_history(ticker, period="max")
    benchmark = get_company_price_history(BENCHMARK_TICKER, period="max")
    sector_ticker = SECTOR_ETF_MAP.get(universe_row.get("sector", ""))
    sector_points = get_company_price_history(sector_ticker, period="max") if sector_ticker else []
    result = calculate_market_context(ticker, history, benchmark, as_of=cutoff, sector=universe_row.get("sector"), sector_points=sector_points)
    return result


def calculate_event_study(events: Iterable[dict], stock_points: Iterable[dict], benchmark_points: Iterable[dict], *, horizons=(1, 5, 20), as_of: date | None = None) -> dict:
    """Descriptive post-publication close returns; excludes the publication session unless premarket."""
    cutoff = as_of or date.today()
    stock = sorted((p for p in stock_points if p.get("close") is not None and date.fromisoformat(p["date"]) <= cutoff), key=lambda p: p["date"])
    benchmark = {p["date"]: float(p["close"]) for p in benchmark_points if p.get("close") is not None and date.fromisoformat(p["date"]) <= cutoff}
    sessions = [p["date"] for p in stock]
    stock_close = {p["date"]: float(p["close"]) for p in stock}
    prepared = []
    ny = ZoneInfo("America/New_York")
    for event in events:
        published = event.get("published_at")
        if not published:
            continue
        try:
            timestamp = datetime.fromisoformat(published.replace("Z", "+00:00"))
            timestamp = timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp
            local = timestamp.astimezone(ny)
        except (ValueError, TypeError):
            continue
        if local.date() > cutoff:
            continue
        eligible_day = local.date()
        is_session = local.date().isoformat() in sessions
        if local.weekday() >= 5:
            publication_period = "weekend"
        elif not is_session:
            publication_period = "market_holiday_or_no_trading_bar"
        elif local.time() < time(9, 30):
            publication_period = "premarket"
        elif local.time() < time(16, 0):
            publication_period = "intraday"
        else:
            publication_period = "after_hours"
        # Premarket stories can use that session close; all other events start
        # at the next available close so same-session moves are excluded.
        if publication_period != "premarket":
            eligible_day = date.fromordinal(eligible_day.toordinal() + 1)
        session_index = next((i for i, day in enumerate(sessions) if date.fromisoformat(day) >= eligible_day), None)
        prepared.append((event, local, publication_period, session_index))

    rows = []
    for event, local, publication_period, index in prepared:
        aligned = sessions[index] if index is not None else None
        returns = {}
        if index is not None:
            for horizon in horizons:
                target = index + int(horizon)
                if target < len(sessions):
                    start_date, end_date = sessions[index], sessions[target]
                    stock_return = stock_close[end_date] / stock_close[start_date] - 1
                    benchmark_return = (benchmark[end_date] / benchmark[start_date] - 1) if start_date in benchmark and end_date in benchmark else None
                    returns[f"{horizon}_session"] = {
                        "stock_return": stock_return,
                        "benchmark_return": benchmark_return,
                        "excess_return": stock_return - benchmark_return if benchmark_return is not None else None,
                        "start_date": start_date, "end_date": end_date,
                    }
                else:
                    returns[f"{horizon}_session"] = None
        rows.append({
            "article_id": event.get("article_id"), "title": event.get("title"),
            "event_type": event.get("event_type"), "source": event.get("source"),
            "published_at": event.get("published_at"), "publication_time_et": local.isoformat(),
            "publication_period_et": publication_period,
            "aligned_session": aligned, "alignment_rule": "Premarket on a trading day: same trading session close; intraday, after-hours, weekend, or market holiday: next available trading session close.",
            "overlaps_nearby_event": False, "returns": returns,
        })
    for i, row in enumerate(rows):
        if row["aligned_session"]:
            event_date = date.fromisoformat(row["aligned_session"])
            row["overlaps_nearby_event"] = any(
                i != j and other["aligned_session"] and abs((date.fromisoformat(other["aligned_session"]) - event_date).days) <= 2
                for j, other in enumerate(rows)
            )
    return {
        "as_of_date": cutoff.isoformat(), "method": "Descriptive close-to-close association; event starts at conservatively aligned session close.",
        "benchmark": {"ticker": BENCHMARK_TICKER, "name": "S&P 500 Index", "source": BENCHMARK_SOURCE},
        "horizons_trading_sessions": list(horizons), "event_count": len(rows), "events": rows,
        "limitations": ["Historical association does not establish causation or predictive value.", "Duplicate and nearby events are flagged but not statistically deconfounded.", "Daily source timestamps do not identify the exact exchange dissemination time; alignment is conservative by publication timestamp.", "Returns are unavailable when a horizon or benchmark close is missing."],
    }


def get_company_event_study(ticker: str, events: Iterable[dict], as_of: date | None = None) -> dict:
    cutoff = as_of or date.today()
    stock = get_company_price_history(ticker, period="max")
    benchmark = get_company_price_history(BENCHMARK_TICKER, period="max")
    return calculate_event_study(events, stock, benchmark, as_of=cutoff)
