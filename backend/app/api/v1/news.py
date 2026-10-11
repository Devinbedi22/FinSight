"""News analysis, U.S.-listed universe, and ingestion endpoints."""

from datetime import datetime, timedelta, timezone
from html import unescape
import logging
import re
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from fastapi.responses import RedirectResponse
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.orm import Session

from app.db.models import IngestionState, NewsArticle
from app.db.session import get_db
from app.core.config import get_settings
from app.services.news import analyze_headline, ingest_latest, review_stored_article, _classify_usefulness
from app.ml.financialbert import predict_expected_return
from app.ml.financial_relevance import financial_relevance_status
from app.services.news import rerank_company_news
from app.services.universe import get_sp500_universe, get_us_listed_universe
from app.services.market import get_company_market_row, get_company_market_rows, get_company_price_history

router = APIRouter()
logger = logging.getLogger(__name__)


class AnalyzeRequest(BaseModel):
    headline: str = Field(min_length=4, max_length=2000)
    summary: str | None = Field(default=None, max_length=12000)


class IngestRequest(BaseModel):
    limit: int = Field(default=25, ge=1, le=100)
    ticker: str | None = Field(default=None, min_length=1, max_length=16, pattern="^[A-Za-z0-9.\\-]+$")


class NewsOut(BaseModel):
    id: int
    title: str
    summary: str | None
    url: str
    source: str
    published_at: datetime | None
    ingested_at: datetime
    sentiment: str | None = None
    sentiment_score: float | None = None
    sentiment_scores: dict[str, float] | None = None
    ticker_candidates: list[dict]
    impact_predictions: list[dict] = Field(default_factory=list)
    usefulness: dict | None = None

    model_config = {"from_attributes": True}


@router.get("/news/{article_id:int}", response_model=NewsOut)
def get_news_article(article_id: int, session: Session = Depends(get_db)) -> NewsArticle:
    article = session.get(NewsArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Stored news article not found")
    return review_stored_article(article, refresh_usefulness=False)


@router.get("/news/{article_id}/open", include_in_schema=False)
def open_news_source(article_id: int, session: Session = Depends(get_db)) -> RedirectResponse:
    """Resolve Google News RSS redirects to the publisher's article URL."""
    article = session.get(NewsArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Stored news article not found")
    destination = article.url
    logger.info("News source open requested article_id=%d source=%s", article.id, article.source)
    host = (urlsplit(destination).hostname or "").lower()
    if host == "news.google.com" or host.endswith(".news.google.com"):
        try:
            with httpx.Client(follow_redirects=True, timeout=12) as client:
                with client.stream("GET", destination) as response:
                    response.raise_for_status()
                    resolved = str(response.url)
                    if (urlsplit(resolved).hostname or "").lower() not in {
                        "news.google.com", "www.google.com", "google.com",
                    }:
                        destination = resolved
        except httpx.HTTPError:
            # Keep the original Google News link usable if the publisher or
            # aggregator declines automated redirect resolution.
            pass
    return RedirectResponse(destination, status_code=307)


@router.get("/universe/sp500")
def sp500_universe() -> dict:
    try:
        companies = get_sp500_universe()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not refresh S&P 500 universe: {exc}") from exc
    return {"count": len(companies), "constituents": companies}


@router.get("/companies")
def companies(limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)) -> dict:
    """Real S&P 500 constituents with latest available Yahoo Finance quote data."""
    try:
        return get_company_market_rows(limit=limit, offset=offset)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Company/market data unavailable: {exc}") from exc


@router.get("/companies/{ticker}")
def company(ticker: str) -> dict:
    try:
        result = get_company_market_row(ticker)
        if result is None:
            raise HTTPException(status_code=404, detail="Ticker is not an S&P 500 constituent")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Company quote unavailable: {exc}") from exc


@router.get("/companies/{ticker}/prediction")
def company_prediction(ticker: str, session: Session = Depends(get_db)) -> dict:
    """Build the repo-style company forecast from retrieved headlines and actual prices."""
    try:
        ticker = ticker.upper()
        company_row = next(
            (row for row in get_sp500_universe() if row["ticker"].upper() == ticker), None
        )
        if company_row is None:
            raise HTTPException(status_code=404, detail="Ticker is not an S&P 500 constituent")
        logger.info("Company prediction requested ticker=%s", ticker)
        history = get_company_price_history(ticker)
        if not history:
            return {"ticker": ticker, "company": company_row["name"], "sector": company_row["sector"], "history": [],
                    "prediction": None, "news_used": [], "status": "price_history_unavailable"}

        articles = session.scalars(
            select(NewsArticle)
            .where(NewsArticle.published_at.is_not(None))
            .order_by(desc(NewsArticle.published_at), desc(NewsArticle.ingested_at))
        )
        retrieved = []
        for article in articles:
            article = review_stored_article(article, refresh_usefulness=False)
            candidate = next((
                item for item in article.ticker_candidates
                if item.get("ticker", "").upper() == ticker
            ), None)
            if candidate is None:
                continue
            score = candidate.get("relevance_score")
            retrieved.append({
                "id": article.id,
                "title": article.title,
                "description": (unescape(re.sub(r"<[^>]+>", " ", article.summary or ""))
                                .replace("&nbsp;", " ").strip() or article.title),
                "published_at": article.published_at.isoformat(),
                "url": article.url,
                "relevance_score": score,
                "explicit_company_mention": bool(candidate.get("entity_mentioned")),
                "rank": float(score or 0.0) + (1.0 if candidate.get("entity_mentioned") else 0.0),
            })
        retrieved.sort(key=lambda item: (item["rank"], item["published_at"]), reverse=True)
        top_k = max(1, min(get_settings().financialbert_news_top_k, 20))
        selected = rerank_company_news(company_row["name"], retrieved, top_k)
        logger.info(
            "Company news retrieval ticker=%s matched=%d selected=%s",
            ticker, len(retrieved), [(item["id"], item["relevance_score"]) for item in selected],
        )
        if not selected:
            return {"ticker": ticker, "company": company_row["name"], "sector": company_row["sector"],
                    "history": history, "latest_price": history[-1]["close"],
                    "previous_close": history[-2]["close"] if len(history) > 1 else None,
                    "daily_change": history[-1]["close"] / history[-2]["close"] - 1 if len(history) > 1 else None,
                    "prediction": None, "news_used": [], "status": "no_relevant_news"}

        context = ". ".join(item["description"] for item in selected)
        result = predict_expected_return(context)
        logger.info(
            "Company forecast complete ticker=%s status=%s expected_return=%s news_count=%d",
            ticker, result.get("status"), result.get("expected_return"), len(selected),
        )
        latest_close = history[-1]["close"]
        expected_return = result.get("expected_return")
        prediction = None if expected_return is None else {
            "expected_return": expected_return,
            "forecast_price": latest_close * (1 + expected_return),
            "as_of": history[-1]["date"],
            "horizon_days": 30,
        }
        return {
            "ticker": ticker,
            "company": company_row["name"],
            "sector": company_row["sector"],
            "history": history,
            "latest_price": history[-1]["close"],
            "previous_close": history[-2]["close"] if len(history) > 1 else None,
            "daily_change": (
                history[-1]["close"] / history[-2]["close"] - 1 if len(history) > 1 else None
            ),
            "prediction": prediction,
            "news_used": [{key: value for key, value in item.items() if key != "rank"} for item in selected],
            "status": result["status"],
            "model": result.get("model"),
            "model_artifact": result.get("model_artifact"),
            "method": "Company-linked article descriptions reranked for issuer impact, concatenated, then passed to FinancialBERT Model v2 regression",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Company prediction unavailable: {exc}") from exc


@router.get("/universe/us-listed")
def us_listed_universe(refresh: bool = Query(default=False)) -> dict:
    """Return current Nasdaq Trader symbols across Nasdaq and other venues."""
    try:
        securities, retrieved_at = get_us_listed_universe(force_refresh=refresh)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not refresh U.S.-listed universe: {exc}") from exc
    return {
        "count": len(securities),
        "source": "Nasdaq Trader Symbol Directory",
        "source_url": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt",
        "filters": {"nasdaq_traded": "Y", "test_issue": "N", "etf": "N"},
        "retrieved_at": retrieved_at,
        "securities": securities,
    }


@router.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict:
    try:
        result = analyze_headline(request.headline, request.summary)
        result["impact_predictions"] = []
        return result
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"News analysis unavailable: {exc}") from exc


@router.get("/news", response_model=list[NewsOut])
def list_news(
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=100),
    before: datetime | None = Query(default=None),
    sentiment: str | None = Query(default=None, pattern="^(positive|negative|neutral)$"),
    ticker: str | None = None,
    useful_only: bool = False,
    response: Response = None,
    session: Session = Depends(get_db),
) -> list[NewsArticle]:
    if response is not None:
        # Read persisted rows with short-lived HTTP caching; periodic
        # revalidation still exposes newly ingested stories promptly.
        response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=60"
    logger.info("News page requested cursor=%s limit=%d useful_only=%s ticker=%s", cursor, limit, useful_only, ticker)
    query = select(NewsArticle).order_by(desc(NewsArticle.published_at), desc(NewsArticle.ingested_at))
    if sentiment:
        query = query.where(NewsArticle.sentiment == sentiment)
    if before is not None and cursor is None:
        query = query.where(NewsArticle.published_at < before)
    wanted = ticker.upper() if ticker else None
    articles = []
    if cursor:
        try:
            published_text, ingested_text, article_id_text = cursor.rsplit("|", 2)
            cursor_published = datetime.fromisoformat(published_text) if published_text else None
            cursor_ingested = datetime.fromisoformat(ingested_text)
            cursor_id = int(article_id_text)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail="Invalid news cursor") from exc
        if cursor_published is None:
            query = query.where(NewsArticle.published_at.is_(None)).where(
                or_(NewsArticle.ingested_at < cursor_ingested,
                    and_(NewsArticle.ingested_at == cursor_ingested, NewsArticle.id < cursor_id))
            )
        else:
            query = query.where(or_(
                NewsArticle.published_at < cursor_published,
                and_(NewsArticle.published_at == cursor_published, NewsArticle.ingested_at < cursor_ingested),
                and_(NewsArticle.published_at == cursor_published, NewsArticle.ingested_at == cursor_ingested,
                     NewsArticle.id < cursor_id),
                NewsArticle.published_at.is_(None),
            ))
    classified = False
    # Iterate in bounded batches. The filter can discard many rows, so do not
    # let the first page of raw DB rows prevent finding a full page of matches.
    batch_size = max(limit + 1, 100)
    scan_offset = 0
    exhausted = False
    while len(articles) < limit + 1 and not exhausted:
      batch = session.scalars(query.limit(batch_size).offset(scan_offset)).all()
      if not batch:
          break
      scan_offset += len(batch)
      exhausted = len(batch) < batch_size
      for article in batch:
        # Stored classifications are model outputs; hydrating issuer evidence
        # here must not trigger the expensive relevance model per page read.
        article = review_stored_article(article, refresh_usefulness=False)
        if not article.usefulness or (article.usefulness or {}).get("method") not in {
            "pretrained_financial_relevance_regression", "model_disabled", "model_load_error",
            "model_inference_error", "model_error",
            "archive_only_pending_enrichment",
        }:
            article.usefulness = _classify_usefulness(article.title, 0)
            session.add(article)
            classified = True
        if useful_only and (article.usefulness or {}).get("label") != "useful":
            continue
        if wanted and not any(candidate.get("ticker", "").upper() == wanted for candidate in article.ticker_candidates):
            continue
        articles.append(article)
        if len(articles) >= limit + 1:
            break
    has_more = len(articles) > limit
    articles = articles[:limit]
    next_cursor = None
    if articles and has_more:
        last = articles[-1]
        published = last.published_at.isoformat() if last.published_at else ""
        next_cursor = f"{published}|{last.ingested_at.isoformat()}|{last.id}"
    if response is not None:
        response.headers["X-Has-More"] = str(has_more).lower()
        if next_cursor:
            response.headers["X-Next-Cursor"] = next_cursor
    logger.info("News page returned cursor=%s count=%d has_more=%s", cursor, len(articles), has_more)
    if classified:
        session.commit()
    return articles


@router.get("/news/ingestion-status")
def news_ingestion_status(session: Session = Depends(get_db)) -> dict:
    state = session.get(IngestionState, 1)
    cached_model_status = financial_relevance_status()
    return {
        "enabled": get_settings().news_ingest_enabled,
        "poll_minutes": get_settings().news_poll_minutes,
        "latest_attempt_at": state.latest_attempt_at if state else None,
        "latest_success_at": state.latest_success_at if state else None,
        "archive_day": state.archive_day if state else None,
        "last_error": state.last_error if state else None,
        "last_result": state.last_result if state else None,
        "classifier": cached_model_status,
    }


@router.post("/news/ingest")
def ingest(request: IngestRequest, session: Session = Depends(get_db)) -> dict:
    try:
        ticker_query = f'"{request.ticker.upper()}" stock OR shares' if request.ticker else None
        logger.info("Manual ingestion requested limit=%d ticker=%s", request.limit, request.ticker)
        result = ingest_latest(session, request.limit, ticker_query)
        logger.info("Manual ingestion complete result=%s", result)
        return result
    except Exception as exc:
        session.rollback()
        logger.exception("Manual news ingestion failed")
        raise HTTPException(status_code=502, detail=f"News ingestion failed: {exc}") from exc
