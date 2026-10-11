"""Persisted news articles and model outputs."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")


class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (UniqueConstraint("url", name="uq_news_articles_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False, default="Google News RSS")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_scores: Mapped[dict | None] = mapped_column(_JSON, nullable=True)
    ticker_candidates: Mapped[list] = mapped_column(_JSON, nullable=False)
    impact_predictions: Mapped[list] = mapped_column(_JSON, nullable=False, default=list)
    usefulness: Mapped[dict | None] = mapped_column(_JSON, nullable=True)


class IngestionState(Base):
    """Durable latest-poll and archive-backfill status for the news worker."""

    __tablename__ = "ingestion_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    latest_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archive_day: Mapped[str | None] = mapped_column(String(10))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_result: Mapped[dict | None] = mapped_column(_JSON, nullable=True)
    relevance_backfill_before_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
