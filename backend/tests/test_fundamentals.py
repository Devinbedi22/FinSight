"""SEC fundamentals transformations and unavailable-data contracts."""

import unittest
from datetime import date
from unittest.mock import patch

from app.services.fundamentals import (
    FundamentalsProviderError, _cache, _reported_periods, _sec_get, _ticker_map,
    get_company_fundamentals,
)


def fact(value, end, form, filed, start=None):
    result = {"val": value, "end": end, "form": form, "filed": filed}
    if start:
        result["start"] = start
    return result


class FundamentalsTest(unittest.TestCase):
    def test_reported_metrics_include_periods_and_derived_inputs(self):
        facts = {
            "entityName": "Example Corp",
            "facts": {"us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                    fact(2000, "2024-12-31", "10-K", "2025-02-01", "2024-01-01"),
                    fact(1600, "2023-12-31", "10-K", "2024-02-01", "2023-01-01"),
                ]}},
                "NetIncomeLoss": {"units": {"USD": [
                    fact(200, "2024-12-31", "10-K", "2025-02-01", "2024-01-01"),
                ]}},
                "EarningsPerShareDiluted": {"units": {"USD/shares": [
                    fact(0.5, end, form, filed, start)
                    for end, form, filed, start in [
                        ("2024-03-31", "10-Q", "2024-04-30", "2024-01-01"),
                        ("2024-06-30", "10-Q", "2024-07-30", "2024-04-01"),
                        ("2024-09-30", "10-Q", "2024-10-30", "2024-07-01"),
                        ("2024-12-31", "10-K", "2025-02-01", "2024-10-01"),
                    ]
                ] + [
                    # Cumulative year-to-date facts must not be mistaken for a discrete quarter.
                    fact(90.0, "2024-09-30", "10-Q", "2024-10-30", "2024-01-01"),
                    fact(9.0, "2024-12-31", "10-K", "2025-02-01", "2024-01-01"),
                ]}},
                "StockholdersEquity": {"units": {"USD": [
                    fact(1100, "2024-12-31", "10-K", "2025-02-01"),
                    fact(900, "2023-12-31", "10-K", "2024-02-01"),
                ]}},
                "LongTermDebt": {"units": {"USD": [fact(300, "2024-12-31", "10-K", "2025-02-01")]}},
                "LongTermDebtCurrent": {"units": {"USD": [fact(40, "2024-12-31", "10-K", "2025-02-01")]}},
                "ShortTermBorrowings": {"units": {"USD": [fact(25, "2024-12-31", "10-K", "2025-02-01")]}},
                "Assets": {"units": {"USD": [fact(2000, "2024-12-31", "10-K", "2025-02-01")]}},
                "Liabilities": {"units": {"USD": [fact(900, "2024-12-31", "10-K", "2025-02-01")]}},
                "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [fact(500, "2024-12-31", "10-K", "2025-02-01", "2024-01-01")]}},
                "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [fact(100, "2024-12-31", "10-K", "2025-02-01", "2024-01-01")]}},
                "EntityCommonStockSharesOutstanding": {"units": {"shares": [fact(1000, "2024-12-31", "10-K", "2025-02-01")]}},
            }},
        }
        cached = {"facts": facts, "submission": {"sicDescription": "Electronic Computers"}}
        with patch("app.services.fundamentals.get_settings") as settings, \
                patch("app.services.fundamentals._ticker_map", return_value={"EXMP": {"cik": 123, "title": "Example Corp"}}), \
                patch("app.services.fundamentals._cached", return_value=cached):
            settings.return_value.sec_user_agent = "FinSight tests test@example.com"
            result = get_company_fundamentals("EXMP", latest_price=100, latest_price_as_of="2025-02-03")

        self.assertEqual(result["industry"], "Electronic Computers")
        self.assertEqual(result["metrics"]["revenue"]["value"], 2000)
        self.assertEqual(result["metrics"]["revenue"]["period_type"], "annual")
        self.assertAlmostEqual(result["metrics"]["revenue_growth"]["value"], 0.25)
        self.assertEqual(result["metrics"]["market_cap"]["value"], 100000)
        self.assertAlmostEqual(result["metrics"]["pe_ratio"]["value"], 50)
        self.assertEqual(result["metrics"]["pe_ratio"]["period_type"], "trailing_12_months")
        self.assertEqual(result["metrics"]["pe_ratio"]["price_as_of"], "2025-02-03")
        self.assertAlmostEqual(result["metrics"]["eps"]["value"], 2.0)
        self.assertEqual(result["metrics"]["free_cash_flow"]["value"], 400)
        self.assertEqual(result["metrics"]["profit_margin"]["filing_date"], "2025-02-01")
        self.assertEqual(result["metrics"]["net_income"]["value"], 200)
        self.assertEqual(result["metrics"]["assets"]["value"], 2000)
        self.assertEqual(result["metrics"]["liabilities"]["value"], 900)
        self.assertAlmostEqual(result["metrics"]["debt_to_equity"]["value"], 365 / 1100)
        self.assertIn("discrete reported quarters", result["metrics"]["pe_ratio"]["note"])

    def test_quarterly_period_selection_excludes_year_to_date_and_annual_rows(self):
        rows = [
            fact(10, "2024-03-31", "10-Q", "2024-04-30", "2024-01-01"),
            fact(99, "2024-06-30", "10-Q", "2024-07-30", "2024-01-01"),
            fact(20, "2024-06-30", "10-Q", "2024-07-30", "2024-04-01"),
            fact(30, "2024-09-30", "10-Q", "2024-10-30", "2024-07-01"),
            fact(40, "2024-12-31", "10-K", "2025-02-01", "2024-10-01"),
            fact(100, "2024-12-31", "10-K", "2025-02-01", "2024-01-01"),
        ]
        selected = _reported_periods(rows, annual=False)
        self.assertEqual([row["val"] for row in selected], [40, 30, 20, 10])

    def test_ticker_map_resolves_cik_and_uses_process_cache(self):
        _cache.clear()
        payload = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
        with patch("app.services.fundamentals._sec_get", return_value=payload) as request:
            first = _ticker_map("FinSight tests contact@example.invalid")
            second = _ticker_map("FinSight tests contact@example.invalid")
        self.assertEqual(first["AAPL"], {"cik": 320193, "title": "Apple Inc."})
        self.assertIs(first, second)
        request.assert_called_once()
        _cache.clear()

    def test_companyfacts_and_submission_payloads_are_cached_by_cik(self):
        _cache.clear()
        payloads = [
            {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}},
            {"entityName": "Apple Inc.", "facts": {"us-gaap": {}}},
            {"sicDescription": "Electronic Computers"},
        ]

        class Response:
            status_code = 200
            headers = {}

            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        with patch("app.services.fundamentals.get_settings") as settings, \
                patch("app.services.fundamentals.httpx.get", side_effect=[Response(p) for p in payloads]) as request:
            settings.return_value.sec_user_agent = "FinSight tests contact@example.invalid"
            first = get_company_fundamentals("AAPL")
            second = get_company_fundamentals("AAPL")

        self.assertEqual(request.call_count, 3)
        urls = [call.args[0] for call in request.call_args_list]
        self.assertIn("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json", urls)
        self.assertIn("https://data.sec.gov/submissions/CIK0000320193.json", urls)
        self.assertEqual(first["cik"], 320193)
        self.assertEqual(first["company"], "Apple Inc.")
        self.assertEqual(first["industry"], "Electronic Computers")
        self.assertEqual(first["metrics"]["revenue"], None)
        self.assertEqual(second["metrics"]["assets"], None)
        _cache.clear()

    def test_missing_sec_contact_user_agent_fails_explicitly(self):
        with patch("app.services.fundamentals.get_settings") as settings:
            settings.return_value.sec_user_agent = None
            with self.assertRaisesRegex(RuntimeError, "SEC_USER_AGENT"):
                get_company_fundamentals("EXMP")

    def test_sec_rate_limit_is_reported_without_retrying_unboundedly(self):
        response = type("Response", (), {"status_code": 429, "headers": {"Retry-After": "5"}})()
        with patch("app.services.fundamentals.httpx.get", return_value=response):
            with self.assertRaisesRegex(FundamentalsProviderError, "HTTP 429.*5"):
                _sec_get("https://data.sec.gov/test", "FinSight tests test@example.com")

    def test_sec_timeout_configuration_bounds_connect_and_read(self):
        response = type("Response", (), {
            "status_code": 200, "headers": {}, "json": lambda self: {},
            "raise_for_status": lambda self: None,
        })()
        with patch("app.services.fundamentals.httpx.get", return_value=response) as request:
            _sec_get("https://data.sec.gov/test", "FinSight tests test@example.com")
        timeout = request.call_args.kwargs["timeout"]
        self.assertEqual(timeout.connect, 5.0)
        self.assertEqual(timeout.read, 15.0)

    def test_sec_connect_and_read_timeouts_are_reported_as_provider_errors(self):
        request = __import__("httpx").Request("GET", "https://data.sec.gov/test")
        for error in (
            __import__("httpx").ConnectTimeout("connection timed out", request=request),
            __import__("httpx").ReadTimeout("response read timed out", request=request),
        ):
            with self.subTest(error=type(error).__name__), patch(
                "app.services.fundamentals.httpx.get", side_effect=error
            ):
                with self.assertRaisesRegex(FundamentalsProviderError, "SEC request failed"):
                    _sec_get("https://data.sec.gov/test", "FinSight tests test@example.com")

    def test_sec_forbidden_response_is_reported_without_retry(self):
        import httpx
        response = httpx.Response(403, request=httpx.Request("GET", "https://data.sec.gov/test"))
        with patch("app.services.fundamentals.httpx.get", return_value=response) as request:
            with self.assertRaisesRegex(FundamentalsProviderError, "HTTP 403"):
                _sec_get("https://data.sec.gov/test", "FinSight tests test@example.com")
        request.assert_called_once()

    def test_invalid_sec_json_is_reported(self):
        import httpx
        response = httpx.Response(200, content=b"not json", request=httpx.Request("GET", "https://data.sec.gov/test"))
        with patch("app.services.fundamentals.httpx.get", return_value=response):
            with self.assertRaisesRegex(FundamentalsProviderError, "invalid JSON"):
                _sec_get("https://data.sec.gov/test", "FinSight tests test@example.com")

    def test_provider_failure_does_not_poison_cache_and_recovers(self):
        import httpx
        _cache.clear()
        tickers = {"0": {"cik_str": 123, "ticker": "EXMP", "title": "Example Corp"}}
        facts = {"entityName": "Example Corp", "facts": {}}
        submissions = {"sicDescription": "Example"}
        responses = [
            httpx.ConnectTimeout("connection timed out", request=httpx.Request("GET", "https://www.sec.gov/files/company_tickers.json")),
            httpx.Response(200, json=tickers, request=httpx.Request("GET", "https://www.sec.gov/files/company_tickers.json")),
            httpx.Response(200, json=facts, request=httpx.Request("GET", "https://data.sec.gov/facts")),
            httpx.Response(200, json=submissions, request=httpx.Request("GET", "https://data.sec.gov/submissions")),
        ]
        with patch("app.services.fundamentals.get_settings") as settings, patch(
            "app.services.fundamentals.httpx.get", side_effect=responses
        ) as request:
            settings.return_value.sec_user_agent = "FinSight tests contact@example.invalid"
            with self.assertRaises(FundamentalsProviderError):
                get_company_fundamentals("EXMP")
            result = get_company_fundamentals("EXMP")
        self.assertEqual(result["cik"], 123)
        self.assertEqual(request.call_count, 4)
        _cache.clear()

    def test_as_of_excludes_facts_filed_after_cutoff_and_future_periods(self):
        facts = {
            "entityName": "Example Corp",
            "facts": {"us-gaap": {
                "Revenues": {"units": {"USD": [
                    fact(100, "2023-12-31", "10-K", "2024-02-01", "2023-01-01"),
                    fact(150, "2023-12-31", "10-K", "2025-02-01", "2023-01-01"),
                    fact(300, "2025-12-31", "10-K", "2024-12-01", "2025-01-01"),
                ]}},
            }},
        }
        cached = {"facts": facts, "submission": {}}
        with patch("app.services.fundamentals.get_settings") as settings, \
                patch("app.services.fundamentals._ticker_map", return_value={"EXMP": {"cik": 123, "title": "Example Corp"}}), \
                patch("app.services.fundamentals._cached", return_value=cached):
            settings.return_value.sec_user_agent = "FinSight tests test@example.com"
            result = get_company_fundamentals("EXMP", as_of_date=date(2024, 12, 31))

        metric = result["metrics"]["revenue"]
        self.assertEqual(metric["value"], 100)
        self.assertEqual(metric["filing_date"], "2024-02-01")
        self.assertEqual(result["as_of_date"], "2024-12-31")

    def test_missing_xbrl_tags_return_null_metrics_without_failing(self):
        cached = {"facts": {"entityName": "Example Corp", "facts": {}}, "submission": {}}
        with patch("app.services.fundamentals.get_settings") as settings, \
                patch("app.services.fundamentals._ticker_map", return_value={"EXMP": {"cik": 123, "title": "Example Corp"}}), \
                patch("app.services.fundamentals._cached", return_value=cached):
            settings.return_value.sec_user_agent = "FinSight tests test@example.com"
            result = get_company_fundamentals("EXMP")

        self.assertTrue(all(value is None for value in result["metrics"].values()))
