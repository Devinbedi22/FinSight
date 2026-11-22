"""SEC EDGAR CompanyFacts access with process-local caching and provenance."""

from __future__ import annotations

from datetime import date, datetime, timezone
from threading import Lock
from time import monotonic, sleep
from typing import Any

import httpx

from app.core.config import get_settings

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_DATA_URL = "https://data.sec.gov"
_CACHE_TTL_SECONDS = 6 * 60 * 60
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = Lock()
_request_lock = Lock()
_last_request_at = 0.0


class FundamentalsProviderError(RuntimeError):
    """A provider/configuration error that is safe to return as an API detail."""


def _sec_get(url: str, user_agent: str) -> dict[str, Any]:
    global _last_request_at
    with _request_lock:
        delay = 0.11 - (monotonic() - _last_request_at)
        if delay > 0:
            sleep(delay)
        try:
            response = httpx.get(
                url,
                headers={"User-Agent": user_agent, "Accept": "application/json"},
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
            )
            _last_request_at = monotonic()
        except httpx.HTTPError as exc:
            raise FundamentalsProviderError(f"SEC request failed: {exc}") from exc
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "")
        raise FundamentalsProviderError(
            f"SEC rate limit reached (HTTP 429); retry after {retry_after or 'a short wait'}."
        )
    try:
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FundamentalsProviderError(f"SEC returned HTTP {response.status_code}.") from exc
    try:
        return response.json()
    except ValueError as exc:
        raise FundamentalsProviderError("SEC returned an invalid JSON response.") from exc


def _cached(key: str) -> dict | None:
    with _cache_lock:
        item = _cache.get(key)
        if item and monotonic() - item[0] < _CACHE_TTL_SECONDS:
            return item[1]
        if item:
            _cache.pop(key, None)
    return None


def _store(key: str, value: dict) -> dict:
    with _cache_lock:
        _cache[key] = (monotonic(), value)
    return value


def _ticker_map(user_agent: str) -> dict[str, dict]:
    cached = _cached("ticker-map")
    if cached is not None:
        return cached
    raw = _sec_get(SEC_TICKERS_URL, user_agent)
    result = {}
    for item in raw.values():
        ticker = str(item.get("ticker", "")).upper().replace(".", "-")
        if ticker:
            result[ticker] = {"cik": int(item["cik_str"]), "title": item.get("title", "")}
    if not result:
        raise FundamentalsProviderError("SEC ticker directory did not contain any companies.")
    return _store("ticker-map", result)


def _facts_for_tag(facts: dict, tags: tuple[str, ...], unit: str) -> list[dict]:
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        concept = us_gaap.get(tag, {})
        units = concept.get("units", {})
        rows = units.get(unit, [])
        if not rows and unit == "USD / shares":
            rows = units.get("USD/shares", [])
        if rows:
            return rows
    return []


def _reported_periods(rows: list[dict], annual: bool) -> list[dict]:
    selected: dict[str, dict] = {}
    for row in rows:
        form = row.get("form", "")
        start, end = row.get("start"), row.get("end")
        if not start or not end or form not in {"10-K", "10-Q", "20-F", "40-F"}:
            continue
        try:
            days = (date.fromisoformat(end) - date.fromisoformat(start)).days
        except (TypeError, ValueError):
            continue
        # CompanyFacts can contain both discrete quarter and year-to-date
        # contexts in a 10-Q. Keep only discrete quarters here so TTM sums
        # never mix Q2/Q3 cumulative values with standalone quarters.
        if annual and not (300 <= days <= 400):
            continue
        if not annual and not (70 <= days <= 110):
            continue
        current = selected.get(end)
        if current is None or row.get("filed", "") > current.get("filed", ""):
            selected[end] = row
    return sorted(selected.values(), key=lambda item: item["end"], reverse=True)


def _instant_facts(rows: list[dict]) -> list[dict]:
    selected: dict[str, dict] = {}
    for row in rows:
        if row.get("start") or not row.get("end") or row.get("form") not in {"10-K", "10-Q", "20-F", "40-F"}:
            continue
        end = row["end"]
        current = selected.get(end)
        if current is None or row.get("filed", "") > current.get("filed", ""):
            selected[end] = row
    return sorted(selected.values(), key=lambda item: item["end"], reverse=True)


def _metric(row: dict | None, unit: str, period_type: str) -> dict | None:
    if row is None:
        return None
    return {
        "value": row.get("val"),
        "unit": unit,
        "period_type": period_type,
        "period_start": row.get("start"),
        "period_end": row.get("end"),
        "filing_date": row.get("filed"),
        "form": row.get("form"),
        "source": "SEC EDGAR CompanyFacts",
    }


def _reported_by(rows: list[dict], cutoff: date) -> list[dict]:
    available = []
    for row in rows:
        try:
            filed = date.fromisoformat(row.get("filed", ""))
            period_end = date.fromisoformat(row.get("end", ""))
        except (TypeError, ValueError):
            continue
        if filed <= cutoff and period_end <= cutoff:
            available.append(row)
    return available


def get_company_fundamentals(
    ticker: str,
    latest_price: float | None = None,
    latest_price_as_of: str | None = None,
    as_of_date: date | None = None,
) -> dict:
    """Return selected SEC-reported metrics; unsupported facts remain null."""
    settings = get_settings()
    user_agent = settings.sec_user_agent
    if not user_agent or "@" not in user_agent:
        raise FundamentalsProviderError(
            "Set SEC_USER_AGENT to an application name and monitored contact email before requesting SEC data."
        )
    symbol = ticker.upper().replace(".", "-")
    tickers = _ticker_map(user_agent)
    company = tickers.get(symbol)
    if company is None:
        raise FundamentalsProviderError(f"{symbol} was not found in the SEC ticker directory.")
    cik = company["cik"]
    key = f"facts:{cik}"
    payload = _cached(key)
    if payload is None:
        cik_text = f"{cik:010d}"
        facts = _sec_get(f"{SEC_DATA_URL}/api/xbrl/companyfacts/CIK{cik_text}.json", user_agent)
        submission = _sec_get(f"{SEC_DATA_URL}/submissions/CIK{cik_text}.json", user_agent)
        payload = _store(key, {"facts": facts, "submission": submission})

    facts = payload["facts"]
    concepts = {
        "revenue": _facts_for_tag(facts, ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"), "USD"),
        "net_income": _facts_for_tag(facts, ("NetIncomeLoss", "ProfitLoss"), "USD"),
        "diluted_eps": _facts_for_tag(facts, ("EarningsPerShareDiluted",), "USD / shares"),
        "equity": _facts_for_tag(facts, ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"), "USD"),
        "current_debt": _facts_for_tag(facts, ("LongTermDebtCurrent",), "USD"),
        "short_term_debt": _facts_for_tag(facts, ("ShortTermBorrowings",), "USD"),
        "long_term_debt": _facts_for_tag(facts, ("LongTermDebtNoncurrent", "LongTermDebt"), "USD"),
        "assets": _facts_for_tag(facts, ("Assets",), "USD"),
        "liabilities": _facts_for_tag(facts, ("Liabilities",), "USD"),
        "operating_cash_flow": _facts_for_tag(facts, ("NetCashProvidedByUsedInOperatingActivities",), "USD"),
        "capital_expenditure": _facts_for_tag(facts, ("PaymentsToAcquirePropertyPlantAndEquipment",), "USD"),
        "shares": _facts_for_tag(facts, ("EntityCommonStockSharesOutstanding",), "shares"),
    }
    if as_of_date is not None:
        concepts = {name: _reported_by(rows, as_of_date) for name, rows in concepts.items()}
    annual = {name: _reported_periods(rows, annual=True) for name, rows in concepts.items()}
    quarterly = {name: _reported_periods(rows, annual=False) for name, rows in concepts.items()}
    instant = {name: _instant_facts(rows) for name, rows in concepts.items()}

    revenue = annual["revenue"]
    revenue_growth = None
    revenue_days = [
        (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days
        for row in revenue[:2]
    ] if len(revenue) >= 2 else []
    if len(revenue) >= 2 and revenue[1].get("val") and abs(revenue_days[0] - revenue_days[1]) <= 10:
        revenue_growth = {
            **_metric(revenue[0], "USD", "annual"),
            "value": revenue[0]["val"] / revenue[1]["val"] - 1,
            "unit": "ratio",
            "comparison_period_end": revenue[1].get("end"),
            "note": "Year-over-year change between annual revenue periods with lengths within 10 days of each other.",
        }
    annual_revenue = revenue[0] if revenue else None
    net_income = next(
        (row for row in annual["net_income"] if annual_revenue
         and row.get("start") == annual_revenue.get("start")
         and row.get("end") == annual_revenue.get("end")),
        None,
    )
    profit_margin = None
    if net_income and annual_revenue and annual_revenue.get("val"):
        profit_margin = {**_metric(net_income, "USD", "annual"), "value": net_income["val"] / annual_revenue["val"], "unit": "ratio"}

    equity_rows = instant["equity"]
    debt_equity = None
    debt_components = (instant["long_term_debt"], instant["current_debt"], instant["short_term_debt"])
    debt_dates = sorted({row["end"] for rows in debt_components for row in rows}, reverse=True)
    debt_date = debt_dates[0] if debt_dates else None
    matching_debt = [row for rows in debt_components for row in rows if row.get("end") == debt_date]
    debt_equity_fact = next((row for row in equity_rows if row.get("end") == debt_date), None)
    if matching_debt and debt_equity_fact and debt_equity_fact.get("val"):
        total_debt = sum(row["val"] for row in matching_debt)
        debt_equity = {
            **_metric(matching_debt[0], "USD", "instant"),
            "value": total_debt / debt_equity_fact["val"],
            "unit": "ratio",
            "denominator_period_end": debt_equity_fact["end"],
            "note": "Uses reported long-term debt, current maturities, and short-term borrowings for the same reporting date when available.",
        }

    operating_cf = annual["operating_cash_flow"][0] if annual["operating_cash_flow"] else None
    capex = next(
        (row for row in annual["capital_expenditure"] if operating_cf
         and row.get("start") == operating_cf.get("start")
         and row.get("end") == operating_cf.get("end")),
        None,
    )
    free_cash_flow = None
    if operating_cf and capex:
        # SEC cash-flow outflows are commonly reported as positive amounts.
        free_cash_flow = {**_metric(operating_cf, "USD", "annual"), "value": operating_cf["val"] - abs(capex["val"]), "unit": "USD", "capital_expenditure_period_end": capex["end"]}

    eps_rows = quarterly["diluted_eps"][:4]
    ttm_eps = None
    quarterly_dates = [date.fromisoformat(row["end"]) for row in eps_rows]
    consecutive_quarters = len(quarterly_dates) == 4 and all(
        70 <= (later - earlier).days <= 110
        for earlier, later in zip(reversed(quarterly_dates[1:]), reversed(quarterly_dates[:-1]))
    )
    if consecutive_quarters:
        ttm_eps = {
            **_metric(eps_rows[0], "USD / shares", "trailing_12_months"),
            "value": sum(row["val"] for row in eps_rows),
            "unit": "USD / shares",
            "quarters": [row["end"] for row in eps_rows],
            "note": "Sum of diluted EPS for four consecutive discrete reported quarters; year-to-date and annual periods are excluded.",
        }
    latest_shares = instant["shares"][0] if instant["shares"] else None
    market_cap = None
    if latest_price is not None and latest_shares is not None:
        market_cap = {**_metric(latest_shares, "shares", "instant"), "value": latest_price * latest_shares["val"], "unit": "USD", "price_as_of": latest_price_as_of, "note": "Calculated from latest available daily close and latest SEC-reported shares outstanding."}
    pe_ratio = None
    if latest_price is not None and ttm_eps and ttm_eps["value"] > 0:
        pe_ratio = {**ttm_eps, "value": latest_price / ttm_eps["value"], "unit": "ratio", "price": latest_price, "price_as_of": latest_price_as_of, "note": "Calculated from latest available daily close divided by SEC-reported diluted EPS for four consecutive discrete reported quarters."}
    roe = None
    if net_income:
        current_equity = next((row for row in equity_rows if row.get("end") == net_income.get("end")), None)
        prior_equity = next((row for row in equity_rows if row.get("end", "") < net_income.get("end", "")), None)
        if current_equity and prior_equity and current_equity["val"] + prior_equity["val"]:
            roe = {
                **_metric(net_income, "USD", "annual"),
                "value": net_income["val"] / ((current_equity["val"] + prior_equity["val"]) / 2),
                "unit": "ratio",
                "equity_periods": [current_equity["end"], prior_equity["end"]],
            }

    return {
        "ticker": symbol,
        "company": facts.get("entityName", company["title"]),
        "cik": cik,
        "industry": payload["submission"].get("sicDescription"),
        "source": "SEC EDGAR CompanyFacts",
        "source_url": f"https://www.sec.gov/edgar/browse/?CIK={cik}",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": as_of_date.isoformat() if as_of_date else None,
        "metrics": {
            "market_cap": market_cap,
            "pe_ratio": pe_ratio,
            "eps": ttm_eps or (_metric(annual["diluted_eps"][0], "USD / shares", "annual") if annual["diluted_eps"] else None),
            "revenue": _metric(annual_revenue, "USD", "annual"),
            "net_income": _metric(net_income, "USD", "annual"),
            "assets": _metric(instant["assets"][0], "USD", "instant") if instant["assets"] else None,
            "liabilities": _metric(instant["liabilities"][0], "USD", "instant") if instant["liabilities"] else None,
            "revenue_growth": revenue_growth,
            "profit_margin": profit_margin,
            "debt_to_equity": debt_equity,
            "free_cash_flow": free_cash_flow,
            "return_on_equity": roe,
        },
    }
