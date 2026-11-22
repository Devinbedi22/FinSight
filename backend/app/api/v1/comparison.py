"""Multi-company comparison API."""

import re

from fastapi import APIRouter, HTTPException, Query

from app.services.comparison import get_company_comparison
from app.services.market import PRICE_HISTORY_PERIODS
from app.services.universe import get_sp500_universe, get_sp500_universe_metadata

router = APIRouter()
_TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,16}$")


@router.get("/companies/compare")
def compare_companies(
    tickers: str = Query(min_length=3, max_length=67, description="Comma-separated S&P 500 tickers; select 2 to 4."),
    period: str = Query(default="1y", pattern="^(1mo|3mo|6mo|1y|5y)$"),
) -> dict:
    requested = [item.strip().upper() for item in tickers.split(",") if item.strip()]
    if not 2 <= len(requested) <= 4:
        raise HTTPException(status_code=422, detail="Select between 2 and 4 distinct company tickers.")
    if len(set(requested)) != len(requested):
        raise HTTPException(status_code=422, detail="Duplicate tickers are not allowed.")
    if any(not _TICKER_PATTERN.fullmatch(ticker) for ticker in requested):
        raise HTTPException(status_code=422, detail="One or more tickers have invalid characters.")
    try:
        universe = {row["ticker"].upper(): row for row in get_sp500_universe()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Company directory is temporarily unavailable.") from exc
    unsupported = [ticker for ticker in requested if ticker not in universe]
    if unsupported:
        raise HTTPException(status_code=404, detail=f"Unsupported S&P 500 ticker(s): {', '.join(unsupported)}")
    try:
        result = get_company_comparison(requested, period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Comparison data is temporarily unavailable.") from exc
    result["companies"] = [
        {**item, "name": universe[item["ticker"]]["name"], "sector": universe[item["ticker"]].get("sector")}
        for item in result["companies"]
    ]
    result["directory"] = get_sp500_universe_metadata()
    if all(item["status"] == "unavailable" for item in result["companies"]):
        raise HTTPException(status_code=502, detail="Price history is unavailable for all selected companies.")
    return result
