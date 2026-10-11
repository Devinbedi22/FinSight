"""Company directory and latest available market values for the POC."""

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import yfinance as yf

from app.services.universe import get_sp500_universe

_quote_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quotes")
_quote_lock = Lock()
_quote_cache: dict[str, dict] = {}
_quote_refreshing: set[tuple[str, ...]] = set()


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
                }
            except (KeyError, IndexError, TypeError, ValueError):
                updated[symbol] = {"price": None, "previous_close": None, "change_percent": None,
                                   "quote_time": None, "quote_status": "unavailable"}
        with _quote_lock:
            _quote_cache.update(updated)
    except Exception:
        pass
    finally:
        with _quote_lock:
            _quote_refreshing.discard(symbols)


def get_company_market_rows(limit: int = 100, offset: int = 0) -> dict:
    companies = get_sp500_universe()
    page = companies[offset : offset + limit]
    symbols = [row["ticker"].replace(".", "-") for row in page]
    if not symbols:
        return {"total": len(companies), "offset": offset, "count": 0, "source": "Yahoo Finance via yfinance", "retrieved_at": datetime.now(timezone.utc).isoformat(), "companies": []}
    batch_key = tuple(symbols)
    with _quote_lock:
        if batch_key not in _quote_refreshing and any(symbol not in _quote_cache for symbol in symbols):
            _quote_refreshing.add(batch_key)
            _quote_executor.submit(_refresh_quotes, batch_key)
    results = []
    with _quote_lock:
        cached_quotes = {symbol: _quote_cache.get(symbol) for symbol in symbols}
        batch_pending = batch_key in _quote_refreshing
    for company, symbol in zip(page, symbols):
        quote = cached_quotes[symbol] or {
            "price": None, "previous_close": None, "change_percent": None,
            "quote_time": None, "quote_status": "pending" if batch_pending else "unavailable",
        }
        results.append({
            **company,
            **quote,
        })
    return {
        "total": len(companies),
        "offset": offset,
        "count": len(results),
        "source": "Yahoo Finance via yfinance (delayed/unofficial; latest available daily close)",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "companies": results,
    }


def get_company_market_row(ticker: str) -> dict | None:
    company = next((row for row in get_sp500_universe() if row["ticker"].upper() == ticker.upper()), None)
    if company is None:
        return None
    symbol = ticker.upper().replace(".", "-")
    history = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=True)
    history = history.dropna(subset=["Close"])
    latest = float(history["Close"].iloc[-1]) if len(history) else None
    previous = float(history["Close"].iloc[-2]) if len(history) > 1 else None
    quote_time = history.index[-1].to_pydatetime().isoformat() if len(history) else None
    return {
        **company,
        "price": latest,
        "previous_close": previous,
        "change_percent": latest / previous - 1 if latest is not None and previous else None,
        "quote_time": quote_time,
        "quote_status": "available" if latest is not None else "unavailable",
        "source": "Yahoo Finance via yfinance (delayed/unofficial; latest available daily close)",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def get_company_price_history(ticker: str, period: str = "1y") -> list[dict]:
    """Return observed daily adjusted closes for a company chart."""
    symbol = ticker.upper().replace(".", "-")
    history = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
    history = history.dropna(subset=["Close"])
    return [
        {"date": index.date().isoformat(), "close": float(row["Close"])}
        for index, row in history.iterrows()
    ]
