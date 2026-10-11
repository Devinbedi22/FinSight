"""Current S&P 500 and broad U.S.-listed security universes."""

import csv
from functools import lru_cache
from io import StringIO
from datetime import datetime, timezone

import httpx
import pandas as pd

from app.core.config import get_settings

LISTING_EXCHANGE_NAMES = {
    "N": "NYSE",
    "Q": "Nasdaq",
    "A": "NYSE American",
    "P": "NYSE Arca",
    "Z": "BATS Global Markets",
    "V": "Investors Exchange (IEX)",
}


@lru_cache(maxsize=1)
def get_sp500_universe() -> list[dict[str, str]]:
    response = httpx.get(
        get_settings().sp500_constituents_url,
        headers={"User-Agent": "FinSightResearch/0.1 (market-news POC)"},
        timeout=30,
    )
    response.raise_for_status()
    table = pd.read_csv(StringIO(response.text))
    if not {"Symbol", "Security", "GICS Sector"}.issubset(table.columns):
        raise RuntimeError("S&P constituent CSV is missing required columns")
    return [
        {
            "ticker": str(row["Symbol"]).strip(),
            "name": str(row["Security"]).strip(),
            "sector": str(row["GICS Sector"]).strip(),
        }
        for _, row in table.iterrows()
    ]


@lru_cache(maxsize=1)
def _load_us_listed_universe() -> tuple[list[dict[str, str]], str]:
    """Fetch current Nasdaq Trader-listed, non-test, non-ETF symbols.

    Nasdaq Trader's directory includes Nasdaq and other U.S. listing venues.
    It is a security master, not a company-sector file; exchange and security
    descriptions are preserved as published rather than guessed.
    """
    response = httpx.get(
        get_settings().us_listed_symbols_url,
        headers={"User-Agent": "FinSightResearch/0.1 (market-news POC)"},
        timeout=30,
    )
    response.raise_for_status()
    rows = csv.DictReader(StringIO(response.text), delimiter="|")
    constituents = []
    for row in rows:
        ticker = (row.get("Symbol") or "").strip()
        if (
            row.get("Nasdaq Traded") != "Y"
            or row.get("Test Issue") != "N"
            or row.get("ETF") != "N"
            or not ticker
        ):
            continue
        constituents.append(
            {
                "ticker": ticker,
                "name": (row.get("Security Name") or "").strip(),
                "listing_exchange": (row.get("Listing Exchange") or "").strip(),
                "listing_exchange_name": LISTING_EXCHANGE_NAMES.get(
                    (row.get("Listing Exchange") or "").strip(),
                    f"Other ({(row.get('Listing Exchange') or '').strip() or 'unknown'})",
                ),
                "market_category": (row.get("Market Category") or "").strip(),
            }
        )
    if not constituents:
        raise RuntimeError("Nasdaq Trader directory returned no active non-ETF symbols")
    return constituents, datetime.now(timezone.utc).isoformat()


def get_us_listed_universe(force_refresh: bool = False) -> tuple[list[dict[str, str]], str]:
    """Return the cached current U.S.-listed universe and its retrieval time.

    The process cache is refreshed on restart or by passing ``force_refresh``.
    """
    if force_refresh:
        _load_us_listed_universe.cache_clear()
    return _load_us_listed_universe()
