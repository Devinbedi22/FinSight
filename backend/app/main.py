"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.api.health import router as health_router
from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.db.session import get_engine
from app.db.models import NewsArticle
from app.services.news import backfill_missing_impacts, bootstrap_news_archive, ingest_latest, refresh_stored_usefulness

settings = get_settings()
scheduler = BackgroundScheduler(daemon=True)
logger = logging.getLogger(__name__)


def _scheduled_ingest() -> None:
    limit = max(1, min(settings.news_ingest_limit, 100))
    logger.info("Scheduled news ingestion starting (limit=%d)", limit)
    try:
        with Session(get_engine()) as session:
            archive_result = None
            stored_count = session.query(NewsArticle.id).count()
            if stored_count < settings.news_archive_bootstrap_articles:
                logger.info(
                    "News archive below target: stored=%d target=%d; resuming archive bootstrap",
                    stored_count, settings.news_archive_bootstrap_articles,
                )
                archive_result = bootstrap_news_archive(session)
            relevance_backfilled = refresh_stored_usefulness(session, limit=25)
            backfilled = backfill_missing_impacts(session, limit=50)
            result = ingest_latest(session, limit=limit)
        logger.info(
            "Scheduled news ingestion complete: archive=%s fetched=%d created=%d skipped=%d backfilled_relevance=%d backfilled_impacts=%d",
            archive_result, result["fetched"], result["created"], result["skipped"], relevance_backfilled, backfilled,
        )
    except Exception:
        logger.exception("Scheduled news ingestion failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.news_ingest_enabled:
        logger.info(
            "Automatic news ingestion enabled: every %d minutes; first run in 30 seconds",
            max(1, settings.news_poll_minutes),
        )
        scheduler.add_job(
            _scheduled_ingest,
            "interval",
            minutes=max(1, settings.news_poll_minutes),
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30),
            id="financial-news-ingest",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)

app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Has-More", "X-Next-Cursor"],
)
app.include_router(health_router)
app.include_router(v1_router, prefix="/api/v1")
