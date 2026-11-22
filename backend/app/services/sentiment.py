"""Bounded, persisted FinBERT inference for already-stored relevant stories."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import logging
from threading import BoundedSemaphore, Lock

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import NewsArticle
from app.db.session import get_engine
from app.ml.finbert import ModelUnavailableError, classify_sentiment

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="news-finbert")
_capacity = BoundedSemaphore(64)
_lock = Lock()
_scheduled: set[int] = set()


def _infer_article(article_id: int) -> None:
    try:
        with Session(get_engine()) as session:
            article = session.get(NewsArticle, article_id)
            if article is None or article.sentiment_status == "processed":
                return
            article.sentiment_status = "processing"
            article.sentiment_inferred_at = datetime.now(timezone.utc)
            article.sentiment_error = None
            session.commit()

            try:
                result = classify_sentiment(article.title)
                label = str(result.get("label", "")).lower()
                scores = result.get("scores")
                if label not in {"positive", "negative", "neutral"} or not isinstance(scores, dict):
                    raise ValueError("FinBERT returned an invalid sentiment response")
                probabilities = {str(key).lower(): float(value) for key, value in scores.items()}
                if not probabilities or any(value < 0 or value > 1 for value in probabilities.values()):
                    raise ValueError("FinBERT returned invalid class probabilities")
                article.sentiment = label
                article.sentiment_score = float(result.get("score", probabilities.get(label, 0.0)))
                article.sentiment_scores = probabilities
                article.sentiment_model = str(result.get("model") or get_settings().finbert_model_id)
                article.sentiment_model_version = result.get("model_version")
                article.sentiment_status = "processed"
            except ModelUnavailableError as exc:
                article.sentiment_status = "model_unavailable"
                article.sentiment_error = str(exc)[:500]
                article.sentiment = article.sentiment_score = article.sentiment_scores = None
                article.sentiment_model_version = None
            except Exception as exc:
                article.sentiment_status = "inference_failed"
                article.sentiment_error = str(exc)[:500]
                article.sentiment = article.sentiment_score = article.sentiment_scores = None
                article.sentiment_model_version = None
            article.sentiment_inferred_at = datetime.now(timezone.utc)
            session.commit()
    except Exception:
        logger.exception("Could not persist FinBERT result article_id=%s", article_id)
    finally:
        with _lock:
            _scheduled.discard(article_id)
        _capacity.release()


def enqueue_sentiment(article_ids: list[int]) -> int:
    """Queue up to 64 pending article jobs; never blocks ingestion on inference."""
    queued = 0
    for article_id in article_ids:
        with _lock:
            if article_id in _scheduled:
                continue
            if not _capacity.acquire(blocking=False):
                continue
            _scheduled.add(article_id)
        try:
            _executor.submit(_infer_article, article_id)
            queued += 1
        except RuntimeError:
            with _lock:
                _scheduled.discard(article_id)
            _capacity.release()
            logger.exception("Could not queue FinBERT inference article_id=%s", article_id)
    return queued


def process_pending_sentiment(session: Session, limit: int = 20) -> int:
    """Retry a bounded set of stories left pending after queue saturation/restart."""
    stale_before = datetime.now(timezone.utc) - timedelta(minutes=10)
    rows = session.query(NewsArticle.id).filter(
        (NewsArticle.sentiment_status == "not_processed")
        | ((NewsArticle.sentiment_status == "processing") & (
            NewsArticle.sentiment_inferred_at.is_(None)
            | (NewsArticle.sentiment_inferred_at < stale_before)
        ))
    ).order_by(NewsArticle.id.asc()).limit(max(1, min(limit, 100))).all()
    return enqueue_sentiment([row[0] for row in rows])
