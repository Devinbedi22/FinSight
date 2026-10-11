"""Integration contract: persisted impact classes are served to the frontend."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.api.v1.news import company_prediction
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import NewsArticle
from app.db.session import get_db
from app.main import app
from app.services.news import analyze_headline, add_impact_predictions, ingest_latest, review_stored_article, _classify_usefulness, _default_rss_url, _explicitly_named_companies, _feed_queries, _ingestion_lock, _reported_direction


class NewsApiContractTest(unittest.TestCase):
    def test_reported_hammered_share_move_overrides_positive_model_estimate(self) -> None:
        headline = "SpaceX deal to acquire spectrum license hammers shares of AT&T, Verizon and T-Mobile - CNBC"
        companies = {
            "T": "AT&T Inc.",
            "VZ": "Verizon Communications Inc. Common Stock",
            "TMUS": "T-Mobile US, Inc. - Common Stock",
        }
        for ticker, name in companies.items():
            with self.subTest(ticker=ticker):
                self.assertEqual(_reported_direction(headline, ticker, name), "negative")

        article = NewsArticle(
            id=24, title=headline, summary=None, url="urn:reported-move", source="test",
            published_at=None, sentiment=None, sentiment_score=None, sentiment_scores=None,
            ticker_candidates=[
                {"ticker": ticker, "name": name, "entity_mentioned": True,
                 "security_type": "common_or_adr"}
                for ticker, name in companies.items()
            ] + [{"ticker": "T$C", "name": "AT&T preferred stock",
                  "entity_mentioned": True, "security_type": "preferred"}],
            impact_predictions=[
                {"ticker": ticker, "impact": "positive", "status": "financialbert_model_v2",
                 "expected_return": 0.03}
                for ticker in (*companies.keys(), "T$C")
            ],
        )
        with patch("app.services.news.get_sp500_universe", return_value=[]):
            review_stored_article(article)
        corrected = {prediction["ticker"]: prediction for prediction in article.impact_predictions}
        for ticker in companies:
            self.assertEqual(corrected[ticker]["impact"], "negative")
            self.assertEqual(corrected[ticker]["status"], "reported_market_move")
            self.assertIsNone(corrected[ticker]["expected_return"])
        self.assertEqual(corrected["T$C"]["impact"], "positive")

    def test_default_feed_discovers_broad_news_and_uses_distinct_archive_windows(self) -> None:
        queries = _feed_queries()
        self.assertIsNone(queries[0])  # unfiltered Google News headlines
        self.assertEqual(len(queries), 32)
        self.assertIn("news after:", queries[1])
        self.assertNotEqual(queries[1], queries[2])

    def test_company_news_reranker_keeps_company_relevant_document(self) -> None:
        from app.services.news import rerank_company_news
        docs = [
            {"id": 1, "description": "Unrelated broad market news", "explicit_company_mention": False, "relevance_score": 0.9},
            {"id": 2, "description": "Apple reports quarterly earnings", "explicit_company_mention": True, "relevance_score": 0.1},
        ]
        with patch("app.services.news.get_settings") as settings:
            settings.return_value.cohere_api_key = None
            self.assertEqual(rerank_company_news("Apple Inc.", docs, 1)[0]["id"], 2)

    def test_persistent_archive_cursor_advances_by_day(self) -> None:
        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        response = type("Response", (), {"text": "feed", "raise_for_status": lambda self: None})()
        feed = type("Feed", (), {"entries": []})()
        with Session(engine) as session, patch("app.services.news.httpx.get", return_value=response), \
                patch("app.services.news.feedparser.parse", return_value=feed):
            first = ingest_latest(session, limit=1)
            first_day = first["archive_day"]
            second = ingest_latest(session, limit=1)
            self.assertNotEqual(first_day, second["archive_day"])
        engine.dispose()

    def test_old_literal_time_filter_configuration_falls_back_to_broad_headlines(self) -> None:
        with patch("app.services.news.get_settings") as settings:
            settings.return_value.google_news_rss_url = (
                "https://news.google.com/rss/search?q=when%3A30d&hl=en-US"
            )
            self.assertIn("/rss?", _default_rss_url())

    def test_usefulness_separates_market_news_from_generic_court_story(self) -> None:
        def score(text):
            value = 0.8 if "stocks" in text else 0.2
            return {"label": "useful" if value >= 0.55 else "not_useful", "score": value,
                    "threshold": 0.55, "model": "test-classifier", "method": "pretrained_financial_relevance_regression"}
        with patch("app.services.news.score_financial_relevance", side_effect=score):
            market = _classify_usefulness("Tech stocks struggle on AI spending worries and elevated bond yields", 0)
            court = _classify_usefulness("Supreme Court rules against Colorado conversion therapy law for minors", 0)
        self.assertEqual(market["label"], "useful")
        self.assertEqual(court["label"], "not_useful")

    def test_ambiguous_ice_ticker_requires_financial_context(self) -> None:
        universe = [{
            "ticker": "ICE", "name": "Intercontinental Exchange Inc. Common Stock",
            "listing_exchange": "N", "listing_exchange_name": "NYSE",
        }]
        unrelated = "ICE agent shoots man in New York City"
        market = "ICE shares rise after earnings beat"
        self.assertEqual(_explicitly_named_companies(unrelated, universe), [])
        self.assertEqual(
            [company["ticker"] for company in _explicitly_named_companies(market, universe)],
            ["ICE"],
        )

    def test_news_publisher_name_does_not_match_news_corporation_tickers(self) -> None:
        universe = [
            {"ticker": "NWS", "name": "News Corporation Class B Common Stock"},
            {"ticker": "NWSA", "name": "News Corporation Class A Common Stock"},
        ]
        headline = "Man shot in New York City - ABC News - Breaking News"
        self.assertEqual(_explicitly_named_companies(headline, universe), [])

    def test_irrelevant_headline_skips_stock_retrieval(self) -> None:
        with patch("app.services.news.get_us_listed_universe", return_value=([{
            "ticker": "ICE", "name": "Intercontinental Exchange Inc. Common Stock",
            "listing_exchange": "N", "listing_exchange_name": "NYSE",
        }], "test")), patch("app.services.news.get_sp500_universe", return_value=[{
            "ticker": "ICE", "name": "Intercontinental Exchange Inc. Common Stock",
            "sector": "Financials",
        }]), patch("app.services.news.retrieve_tickers") as retrieve:
            result = analyze_headline("ICE agent shoots man in New York City")
        self.assertEqual(result["usefulness"]["label"], "not_useful")
        self.assertEqual(result["ticker_candidates"], [])
        retrieve.assert_not_called()

    def test_named_companies_are_recovered_and_crude_cl_is_not_colgate(self) -> None:
        universe = [
            {"ticker": "NVDA", "name": "NVIDIA Corporation - Common Stock", "listing_exchange": "Q", "listing_exchange_name": "Nasdaq"},
            {"ticker": "ORCL", "name": "Oracle Corporation Common Stock", "listing_exchange": "N", "listing_exchange_name": "NYSE"},
            {"ticker": "CRWV", "name": "CoreWeave, Inc. - Class A Common Stock", "listing_exchange": "Q", "listing_exchange_name": "Nasdaq"},
            {"ticker": "CL", "name": "Colgate-Palmolive Company Common Stock", "listing_exchange": "N", "listing_exchange_name": "NYSE"},
        ]
        with patch("app.services.news.get_us_listed_universe", return_value=(universe, "test")), \
                patch("app.services.news.get_sp500_universe", return_value=[
                    {"ticker": item["ticker"], "name": item["name"], "sector": "Technology"}
                    for item in universe
                ]), \
                patch("app.services.news.retrieve_tickers", return_value=[{"ticker": "CL", "relevance_score": 0.94}]):
            result = analyze_headline(
                "Nvidia, Oracle and CoreWeave shares sank after OpenAI news as crude prices jumped"
            )

        by_ticker = {item["ticker"]: item for item in result["ticker_candidates"]}
        self.assertTrue({"NVDA", "ORCL", "CRWV", "CL"}.issubset(by_ticker))
        for ticker in ("NVDA", "ORCL", "CRWV"):
            self.assertTrue(by_ticker[ticker]["entity_mentioned"])
            self.assertEqual(by_ticker[ticker]["candidate_source"], "exact_company_name")
        self.assertFalse(by_ticker["CL"]["entity_mentioned"])

    def test_model_runs_for_every_retrieved_ticker_including_ambiguous_symbols(self) -> None:
        now = datetime.now(timezone.utc)
        article = NewsArticle(
            title="Dow Jones futures rise after AI stocks tumble; SpaceX deal hammers shares of Verizon, AT&T and T-Mobile",
            summary=None,
            url="urn:telecom-news",
            source="test",
            published_at=now,
            sentiment="negative",
            sentiment_score=0.9,
            sentiment_scores={"negative": 0.9},
            ticker_candidates=[
                {"ticker": "VZ", "name": "Verizon Communications Inc. Common Stock", "entity_mentioned": True},
                {"ticker": "T", "name": "AT&T Inc.", "entity_mentioned": True},
                {"ticker": "TMUS", "name": "T-Mobile US, Inc. - Common Stock", "entity_mentioned": True},
            ],
            impact_predictions=[],
        )
        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        model_result = {"impact": "negative", "expected_return": -0.02, "status": "financialbert_model_v2"}
        with Session(engine) as session, patch("app.services.news.classify_impact", return_value=model_result) as model:
            impacts = add_impact_predictions(session, article)
        self.assertEqual([item["impact"] for item in impacts], ["negative"] * 3)
        self.assertEqual([item["status"] for item in impacts], ["reported_market_move"] * 3)
        self.assertEqual(model.call_count, 3)

        article.title = "S&P 500 falls as crude prices jump"
        article.ticker_candidates = [{
            "ticker": "CL", "name": "Colgate-Palmolive Company Common Stock", "entity_mentioned": False,
        }]
        with Session(engine) as session, patch("app.services.news.classify_impact", return_value=model_result) as model:
            impacts = add_impact_predictions(session, article)
        self.assertEqual(impacts[0]["impact"], "negative")
        self.assertEqual(impacts[0]["status"], "financialbert_model_v2")
        model.assert_called_once()
        engine.dispose()

    def test_indirect_market_news_uses_available_company_sector(self) -> None:
        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        article = NewsArticle(
            title="A celebrity opens a new restaurant",
            summary=None,
            url="urn:tech-news",
            source="test",
            published_at=datetime.now(timezone.utc),
            sentiment="negative",
            sentiment_score=0.8,
            sentiment_scores={"negative": 0.8},
            ticker_candidates=[{
                "ticker": "TSM", "name": "Taiwan Semiconductor Manufacturing Company",
                "relevance_score": 0.12, "business_sector": "Information Technology",
                "security_type": "common_or_adr", "entity_mentioned": False,
            }],
            impact_predictions=[],
            usefulness={"label": "not_useful", "reason": "test non-market story"},
        )
        with Session(engine) as session, patch(
            "app.services.news.classify_impact",
            return_value={"impact": "negative", "status": "financialbert_model_v2"},
        ) as model:
            predictions = add_impact_predictions(session, article)
        self.assertEqual(predictions[0]["impact"], "negative")
        self.assertEqual(predictions[0]["evidence_status"], "indirect_company_profile_model_estimate")
        self.assertIn("sector: Information Technology", model.call_args.args[0])
        engine.dispose()

    def test_ingestion_infers_before_persisting_and_serializes_runs(self) -> None:
        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        entry = {
            "link": "https://example.test/new",
            "title": "New company headline",
            "summary": "Summary",
            "source": {"title": "Test News"},
            "published": "Thu, 08 Oct 2026 12:00:00 GMT",
        }
        response = type("Response", (), {"text": "feed", "raise_for_status": lambda self: None})()
        with Session(engine) as session, \
                patch("app.services.news.httpx.get", return_value=response), \
                patch("app.services.news.feedparser.parse", return_value=type("Feed", (), {"entries": [entry]})()), \
                patch("app.services.news.analyze_headline", return_value={
                    "ticker_candidates": [],
                    "usefulness": {"label": "useful", "reason": "test"},
                }), \
                patch("app.services.news.add_impact_predictions", return_value=[]) as impact:
            result = ingest_latest(session, limit=1)
            self.assertEqual(result["created"], 1)
            self.assertEqual(session.query(NewsArticle).count(), 1)
            impact.assert_called_once()
            stored = session.query(NewsArticle).one()
            self.assertIsNone(stored.sentiment)
            self.assertEqual(stored.impact_predictions, [])

        self.assertTrue(_ingestion_lock.acquire(blocking=False))
        try:
            with self.assertRaisesRegex(RuntimeError, "already running"):
                ingest_latest(None, limit=1)
        finally:
            _ingestion_lock.release()
        engine.dispose()

    def test_impact_context_uses_only_prior_ticker_linked_articles(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        now = datetime.now(timezone.utc)
        with Session(engine) as session:
            prior = NewsArticle(
                title="Earlier HCA hospital drug costs article", summary=None,
                url="https://example.test/prior", source="test",
                published_at=now - timedelta(days=1), sentiment="neutral", sentiment_score=0.5,
                sentiment_scores={"neutral": 0.5},
                ticker_candidates=[{"ticker": "HCA", "name": "HCA Healthcare"}],
                impact_predictions=[],
            )
            unrelated = NewsArticle(
                title="Earlier unrelated AAPL article", summary=None,
                url="https://example.test/unrelated", source="test",
                published_at=now - timedelta(hours=12), sentiment="neutral", sentiment_score=0.5,
                sentiment_scores={"neutral": 0.5},
                ticker_candidates=[{"ticker": "AAPL", "name": "Apple Inc."}],
                impact_predictions=[],
            )
            future = NewsArticle(
                title="Later HCA article", summary=None,
                url="https://example.test/future", source="test",
                published_at=now + timedelta(days=1), sentiment="neutral", sentiment_score=0.5,
                sentiment_scores={"neutral": 0.5},
                ticker_candidates=[{"ticker": "HCA", "name": "HCA Healthcare"}],
                impact_predictions=[],
            )
            session.add_all([prior, unrelated, future])
            session.flush()
            current = NewsArticle(
                id=-1, title="Current HCA news", summary=None, url="urn:current", source="test",
                published_at=now, sentiment="neutral", sentiment_score=0.5,
                sentiment_scores={"neutral": 0.5},
                ticker_candidates=[{"ticker": "HCA", "name": "HCA Healthcare"}],
                impact_predictions=[],
            )
            with patch("app.services.news.classify_impact", return_value={"impact": "negative", "status": "test"}) as model:
                result = add_impact_predictions(session, current)

        self.assertEqual(result[0]["context_count"], 1)
        self.assertEqual(result[0]["context_article_ids"], [prior.id])
        model.assert_called_once()
        self.assertIn("Earlier HCA hospital drug costs article", model.call_args.args[0])
        self.assertNotIn("Earlier unrelated AAPL article", model.call_args.args[0])
        self.assertNotIn("Later HCA article", model.call_args.args[0])
        engine.dispose()

    def test_news_endpoint_returns_financialbert_impact_fields(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(NewsArticle(
                title="Court criticizes hospital drug prices",
                summary=None,
                url="https://example.test/hospital-news",
                source="test",
                published_at=None,
                sentiment="negative",
                sentiment_score=0.91,
                sentiment_scores={"negative": 0.91, "neutral": 0.07, "positive": 0.02},
                ticker_candidates=[{"ticker": "HCA", "name": "HCA Healthcare", "relevance_score": 0.8}],
                impact_predictions=[{
                    "ticker": "HCA",
                    "impact": "negative",
                    "status": "financialbert_model_v2",
                    "model": "techandy42/FinancialBERT Model v2",
                    "context_count": 2,
                    "context_article_ids": [1, 2],
                }],
            ))
            session.commit()

        def override_db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        try:
            response = TestClient(app).get("/api/v1/news?limit=10")
        finally:
            app.dependency_overrides.pop(get_db, None)
            engine.dispose()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, max-age=30, stale-while-revalidate=60")
        payload = response.json()
        self.assertEqual(payload[0]["ticker_candidates"][0]["ticker"], "HCA")
        self.assertEqual(payload[0]["impact_predictions"][0]["impact"], "negative")
        self.assertEqual(payload[0]["impact_predictions"][0]["model"], "techandy42/FinancialBERT Model v2")

    def test_news_feed_includes_all_stories_by_default(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            for title, url in (
                ("Supreme Court rules against conversion therapy law", "https://example.test/unrelated"),
                ("Tech stocks slide after earnings warning", "https://example.test/markets"),
            ):
                session.add(NewsArticle(
                    title=title, summary=None, url=url, source="test", published_at=None,
                    sentiment="neutral", sentiment_score=0.5,
                    sentiment_scores={"neutral": 0.5}, ticker_candidates=[], impact_predictions=[],
                ))
            session.commit()

        def override_db():
            with Session(engine) as session:
                yield session

        def model_score(text, _count=0):
            label = "useful" if "stocks slide" in text else "not_useful"
            return {"label": label, "score": 0.8 if label == "useful" else 0.1,
                    "threshold": 0.55, "model": "test", "method": "pretrained_financial_relevance_regression"}
        app.dependency_overrides[get_db] = override_db
        try:
            with patch("app.api.v1.news._classify_usefulness", side_effect=model_score):
                response = TestClient(app).get("/api/v1/news?limit=10")
                useful_only_response = TestClient(app).get("/api/v1/news?limit=10&useful_only=true")
        finally:
            app.dependency_overrides.pop(get_db, None)
            engine.dispose()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)
        self.assertEqual([article["url"] for article in useful_only_response.json()], ["https://example.test/markets"])

    def test_news_cursor_is_available_to_cross_origin_frontend(self) -> None:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        now = datetime.now(timezone.utc)
        with Session(engine) as session:
            for index in range(25):
                session.add(NewsArticle(
                    title=f"Market story {index}", summary=None, url=f"https://example.test/{index}",
                    source="test", published_at=now - timedelta(minutes=index),
                    usefulness={"label": "useful", "method": "pretrained_financial_relevance_regression",
                                "ticker_inference": "stocky-sp500-v1"},
                    ticker_candidates=[], impact_predictions=[],
                ))
            session.commit()

        def override_db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        try:
            response = TestClient(app).get(
                "/api/v1/news?limit=10&useful_only=true", headers={"Origin": "http://localhost:3000"}
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
            engine.dispose()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 10)
        self.assertEqual(response.headers["x-has-more"], "true")
        self.assertIn("x-next-cursor", response.headers)
        exposed = response.headers["access-control-expose-headers"].lower()
        self.assertIn("x-has-more", exposed)
        self.assertIn("x-next-cursor", exposed)

    def test_company_prediction_uses_retrieved_headlines_and_returns_regression_value(self) -> None:
        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        now = datetime.now(timezone.utc)
        with Session(engine) as session:
            session.add(NewsArticle(
                title="Apple shares fall after earnings outlook", summary=None,
                url="https://example.test/aapl", source="test", published_at=now,
                sentiment="negative", sentiment_score=0.8, sentiment_scores={"negative": 0.8},
                ticker_candidates=[{
                    "ticker": "AAPL", "name": "Apple Inc. Common Stock", "relevance_score": 0.81,
                    "entity_mentioned": True,
                }], impact_predictions=[],
                usefulness={"label": "useful", "reason": "test"},
            ))
            session.commit()
            with patch("app.api.v1.news.get_sp500_universe", return_value=[{
                "ticker": "AAPL", "name": "Apple Inc.", "sector": "Information Technology",
            }]), patch("app.api.v1.news.get_company_price_history", return_value=[
                {"date": "2026-10-08", "close": 100.0}, {"date": "2026-10-09", "close": 101.0},
            ]), patch("app.api.v1.news.predict_expected_return", return_value={
                "status": "financialbert_model_v2", "expected_return": 0.125,
                "model": "techandy42/FinancialBERT Model v2", "model_artifact": "weights.pth",
            }) as predictor:
                result = company_prediction("AAPL", session)

        self.assertEqual(result["prediction"]["expected_return"], 0.125)
        self.assertEqual(result["prediction"]["forecast_price"], 113.625)
        self.assertEqual(len(result["history"]), 2)
        self.assertEqual(result["news_used"][0]["title"], "Apple shares fall after earnings outlook")
        self.assertIn("Apple shares fall", predictor.call_args.args[0])
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
