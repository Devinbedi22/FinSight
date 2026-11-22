import pytest
from unittest.mock import patch

from app.services.comparison import BENCHMARK_TICKER, build_comparison
from app.api.v1 import comparison as comparison_api
from app.api.v1.news import companies as companies_endpoint
from app.services.market import get_company_market_rows
from fastapi import HTTPException


def _bars(values):
    return [{"date": day, "close": close} for day, close in values]


def test_comparison_normalizes_to_first_common_session_and_calculates_metrics():
    histories = {
        "AAA": _bars([("2025-01-02", 10), ("2025-01-03", 11), ("2025-01-06", 9), ("2025-01-07", 12)]),
        "BBB": _bars([("2025-01-03", 20), ("2025-01-06", 22), ("2025-01-07", 18)]),
    }
    benchmark = _bars([("2025-01-03", 100), ("2025-01-06", 105), ("2025-01-07", 110)])

    result = build_comparison(["AAA", "BBB"], histories, benchmark, period="1mo")

    assert result["status"] == "available"
    assert [row["date"] for row in result["chart"]] == ["2025-01-03", "2025-01-06", "2025-01-07"]
    assert result["chart"][0]["AAA"] == 100
    assert result["chart"][0]["BBB"] == 100
    assert result["chart"][0][BENCHMARK_TICKER] == 100
    aaa = result["companies"][0]
    assert aaa["cumulative_return"] == pytest.approx(12 / 11 - 1)
    assert aaa["maximum_drawdown"] == pytest.approx(9 / 11 - 1)
    assert aaa["benchmark_relative_return"] == pytest.approx((12 / 11 - 1) - (110 / 100 - 1))
    assert aaa["annualized_volatility"] is not None


def test_missing_and_misaligned_sessions_are_not_filled():
    histories = {
        "AAA": _bars([("2025-01-02", 10), ("2025-01-03", 11), ("2025-01-06", 11.5), ("2025-01-07", 12), ("2025-01-08", 12.5)]),
        "BBB": _bars([("2025-01-03", 20), ("2025-01-06", 21), ("2025-01-08", 22), ("2025-01-09", 23)]),
    }
    result = build_comparison(["AAA", "BBB"], histories, [], period="1mo")

    assert [row["date"] for row in result["chart"]] == ["2025-01-03", "2025-01-06", "2025-01-08"]
    assert all(row.get("SPY") is None for row in result["chart"])
    assert result["companies"][0]["dropped_observed_sessions"] == 1
    assert result["companies"][0]["annualized_volatility"] is None
    assert result["companies"][0]["benchmark_relative_return"] is None


def test_partial_history_and_single_common_session_return_explicit_unavailable_values():
    result = build_comparison(
        ["AAA", "BBB"],
        {"AAA": _bars([("2025-01-02", 10), ("2025-01-03", 11)]), "BBB": _bars([("2025-01-03", 20)])},
        [], period="1mo",
    )
    assert result["status"] == "insufficient_common_history"
    assert len(result["chart"]) == 1
    assert result["companies"][0]["cumulative_return"] is None
    assert result["companies"][0]["annualized_volatility"] is None
    assert result["companies"][0]["maximum_drawdown"] is None


@pytest.mark.parametrize("tickers", [["AAA"], ["AAA", "BBB", "CCC", "DDD", "EEE"], ["AAA", "AAA"]])
def test_comparison_enforces_two_to_four_distinct_companies(tickers):
    with pytest.raises(ValueError, match="2 to 4 distinct"):
        build_comparison(tickers, {}, [], period="1mo")


def test_comparison_rejects_unsupported_period():
    with pytest.raises(ValueError, match="Unsupported comparison period"):
        build_comparison(["AAA", "BBB"], {}, [], period="max")


@pytest.mark.parametrize("tickers", ["AAPL", "AAPL,MSFT,NVDA,AMZN,TSLA", "AAPL,AAPL", "AAPL,MSFT/ADMIN"])
def test_api_rejects_invalid_selection_before_provider_call(monkeypatch, tickers):
    monkeypatch.setattr(comparison_api, "get_sp500_universe", lambda: [{"ticker": "AAPL", "name": "Apple", "sector": "Technology"}, {"ticker": "MSFT", "name": "Microsoft", "sector": "Technology"}])
    with pytest.raises(HTTPException) as error:
        comparison_api.compare_companies(tickers=tickers, period="1y")
    assert error.value.status_code == 422


def test_api_rejects_ticker_outside_supported_directory(monkeypatch):
    monkeypatch.setattr(comparison_api, "get_sp500_universe", lambda: [{"ticker": "AAPL", "name": "Apple", "sector": "Technology"}, {"ticker": "MSFT", "name": "Microsoft", "sector": "Technology"}])
    with pytest.raises(HTTPException) as error:
        comparison_api.compare_companies(tickers="AAPL,FAKE", period="1y")
    assert error.value.status_code == 404


def test_api_attaches_directory_metadata_and_preserves_provider_partial_errors(monkeypatch):
    monkeypatch.setattr(comparison_api, "get_sp500_universe", lambda: [{"ticker": "AAPL", "name": "Apple Inc.", "sector": "Information Technology"}, {"ticker": "MSFT", "name": "Microsoft Corporation", "sector": "Information Technology"}])
    monkeypatch.setattr(comparison_api, "get_sp500_universe_metadata", lambda: {"status": "current"})
    monkeypatch.setattr(comparison_api, "get_company_comparison", lambda tickers, period: {
        "companies": [{"ticker": ticker, "status": "available", "common_session_count": 3} for ticker in tickers],
        "provider_errors": {"SPY": "Price history provider is temporarily unavailable."},
    })
    result = comparison_api.compare_companies(tickers="aapl,msft", period="1y")
    assert result["companies"][0]["name"] == "Apple Inc."
    assert result["companies"][1]["sector"] == "Information Technology"
    assert "SPY" in result["provider_errors"]


def test_directory_search_can_skip_quotes_without_scheduling_provider_work():
    with patch("app.services.market.get_sp500_universe", return_value=[
        {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Information Technology"},
        {"ticker": "MSFT", "name": "Microsoft Corporation", "sector": "Information Technology"},
    ]), patch("app.services.market.get_sp500_universe_metadata", return_value={"status": "current"}), \
         patch("app.services.market._quote_executor.submit") as submit:
        result = get_company_market_rows(limit=8, search="apple", include_quotes=False)
    submit.assert_not_called()
    assert [row["ticker"] for row in result["companies"]] == ["AAPL"]
    assert result["companies"][0]["quote_status"] == "not_requested"
    assert "quotes not requested" in result["source"]


def test_companies_api_exposes_quote_opt_out_for_picker_search():
    with patch("app.api.v1.news.get_company_market_rows", return_value={"companies": [], "total": 0}) as rows:
        result = companies_endpoint(limit=8, offset=0, search="Apple", include_quotes=False)
    assert result["total"] == 0
    rows.assert_called_once_with(limit=8, offset=0, search="Apple", include_quotes=False)
