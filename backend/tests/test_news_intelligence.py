"""Tests for persisted sentiment states, headline events, and canonical URL deduplication."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import NewsArticle
from app.services.news import canonicalize_news_url, extract_financial_events
from app.services import sentiment as sentiment_service
from app.ml.finbert import InferenceError, ModelUnavailableError


class NewsIntelligenceTest(unittest.TestCase):
    def test_url_normalization_removes_trackers_and_preserves_story_parameters(self) -> None:
        self.assertEqual(
            canonicalize_news_url("HTTPS://Example.com/story/?utm_source=feed&id=7&fbclid=abc#top"),
            "https://example.com/story?id=7",
        )

    def test_event_extraction_records_source_and_article_evidence_without_confidence_claim(self) -> None:
        published = datetime(2026, 11, 21, tzinfo=timezone.utc)
        events = extract_financial_events(
            "Apple reports quarterly earnings and raises full-year guidance",
            [{"ticker": "AAPL", "name": "Apple Inc."}], 42, published, "Example News",
        )
        self.assertEqual({event["event_type"] for event in events}, {"earnings_announcement", "guidance"})
        for event in events:
            self.assertEqual(event["supporting_article_id"], 42)
            self.assertEqual(event["published_at"], published.isoformat())
            self.assertEqual(event["related_companies"][0]["ticker"], "AAPL")
            self.assertEqual(event["supporting_evidence"], "Apple reports quarterly earnings and raises full-year guidance")
            self.assertNotIn("confidence", event)

    def _article_engine(self):
        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(NewsArticle(
                title="Apple reports quarterly results", url="https://example.test/a", source="test",
                published_at=datetime.now(timezone.utc), ticker_candidates=[{"ticker": "AAPL"}],
            ))
            session.commit()
            article_id = session.query(NewsArticle.id).one()[0]
        return engine, article_id

    def test_finbert_success_persists_label_probabilities_and_model(self) -> None:
        engine, article_id = self._article_engine()
        with patch("app.services.sentiment.get_engine", return_value=engine), patch(
            "app.services.sentiment.classify_sentiment",
            return_value={"label": "positive", "score": 0.91,
                          "scores": {"positive": 0.91, "negative": 0.02, "neutral": 0.07},
                          "model": "ProsusAI/finbert", "model_version": "revision123"},
        ) as classify:
            sentiment_service._capacity.acquire()
            sentiment_service._infer_article(article_id)
            sentiment_service._capacity.acquire()
            sentiment_service._infer_article(article_id)
            classify.assert_called_once()
        with Session(engine) as session:
            article = session.get(NewsArticle, article_id)
            self.assertEqual(article.sentiment_status, "processed")
            self.assertEqual(article.sentiment, "positive")
            self.assertAlmostEqual(article.sentiment_scores["positive"], 0.91)
            self.assertEqual(article.sentiment_model, "ProsusAI/finbert")
            self.assertEqual(article.sentiment_model_version, "revision123")
            self.assertIsNotNone(article.sentiment_inferred_at)
            self.assertIsNone(article.sentiment_error)
        engine.dispose()

    def test_model_unavailable_and_inference_failure_are_distinct_and_not_fabricated(self) -> None:
        for exception, expected_status in (
            (ModelUnavailableError("missing"), "model_unavailable"),
            (InferenceError("failed"), "inference_failed"),
        ):
            with self.subTest(status=expected_status):
                engine, article_id = self._article_engine()
                with patch("app.services.sentiment.get_engine", return_value=engine), patch(
                    "app.services.sentiment.classify_sentiment", side_effect=exception,
                ):
                    sentiment_service._capacity.acquire()
                    sentiment_service._infer_article(article_id)
                with Session(engine) as session:
                    article = session.get(NewsArticle, article_id)
                    self.assertEqual(article.sentiment_status, expected_status)
                    self.assertIsNone(article.sentiment)
                    self.assertIsNone(article.sentiment_score)
                    self.assertIsNone(article.sentiment_scores)
                    self.assertTrue(article.sentiment_error)
                    self.assertIsNotNone(article.sentiment_inferred_at)
                engine.dispose()

    def test_pending_and_stale_processing_jobs_are_recovered_from_persistence(self) -> None:
        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            pending = NewsArticle(
                title="Pending headline", url="https://example.test/pending", source="test",
                sentiment_status="not_processed", ticker_candidates=[], impact_predictions=[],
            )
            stale = NewsArticle(
                title="Interrupted headline", url="https://example.test/stale", source="test",
                sentiment_status="processing",
                sentiment_inferred_at=datetime.now(timezone.utc) - timedelta(minutes=20),
                ticker_candidates=[], impact_predictions=[],
            )
            fresh = NewsArticle(
                title="Still running headline", url="https://example.test/fresh", source="test",
                sentiment_status="processing", sentiment_inferred_at=datetime.now(timezone.utc),
                ticker_candidates=[], impact_predictions=[],
            )
            session.add_all([pending, stale, fresh])
            session.commit()
            pending_id, stale_id, fresh_id = pending.id, stale.id, fresh.id
            expected_ids = {pending_id, stale_id}
            with patch("app.services.sentiment.enqueue_sentiment", return_value=2) as enqueue:
                queued = sentiment_service.process_pending_sentiment(session, limit=20)
        self.assertEqual(queued, 2)
        queued_ids = set(enqueue.call_args.args[0])
        self.assertEqual(queued_ids, expected_ids)
        self.assertNotIn(fresh_id, queued_ids)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
