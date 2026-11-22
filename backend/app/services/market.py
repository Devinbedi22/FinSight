"""Company directory and latest available market values for the POC."""

from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import logging
from math import isfinite
from threading import Lock
from time import monotonic

import yfinance as yf

from app.services.universe import get_sp500_universe, get_sp500_universe_metadata

_quote_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quotes")
_quote_lock = Lock()
_quote_cache: dict[str, dict] = {}
_quote_cache_time: dict[str, float] = {}
_quote_refreshing: set[tuple[str, ...]] = set()
_QUOTE_CACHE_TTL_SECONDS = 180
logger = logging.getLogger(__name__)


def _refresh_quotes(symbols: tuple[str, ...]) -> None:
    try:
        raw = yf.download(
            tickers=" ".join(symbols), period="5d", interval="1d", group_by="ticker",
            auto_adjust=True, progress=False, threads=True, timeout=12,
        )
        updated = {}
        for symbol in symbols:
            try:
                history = raw[symbol].dropna(subset=["Close"])
                latest = float(history["Close"].iloc[-1])
                previous = float(history["Close"].iloc[-2]) if len(history) > 1 else None
                updated[symbol] = {
                    "price": latest,
                    "previous_close": previous,
                    "change_percent": latest / previous - 1 if previous else None,
                    "quote_time": history.index[-1].to_pydatetime().isoformat(),
                    "quote_status": "available",
                    "quote_error": None,
                }
            except (KeyError, IndexError, TypeError, ValueError):
                updated[symbol] = {"price": None, "previous_close": None, "change_percent": None,
                                   "quote_time": None, "quote_status": "unavailable",
                                   "quote_error": "No recent daily quote was returned by Yahoo Finance."}
        with _quote_lock:
            _quote_cache.update(updated)
            now = monotonic()
            _quote_cache_time.update({symbol: now for symbol in symbols})
    except Exception as exc:
        logger.warning("Yahoo Finance quote batch unavailable (%s)", type(exc).__name__)
        with _quote_lock:
            now = monotonic()
            for symbol in symbols:
                _quote_cache[symbol] = {
                    "price": None, "previous_close": None, "change_percent": None,
                    "quote_time": None, "quote_status": "unavailable",
                    "quote_error": "Yahoo Finance is temporarily unavailable; retry is bounded by the quote cache interval.",
                }
                _quote_cache_time[symbol] = now
    finally:
        with _quote_lock:
            _quote_refreshing.discard(symbols)


def get_company_market_rows(
    limit: int = 100, offset: int = 0, search: str | None = None, *, include_quotes: bool = True,
) -> dict:
    companies = get_sp500_universe()
    directory = get_sp500_universe_metadata()
    if search and search.strip():
        needle = search.strip().casefold()
        companies = [
            company for company in companies
            if needle in " ".join((company["ticker"], company["name"], company["sector"])).casefold()
        ]
    page = companies[offset : offset + limit]
    symbols = [row["ticker"].replace(".", "-") for row in page]
    if not symbols:
        return {"total": len(companies), "offset": offset, "count": 0, "source": "Company directory", "directory": directory, "retrieved_at": datetime.now(timezone.utc).isoformat(), "companies": []}
    batch_key = tuple(symbols)
    if include_quotes:
        with _quote_lock:
            if batch_key not in _quote_refreshing and any(
                symbol not in _quote_cache
                or monotonic() - _quote_cache_time.get(symbol, 0) >= _QUOTE_CACHE_TTL_SECONDS
                for symbol in symbols
            ):
                _quote_refreshing.add(batch_key)
                _quote_executor.submit(_refresh_quotes, batch_key)
    results = []
    if include_quotes:
        with _quote_lock:
            cached_quotes = {symbol: _quote_cache.get(symbol) for symbol in symbols}
            batch_pending = batch_key in _quote_refreshing
    else:
        cached_quotes = {}
        batch_pending = False
    for company, symbol in zip(page, symbols):
        quote = (cached_quotes.get(symbol) or {
            "price": None, "previous_close": None, "change_percent": None,
            "quote_time": None, "quote_status": "pending" if batch_pending else "unavailable",
        }) if include_quotes else {
            "price": None, "previous_close": None, "change_percent": None,
            "quote_time": None, "quote_status": "not_requested",
        }
        results.append({
            **company,
            **quote,
        })
    quote_status = (
        "not_requested" if not include_quotes else
        "pending" if batch_pending else
        "available" if any((quote or {}).get("quote_status") == "available" for quote in cached_quotes.values()) else
        "unavailable"
    )
    source = (
        "S&P 500 constituent directory (quotes not requested)" if not include_quotes else
        "Yahoo Finance via yfinance (delayed/unofficial; latest available daily close)" if quote_status == "available" else
        "Yahoo Finance quote request pending" if quote_status == "pending" else
        "Yahoo Finance quotes unavailable; company directory loaded independently"
    )
    return {
        "total": len(companies),
        "offset": offset,
        "count": len(results),
        "source": source,
        "directory": directory,
        "quotes_status": quote_status,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "companies": results,
    }


def get_company_market_row(ticker: str) -> dict | None:
    company = next((row for row in get_sp500_universe() if row["ticker"].upper() == ticker.upper()), None)
    if company is None:
        return None
    symbol = ticker.upper().replace(".", "-")
    quote_error = None
    try:
        history = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=True, timeout=8)
        history = history.dropna(subset=["Close"])
        latest = float(history["Close"].iloc[-1]) if len(history) else None
        previous = float(history["Close"].iloc[-2]) if len(history) > 1 else None
        quote_time = history.index[-1].to_pydatetime().isoformat() if len(history) else None
        if latest is None:
            quote_error = "Yahoo Finance returned no recent daily quote."
    except Exception as exc:
        latest = previous = quote_time = None
        quote_error = "Yahoo Finance is temporarily unavailable."
        logger.warning(
            "Yahoo Finance company quote unavailable ticker=%s error_type=%s", ticker.upper(), type(exc).__name__
        )
    return {
        **company,
        "price": latest,
        "previous_close": previous,
        "change_percent": latest / previous - 1 if latest is not None and previous else None,
        "quote_time": quote_time,
        "quote_status": "available" if latest is not None else "unavailable",
        "quote_error": quote_error,
        "source": "Yahoo Finance via yfinance (delayed/unofficial; latest available daily close)",
        "directory": get_sp500_universe_metadata(),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


PRICE_HISTORY_PERIODS = {"1mo", "3mo", "6mo", "1y", "5y", "max"}


def _optional_number(value):
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def get_company_price_history(ticker: str, period: str = "1y") -> list[dict]:
    """Return observed daily adjusted OHLCV bars for a company chart."""
    if period not in PRICE_HISTORY_PERIODS:
        raise ValueError(f"Unsupported history period: {period}")
    symbol = ticker.upper().replace(".", "-")
    history = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
    history = history.dropna(subset=["Close"])
    points = []
    for index, row in history.iterrows():
        volume = _optional_number(row.get("Volume"))
        points.append({
            "date": index.date().isoformat(),
            "open": _optional_number(row.get("Open")),
            "high": _optional_number(row.get("High")),
            "low": _optional_number(row.get("Low")),
            "close": float(row["Close"]),
            "volume": int(volume) if volume is not None else None,
        })
    return points


def get_company_price_on_or_before(ticker: str, as_of: date) -> tuple[float | None, str | None]:
    """Return the latest adjusted daily close dated no later than ``as_of``."""
    start = (as_of - timedelta(days=10)).isoformat()
    end = (as_of + timedelta(days=1)).isoformat()
    symbol = ticker.upper().replace(".", "-")
    history = yf.Ticker(symbol).history(start=start, end=end, interval="1d", auto_adjust=True)
    if history.empty:
        return None, None
    eligible = [(index, row) for index, row in history.iterrows() if index.date() <= as_of]
    if not eligible:
        return None, None
    index, row = eligible[-1]
    return float(row["Close"]), index.date().isoformat()
