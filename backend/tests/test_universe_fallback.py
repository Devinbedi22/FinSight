from unittest.mock import patch

import httpx

from app.services import universe
from app.services.market import get_company_market_rows


def setup_function():
    universe._load_sp500_directory.cache_clear()


def teardown_function():
    universe._load_sp500_directory.cache_clear()


def test_directory_falls_back_to_dated_local_research_symbols_when_provider_socket_fails():
    with patch("app.services.universe.httpx.get", side_effect=httpx.ConnectError("socket denied")):
        rows = universe.get_sp500_universe()
        metadata = universe.get_sp500_universe_metadata()

    assert {row["ticker"] for row in rows} == {"AAPL", "MSFT", "NVDA", "AMZN", "TSLA"}
    assert {"Apple", "Microsoft", "NVIDIA", "Amazon", "Tesla"} == {row["name"] for row in rows}
    assert metadata["status"] == "stale_limited_fallback"
    assert "2026-11-21" in metadata["snapshot_date"]
    assert "membership is not verified" in metadata["detail"]
    assert all("proxy" in row["sector"].lower() for row in rows)


def test_directory_search_stays_available_without_quotes_or_provider_access():
    with patch("app.services.universe.httpx.get", side_effect=httpx.ConnectError("socket denied")), \
         patch("app.services.market._quote_executor.submit") as submit:
        result = get_company_market_rows(limit=6, search="NVIDIA", include_quotes=False)

    assert result["total"] == 1
    assert result["companies"][0]["ticker"] == "NVDA"
    assert result["companies"][0]["quote_status"] == "not_requested"
    assert result["directory"]["status"] == "stale_limited_fallback"
    submit.assert_not_called()


def test_quote_batch_failure_is_cached_as_unavailable_instead_of_pending_forever(monkeypatch):
    from app.services import market

    monkeypatch.setattr(market.yf, "download", lambda **_kwargs: (_ for _ in ()).throw(httpx.ConnectError("socket denied")))
    market._quote_cache.clear()
    market._quote_cache_time.clear()
    market._refresh_quotes(("AAPL", "MSFT"))

    assert market._quote_cache["AAPL"]["quote_status"] == "unavailable"
    assert market._quote_cache["MSFT"]["price"] is None
    assert market._quote_cache_time["AAPL"] > 0


def test_company_identity_survives_yahoo_quote_provider_failure(monkeypatch):
    from app.services import market

    monkeypatch.setattr(market, "get_sp500_universe", lambda: [{
        "ticker": "AAPL", "name": "Apple", "sector": "Information Technology (XLK proxy)",
    }])
    monkeypatch.setattr(market, "get_sp500_universe_metadata", lambda: {"status": "stale_limited_fallback"})
    monkeypatch.setattr(market.yf, "Ticker", lambda _symbol: (_ for _ in ()).throw(httpx.ConnectError("socket denied")))

    result = market.get_company_market_row("AAPL")

    assert result["ticker"] == "AAPL"
    assert result["name"] == "Apple"
    assert result["price"] is None
    assert result["quote_status"] == "unavailable"
