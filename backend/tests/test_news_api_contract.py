"""Integration contract: persisted impact classes are served to the frontend."""

import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from fastapi import HTTPException
from app.api.v1.news import company_prediction, companies as companies_endpoint, company_history, company_fundamentals, retry_news_sentiment, company_market_context, company_event_study
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import IngestionState, NewsArticle
from app.db.session import get_db
from app.main import app
from app.services.news import analyze_headline, add_impact_predictions, ingest_latest, review_stored_article, _classify_usefulness, _default_rss_url, _explicitly_named_companies, _feed_queries, _ingestion_lock, _reported_direction
from app.services import market as market_service


class NewsApiContractTest(unittest.TestCase):
    def test_market_context_endpoint_includes_cutoff_and_indicator_contract(self) -> None:
        payload = {"ticker": "AAPL", "as_of_date": "2024-01-05", "indicators": {}, "regime": {"probability": None}}
        with patch("app.api.v1.news.get_company_market_context", return_value=payload) as context:
            result = company_market_context("aapl", as_of=date(2024, 1, 5))
        context.assert_called_once_with("AAPL", as_of=date(2024, 1, 5))
        self.assertIsNone(result["regime"]["probability"])

    def test_event_study_endpoint_contract(self) -> None:
        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            with patch("app.api.v1.news.get_sp500_universe", return_value=[{"ticker": "AAPL"}]), \
                    patch("app.api.v1.news.get_company_event_study", return_value={"events": [], "event_count": 0}) as study:
                result = company_event_study("AAPL", as_of=date(2024, 1, 5), session=session)
            study.assert_called_once_with("AAPL", [], as_of=date(2024, 1, 5))
            self.assertEqual(result["event_count"], 0)
        engine.dispose()

    def test_event_study_maps_directory_provider_failure_to_502(self) -> None:
        with patch("app.api.v1.news.get_sp500_universe", side_effect=RuntimeError("provider unavailable")):
            with self.assertRaises(HTTPException) as raised:
                company_event_study("AAPL", as_of=date(2024, 1, 5))
        self.assertEqual(raised.exception.status_code, 502)

    def test_failed_sentiment_can_be_requeued_once_and_successful_state_is_protected(self) -> None:
        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            article = NewsArticle(
                title="A sourced financial headline", url="https://example.test/retry",
                source="test", sentiment_status="inference_failed",
                ticker_candidates=[], impact_predictions=[],
            )
            session.add(article)
            session.commit()
            article_id = article.id
            with patch("app.api.v1.news.enqueue_sentiment", return_value=1) as enqueue:
                result = retry_news_sentiment(article_id, session)
            self.assertTrue(result["queued"])
            self.assertEqual(result["sentiment_status"], "not_processed")
            enqueue.assert_called_once_with([article_id])
            with self.assertRaises(HTTPException) as raised:
                retry_news_sentiment(article_id, session)
            self.assertEqual(raised.exception.status_code, 409)
        engine.dispose()

    def test_company_search_contract_passes_search_and_pagination_to_service(self) -> None:
        with patch("app.api.v1.news.get_company_market_rows", return_value={"companies": [], "total": 0}) as rows:
            result = companies_endpoint(limit=25, offset=50, search="Apple")
        self.assertEqual(result["total"], 0)
        rows.assert_called_once_with(limit=25, offset=50, search="Apple")

    def test_company_history_response_has_source_and_daily_volume(self) -> None:
        points = [{"date": "2025-01-02", "close": 100.0, "volume": 1234}]
        with patch("app.api.v1.news.get_sp500_universe", return_value=[{"ticker": "AAPL"}]), \
                patch("app.api.v1.news.get_company_price_history", return_value=points) as history:
            result = company_history("aapl", period="3mo")
        history.assert_called_once_with("AAPL", period="3mo")
        self.assertEqual(result["points"], points)
        self.assertEqual(result["status"], "available")
        self.assertIn("Yahoo Finance", result["source"])

    def test_fundamentals_response_can_return_sec_data_without_market_quote(self) -> None:
        payload = {"ticker": "AAPL", "metrics": {"revenue": None}, "source": "SEC EDGAR CompanyFacts"}
        with patch("app.api.v1.news.get_sp500_universe", return_value=[{"ticker": "AAPL"}]), \
                patch("app.api.v1.news.get_settings") as settings, \
                patch("app.api.v1.news.get_company_market_row", side_effect=RuntimeError("quote unavailable")), \
                patch("app.api.v1.news.get_company_fundamentals", return_value=payload) as fundamentals:
            settings.return_value.sec_user_agent = "FinSight tests test@example.com"
            result = company_fundamentals("AAPL")
        fundamentals.assert_called_once_with("AAPL", latest_price=None, latest_price_as_of=None, as_of_date=None)
        self.assertEqual(result["source"], "SEC EDGAR CompanyFacts")
        self.assertIsNone(result["market_price"])

    def test_historical_fundamentals_use_historical_close_and_filing_cutoff(self) -> None:
        cutoff = date(2024, 12, 31)
        payload = {"ticker": "AAPL", "as_of_date": cutoff.isoformat(), "metrics": {}}
        with patch("app.api.v1.news.get_sp500_universe", return_value=[{"ticker": "AAPL"}]), \
                patch("app.api.v1.news.get_settings") as settings, \
                patch("app.api.v1.news.get_company_price_on_or_before", return_value=(100.0, "2024-12-30")) as price, \
                patch("app.api.v1.news.get_company_fundamentals", return_value=payload) as fundamentals:
            settings.return_value.sec_user_agent = "FinSight tests test@example.com"
            result = company_fundamentals("AAPL", as_of=cutoff)
        price.assert_called_once_with("AAPL", cutoff)
        fundamentals.assert_called_once_with(
            "AAPL", latest_price=100.0, latest_price_as_of="2024-12-30", as_of_date=cutoff,
        )
        self.assertEqual(result["market_price_as_of"], "2024-12-30")

    def test_company_search_filters_before_quote_batch_and_paginates_matches(self) -> None:
        universe = [
            {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology"},
            {"ticker": "APLE", "name": "Apple Hospitality REIT", "sector": "Real Estate"},
            {"ticker": "MSFT", "name": "Microsoft Corporation", "sector": "Technology"},
        ]
        with patch("app.services.market.get_sp500_universe", return_value=universe), \
                patch("app.services.market.get_sp500_universe_metadata", return_value={"status": "current"}), \
                patch.object(market_service, "_quote_cache", {}), \
                patch.object(market_service, "_quote_refreshing", set()), \
                patch.object(market_service._quote_executor, "submit") as submit:
            first = market_service.get_company_market_rows(limit=1, offset=0, search="apple")
            second = market_service.get_company_market_rows(limit=1, offset=1, search="APPLE")
        self.assertEqual(first["total"], 2)
        self.assertEqual(first["companies"][0]["ticker"], "AAPL")
        self.assertEqual(second["companies"][0]["ticker"], "APLE")
        self.assertEqual(submit.call_count, 2)

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

    def test_common_company_aliases_need_company_context(self) -> None:
        universe = [
            {"ticker": "AAPL", "name": "Apple Inc. Common Stock"},
            {"ticker": "ICE", "name": "Intercontinental Exchange Inc. Common Stock"},
            {"ticker": "LLY", "name": "Eli Lilly and Company"},
            {"ticker": "KHC", "name": "The Kraft Heinz Company"},
        ]
        fruit_story = "Major supermarkets profit as apple prices increase"
        issuer_story = "Apple reports quarterly earnings and revenue growth"
        immigration_story = "Immigration and Customs Enforcement agents arrest people in New York"
        self.assertEqual(_explicitly_named_companies(fruit_story, universe), [])
        self.assertEqual(
            [company["ticker"] for company in _explicitly_named_companies(issuer_story, universe)],
            ["AAPL"],
        )
        self.assertEqual(_explicitly_named_companies(immigration_story, universe), [])
        issuer_result_headlines = [
            "Eli Lilly reports quarterly financial results",
            "Kraft Heinz reports third quarter 2026 results",
        ]
        matched = [
            [company["ticker"] for company in _explicitly_named_companies(title, universe)]
            for title in issuer_result_headlines
        ]
        self.assertEqual(matched, [["LLY"], ["KHC"]])

    def test_news_publisher_name_does_not_match_news_corporation_tickers(self) -> None:
        universe = [
            {"ticker": "NWS", "name": "News Corporation Class B Common Stock"},
            {"ticker": "NWSA", "name": "News Corporation Class A Common Stock"},
        ]
        headline = "Man shot in New York City - ABC News - Breaking News"
        self.assertEqual(_explicitly_named_companies(headline, universe), [])

    def test_irrelevant_headline_skips_stock_retrieval(self) -> None:
        with patch("app.services.news.score_financial_relevance", return_value={
            "label": "not_useful", "score": 0.2, "threshold": 0.55,
            "model": "test-model", "method": "test",
        }), patch("app.services.news.get_us_listed_universe", return_value=([{
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
        with patch("app.services.news.score_financial_relevance", return_value={
                "label": "useful", "score": 0.8, "threshold": 0.55,
                "model": "test-model", "method": "test",
            }), \
                patch("app.services.news.get_us_listed_universe", return_value=(universe, "test")), \
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
            self.assertIn("company_name_match", by_ticker[ticker]["relevance_evidence"])
        self.assertFalse(by_ticker["CL"]["entity_mentioned"])
        self.assertIn("indirect_stocky_candidate", by_ticker["CL"]["relevance_evidence"])

    def test_stocky_checkpoint_failure_keeps_ingestion_linking_exact_names_only(self) -> None:
        apple = {
            "ticker": "AAPL", "name": "Apple Inc. Common Stock",
            "listing_exchange": "Q", "listing_exchange_name": "Nasdaq",
        }
        with patch("app.services.news.score_financial_relevance", return_value={
                "label": "useful", "score": 0.8, "threshold": 0.55,
                "model": "test-model", "method": "test",
            }), \
                patch("app.services.news.get_us_listed_universe", return_value=([apple], "test")), \
                patch("app.services.news.get_sp500_universe", return_value=[{
                    "ticker": "AAPL", "name": apple["name"], "sector": "Technology",
                }]), \
                patch("app.services.news._explicitly_named_companies", return_value=[apple]), \
                patch("app.services.news._stocky_retrieval_unavailable", False), \
                patch("app.services.news.retrieve_tickers", side_effect=OSError("checkpoint unavailable")):
            result = analyze_headline("Apple reports quarterly earnings")

        candidate = result["ticker_candidates"][0]
        self.assertEqual(result["usefulness"]["ticker_inference"], "explicit-name-fallback-v1")
        self.assertEqual(result["usefulness"]["ticker_inference_status"], "model_unavailable")
        self.assertEqual(candidate["ticker"], "AAPL")
        self.assertEqual(candidate["candidate_source"], "exact_company_name")
        self.assertIsNone(candidate["relevance_score"])
        self.assertEqual(candidate["relevance_method"], "explicit_company_name_match_v1")

    def test_stored_exact_name_fallback_keeps_its_matching_diagnostic(self) -> None:
        article = NewsArticle(
            id=1, title="Apple reports quarterly earnings", summary=None,
            url="https://example.test/apple", source="Test", published_at=None,
            sentiment=None, sentiment_score=None, sentiment_scores=None,
            ticker_candidates=[{
                "ticker": "AAPL", "name": "Apple Inc.", "entity_mentioned": True,
                "candidate_source": "exact_company_name", "relevance_score": None,
                "relevance_method": "explicit_company_name_match_v1",
            }], impact_predictions=[], usefulness={
                "label": "useful", "ticker_inference": "explicit-name-fallback-v1",
                "ticker_inference_status": "model_unavailable",
            },
        )
        with patch("app.services.news.get_sp500_universe", return_value=[]):
            hydrated = review_stored_article(article, refresh_usefulness=False)
        candidate = hydrated.ticker_candidates[0]
        self.assertEqual(candidate["candidate_source"], "exact_company_name")
        self.assertEqual(candidate["relevance_method"], "explicit_company_name_match_v1")
        self.assertIsNone(candidate["relevance_score"])
        self.assertEqual(hydrated.usefulness["ticker_inference_status"], "model_unavailable")

    def test_stored_stocky_match_is_still_identified_as_model_based(self) -> None:
        article = NewsArticle(
            id=2, title="Apple market update", summary=None,
            url="https://example.test/stocky", source="Test", published_at=None,
            sentiment=None, sentiment_score=None, sentiment_scores=None,
            ticker_candidates=[{
                "ticker": "AAPL", "name": "Apple Inc.", "entity_mentioned": True,
                "candidate_source": "stocky", "relevance_score": 0.87,
            }], impact_predictions=[], usefulness={"label": "useful"},
        )
        with patch("app.services.news.get_sp500_universe", return_value=[]):
            hydrated = review_stored_article(article, refresh_usefulness=False)
        self.assertEqual(
            hydrated.ticker_candidates[0]["relevance_method"],
            "stocky_retrieval_and_company_entity_v1",
        )

    def test_google_news_http_error_is_persisted_without_articles(self) -> None:
        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        response = httpx.Response(429, request=httpx.Request("GET", "https://news.google.com/rss"))
        recovered_response = type("Response", (), {
            "text": "recovered", "raise_for_status": lambda self: None,
        })()
        entry = {"link": "https://example.test/recovered", "title": "Recovered headline"}
        with Session(engine) as session, \
                patch("app.services.news.httpx.get", side_effect=[response, recovered_response]), \
                patch("app.services.news.feedparser.parse", return_value=type(
                    "Feed", (), {"entries": [entry]}
                )()), \
                patch("app.services.news.analyze_headline", return_value={
                    "ticker_candidates": [], "usefulness": {"label": "not_useful"},
                }), \
                patch("app.services.news.add_impact_predictions", return_value=[]), \
                patch("app.services.news.enqueue_sentiment", return_value=0):
            with self.assertRaises(httpx.HTTPStatusError):
                ingest_latest(session, limit=1, query="AAPL stock OR shares")
            self.assertEqual(session.query(NewsArticle).count(), 0)
            state = session.get(IngestionState, 1)
            self.assertIsNotNone(state.latest_attempt_at)
            self.assertIn("429", state.last_error)
            result = ingest_latest(session, limit=1, query="AAPL stock OR shares")
            self.assertEqual(result["created"], 1)
            self.assertEqual(session.query(NewsArticle).count(), 1)
            self.assertIsNone(session.get(IngestionState, 1).last_error)
        engine.dispose()

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
                patch("app.services.news.add_impact_predictions", return_value=[]) as impact, \
                patch("app.services.news.enqueue_sentiment", return_value=1) as sentiment_queue:
            result = ingest_latest(session, limit=1, query="Apple")
            self.assertEqual(result["created"], 1)
            self.assertEqual(session.query(NewsArticle).count(), 1)
            impact.assert_called_once()
            sentiment_queue.assert_called_once()
            stored = session.query(NewsArticle).one()
            self.assertIsNone(stored.sentiment)
            self.assertEqual(stored.impact_predictions, [])
            self.assertEqual(stored.canonical_url, "https://example.test/new")
            entry["link"] = "https://example.test/new?utm_source=second-feed"
            repeated = ingest_latest(session, limit=1, query="Apple")
            self.assertEqual(repeated["created"], 0)
            self.assertEqual(session.query(NewsArticle).count(), 1)
            impact.assert_called_once()

        self.assertTrue(_ingestion_lock.acquire(blocking=False))
        try:
            with self.assertRaisesRegex(RuntimeError, "already running"):
                ingest_latest(None, limit=1)
        finally:
            _ingestion_lock.release()
        engine.dispose()

    def test_ingestion_stops_at_strict_new_article_limit_across_feed_windows(self) -> None:
        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        feeds = [
            [{"link": f"https://example.test/story-{feed}-{item}",
              "title": f"Headline {feed}-{item}", "summary": None,
              "source": {"title": "Test"}}
             for item in range(8)]
            for feed in range(4)
        ]
        responses = [type("Response", (), {
            "text": str(index), "status_code": 200,
            "raise_for_status": lambda self: None,
        })() for index in range(4)]

        with Session(engine) as session, \
                patch("app.services.news._feed_queries", side_effect=[
                    [None, "window-1", "window-2"],
                    [None, "window-1", "window-2", "window-3"],
                ]), \
                patch("app.services.news._default_rss_url", return_value="https://example.test/rss"), \
                patch("app.services.news._google_news_url", side_effect=lambda query: f"https://example.test/{query}"), \
                patch("app.services.news.httpx.get", side_effect=responses) as get, \
                patch("app.services.news.feedparser.parse", side_effect=lambda raw: type(
                    "Feed", (), {"entries": feeds[int(raw)]}
                )()), \
                patch("app.services.news.analyze_headline", return_value={
                    "ticker_candidates": [], "usefulness": {"label": "not_useful"},
                }), \
                patch("app.services.news.add_impact_predictions", return_value=[]), \
                patch("app.services.news.enqueue_sentiment", return_value=0):
            result = ingest_latest(session, limit=10)

        self.assertEqual(result["created"], 10)
        self.assertEqual(session.query(NewsArticle).count(), 10)
        self.assertEqual(get.call_count, 2)
        engine.dispose()

    def test_existing_and_canonical_duplicates_do_not_consume_new_article_budget(self) -> None:
        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        duplicate = NewsArticle(
            title="Already stored", summary=None,
            url="https://example.test/duplicate?utm_source=old", source="Test",
            published_at=None, sentiment=None, sentiment_score=None, sentiment_scores=None,
            ticker_candidates=[], impact_predictions=[], canonical_url="https://example.test/duplicate",
        )
        entries = [
            {"link": "https://example.test/duplicate?utm_medium=new", "title": "Duplicate canonical"},
            {"link": duplicate.url, "title": "Duplicate exact"},
            {"link": "https://example.test/new-1", "title": "New 1"},
            {"link": "https://example.test/new-2", "title": "New 2"},
            {"link": "https://example.test/new-3", "title": "Should not be persisted"},
        ]
        response = type("Response", (), {"text": "feed", "raise_for_status": lambda self: None})()
        with Session(engine) as session:
            session.add(duplicate)
            session.commit()
            with patch("app.services.news._feed_queries", return_value=["Apple"]), \
                    patch("app.services.news._google_news_url", return_value="https://example.test/rss"), \
                    patch("app.services.news.httpx.get", return_value=response), \
                    patch("app.services.news.feedparser.parse", return_value=type("Feed", (), {"entries": entries})()), \
                    patch("app.services.news.analyze_headline", return_value={
                        "ticker_candidates": [], "usefulness": {"label": "not_useful"},
                    }), \
                    patch("app.services.news.add_impact_predictions", return_value=[]), \
                    patch("app.services.news.enqueue_sentiment", return_value=0):
                result = ingest_latest(session, limit=2, query="Apple")
            self.assertEqual(result["created"], 2)
            self.assertEqual(session.query(NewsArticle).count(), 3)
            self.assertIsNone(session.query(NewsArticle).filter_by(title="Should not be persisted").one_or_none())
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
