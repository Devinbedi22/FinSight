"""S&P 500 directory and broad U.S.-listed security universes.

The live S&P file is preferred. When it is unavailable, a dated, deliberately
small ticker set is derived from the repository's validated Phase 5B snapshot.
That fallback is not represented as a current S&P 500 constituent list.
"""

import csv
import hashlib
import json
import logging
from threading import Lock
from datetime import datetime, timezone
from functools import lru_cache
from io import StringIO
from pathlib import Path

import httpx
import pandas as pd

from app.core.config import get_settings

logger = logging.getLogger(__name__)

LISTING_EXCHANGE_NAMES = {
    "N": "NYSE",
    "Q": "Nasdaq",
    "A": "NYSE American",
    "P": "NYSE Arca",
    "Z": "BATS Global Markets",
    "V": "Investors Exchange (IEX)",
}

_DISPLAY_NAMES = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "AMZN": "Amazon",
    "TSLA": "Tesla",
}
_PROXY_SECTORS = {
    "AAPL": "Information Technology (XLK proxy)",
    "MSFT": "Information Technology (XLK proxy)",
    "NVDA": "Information Technology (XLK proxy)",
    "AMZN": "Consumer Discretionary (XLY proxy)",
    "TSLA": "Consumer Discretionary (XLY proxy)",
}
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_directory_lock = Lock()


def _local_research_snapshot() -> tuple[list[dict[str, str]], dict[str, str]]:
    """Read supported stock symbols from an existing hashed Phase 5B manifest."""
    roots = [
        _BACKEND_DIR / "data" / "market_cache" / "phase5b",
        _BACKEND_DIR / "data" / "forecast_tracking" / "snapshots",
    ]
    candidates: list[tuple[str, Path, dict]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for manifest_path in root.glob("*/manifest.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("schema_version") != "finsight.market-snapshot.v1":
                    continue
                stocks = manifest.get("security_roles", {}).get("stocks", [])
                series = manifest.get("series", {})
                if not stocks or any(symbol not in series for symbol in stocks):
                    continue
                invalid_series = False
                for symbol in stocks:
                    item = series[symbol]
                    data_path = manifest_path.parent / item.get("file", "")
                    if not data_path.is_file() or not item.get("sha256"):
                        invalid_series = True
                        break
                    digest = hashlib.sha256()
                    with data_path.open("rb") as data_file:
                        for chunk in iter(lambda: data_file.read(1024 * 1024), b""):
                            digest.update(chunk)
                    if digest.hexdigest() != item["sha256"]:
                        invalid_series = True
                        break
                if invalid_series:
                    continue
                candidates.append((str(manifest.get("retrieved_at_utc", "")), manifest_path, manifest))
            except (OSError, ValueError, TypeError, AttributeError):
                continue
    if not candidates:
        raise RuntimeError("No valid local Phase 5B market snapshot is available for directory fallback.")

    retrieved_at, path, manifest = max(candidates, key=lambda item: item[0])
    symbols = manifest["security_roles"]["stocks"]
    companies = [
        {
            "ticker": symbol,
            "name": _DISPLAY_NAMES[symbol],
            "sector": _PROXY_SECTORS[symbol],
        }
        for symbol in symbols
        if symbol in _DISPLAY_NAMES
    ]
    if not companies:
        raise RuntimeError("Local market snapshot contains no supported company symbols.")
    metadata = {
        "status": "stale_limited_fallback",
        "source": str(manifest.get("source", "Local Phase 5B market snapshot")),
        "snapshot_date": retrieved_at,
        "detail": (
            f"Limited local research universe from {path.parent.name}; retrieved {retrieved_at}. "
            "Current S&P 500 membership is not verified. Sector labels are ETF proxy groupings. "
            "Company display names are local ticker labels. The fallback remains cached until the backend restarts."
        ),
    }
    return companies, metadata


@lru_cache(maxsize=1)
def _load_sp500_directory() -> tuple[list[dict[str, str]], dict[str, str]]:
    """Load the live directory once, falling back to dated local research data."""
    try:
        response = httpx.get(
            get_settings().sp500_constituents_url,
            headers={"User-Agent": "FinSightResearch/0.1 (market-news POC)"},
            timeout=httpx.Timeout(connect=2.0, read=5.0, write=2.0, pool=2.0),
        )
        response.raise_for_status()
        table = pd.read_csv(StringIO(response.text))
        if not {"Symbol", "Security", "GICS Sector"}.issubset(table.columns):
            raise RuntimeError("S&P constituent CSV is missing required columns")
        companies = [
            {
                "ticker": str(row["Symbol"]).strip(),
                "name": str(row["Security"]).strip(),
                "sector": str(row["GICS Sector"]).strip(),
            }
            for _, row in table.iterrows()
        ]
        if not companies:
            raise RuntimeError("S&P constituent CSV returned no companies")
        metadata = {
            "status": "current",
            "source": "S&P 500 constituent dataset",
            "snapshot_date": datetime.now(timezone.utc).isoformat(),
            "detail": "Current constituents fetched from the configured S&P dataset.",
        }
        return companies, metadata
    except (httpx.HTTPError, ValueError, RuntimeError, OSError) as exc:
        try:
            companies, metadata = _local_research_snapshot()
        except Exception:
            logger.exception("Live S&P directory failed and no local research snapshot is usable")
            raise RuntimeError("S&P directory unavailable and no local fallback is available") from exc
        logger.warning("Using dated limited research-universe fallback: provider error type=%s", type(exc).__name__)
        return companies, metadata


def get_sp500_universe() -> list[dict[str, str]]:
    """Return the cached live directory or a clearly limited local fallback."""
    with _directory_lock:
        return _load_sp500_directory()[0]


def get_sp500_universe_metadata() -> dict[str, str]:
    """Return provenance and freshness information for the cached directory."""
    with _directory_lock:
        return dict(_load_sp500_directory()[1])


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
