"""Run real cached FinBERT and deterministic pipeline components on the review CSV."""

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from time import perf_counter
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import NewsArticle
from app.ml.finbert import _classifier
from app.services.news import (
    _explicitly_named_companies,
    canonicalize_news_url,
    extract_financial_events,
)
from app.services import sentiment


HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / "news_intelligence_review_seed.csv"
UNIVERSE = [
    {"ticker": "TGT", "name": "Target Corporation"},
    {"ticker": "NVDA", "name": "NVIDIA Corporation"},
    {"ticker": "LLY", "name": "Eli Lilly and Company"},
    {"ticker": "KHC", "name": "The Kraft Heinz Company"},
    {"ticker": "PERI", "name": "Perion Network Ltd."},
    {"ticker": "ICE", "name": "Intercontinental Exchange Inc."},
    {"ticker": "CVET", "name": "Covetrus, Inc."},
    {"ticker": "WAY", "name": "Waystar Holding Corp."},
    {"ticker": "TRI", "name": "Thomson Reuters Corporation"},
    {"ticker": "ENVX", "name": "Enovix Corporation"},
    {"ticker": "HSBC", "name": "HSBC Holdings plc"},
    {"ticker": "FME", "name": "Fresenius Medical Care AG"},
    {"ticker": "FI", "name": "Fiserv, Inc."},
    {"ticker": "BMY", "name": "Bristol Myers Squibb Company"},
    {"ticker": "COLM", "name": "Columbia Sportswear Company"},
    {"ticker": "TDC", "name": "Teradata Corporation"},
    {"ticker": "IRM", "name": "Iron Mountain Incorporated"},
    {"ticker": "TT", "name": "Trane Technologies plc"},
    {"ticker": "MAT", "name": "Mattel, Inc."},
]
COMPANY_BY_TICKER = {item["ticker"]: item["name"] for item in UNIVERSE}


def _date(value: str) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def main() -> None:
    with CSV_PATH.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    cases = {row["case_id"]: row for row in rows}
    unique_rows = [row for row in rows if not row["case_type"].startswith("synthetic_")]

    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    article_ids: dict[str, int] = {}
    company_matches: dict[str, list[dict]] = {}
    with Session(engine) as session:
        for row in unique_rows:
            matches = _explicitly_named_companies(row["headline"], UNIVERSE)
            candidates = [
                {"ticker": item["ticker"], "name": item["name"],
                 "candidate_source": "curated_evaluation_alias_match",
                 "entity_mentioned": True,
                 "relevance_method": "company_name_and_contextual_ticker_match_v1"}
                for item in matches
            ]
            article = NewsArticle(
                title=row["headline"], summary=None, url=row["source_url"],
                canonical_url=canonicalize_news_url(row["source_url"]),
                source=row["source"], published_at=_date(row["published_at"]),
                ticker_candidates=candidates, impact_predictions=[],
                usefulness={"label": "evaluation_seed", "method": "manual_source_selection"},
            )
            session.add(article)
            session.flush()
            article.financial_events = extract_financial_events(
                article.title, candidates, article.id, article.published_at, article.source,
            )
            article_ids[row["case_id"]] = article.id
            company_matches[row["case_id"]] = matches
        session.commit()

    load_started = perf_counter()
    model_load_error = None
    try:
        classifier = _classifier()
    except Exception as exc:
        classifier = None
        model_load_error = f"{type(exc).__name__}: {str(exc)[:300]}"
    cold_load_seconds = perf_counter() - load_started

    inference_times: dict[str, float] = {}
    active_case: list[str] = []
    original_classify = sentiment.classify_sentiment

    def timed_classify(text: str) -> dict:
        start = perf_counter()
        try:
            return original_classify(text)
        finally:
            if active_case:
                inference_times[active_case[-1]] = perf_counter() - start

    worker_started = perf_counter()
    with patch("app.services.sentiment.get_engine", return_value=engine), patch.object(
        sentiment, "classify_sentiment", side_effect=timed_classify,
    ):
        for row in unique_rows:
            active_case.append(row["case_id"])
            sentiment._capacity.acquire()
            sentiment._infer_article(article_ids[row["case_id"]])
            active_case.pop()
    worker_wall_seconds = perf_counter() - worker_started

    persisted: dict[str, dict] = {}
    with Session(engine) as session:
        for case_id, article_id in article_ids.items():
            article = session.get(NewsArticle, article_id)
            persisted[case_id] = {
                "status": article.sentiment_status,
                "label": article.sentiment,
                "scores": article.sentiment_scores,
                "model": article.sentiment_model,
                "revision": article.sentiment_model_version,
                "inferred_at": article.sentiment_inferred_at,
                "events": article.financial_events or [],
            }

    for row in rows:
        case_id = row["case_id"]
        if row["case_type"].startswith("synthetic_"):
            base_id = row["duplicate_of"]
            row["canonical_url"] = canonicalize_news_url(row["source_url"])
            row["matched_tickers"] = json.dumps(
                [item["ticker"] for item in company_matches.get(base_id, [])], separators=(",", ":")
            )
            result = persisted.get(base_id, {})
            row["model_status"] = "reused_base_output"
            row["inference_latency_ms"] = ""
            row["extracted_event_types"] = json.dumps(
                [event["event_type"] for event in result.get("events", [])], separators=(",", ":")
            )
        else:
            row["canonical_url"] = canonicalize_news_url(row["source_url"])
            row["matched_tickers"] = json.dumps(
                [item["ticker"] for item in company_matches[case_id]], separators=(",", ":")
            )
            result = persisted[case_id]
            row["model_status"] = result["status"]
            row["inference_latency_ms"] = (
                f"{inference_times[case_id] * 1000:.2f}" if case_id in inference_times else ""
            )
            row["extracted_event_types"] = json.dumps(
                [event["event_type"] for event in result["events"]], separators=(",", ":")
            )
        row["finbert_label"] = result.get("label") or ""
        scores = result.get("scores") or {}
        for label in ("positive", "neutral", "negative"):
            row[f"p_{label}"] = f"{scores[label]:.6f}" if label in scores else ""
        row["model_id"] = result.get("model") or ""
        row["model_revision"] = result.get("revision") or ""
        row["human_review_status"] = "not_reviewed"

    fields = list(rows[0].keys())
    with CSV_PATH.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    latencies = list(inference_times.values())
    statuses = [result["status"] for result in persisted.values()]
    labels = [result["label"] for result in persisted.values() if result["label"]]
    total_inference = sum(latencies)
    print("cases=", len(rows))
    print("unique_articles=", len(unique_rows))
    print("persisted_processed=", statuses.count("processed"))
    print("persisted_unavailable_or_failed=", len(statuses) - statuses.count("processed"))
    print("label_counts=", {label: labels.count(label) for label in ("positive", "neutral", "negative")})
    print("cold_model_load_seconds=", round(cold_load_seconds, 3))
    print("mean_warm_inference_seconds=", round(mean(latencies), 4) if latencies else None)
    print("total_inference_seconds=", round(total_inference, 3))
    print("warm_articles_per_second=", round(len(latencies) / total_inference, 2) if total_inference else None)
    print("worker_wall_seconds_including_persistence=", round(worker_wall_seconds, 3))
    print("persisted_articles_per_second=", round(len(unique_rows) / worker_wall_seconds, 2) if worker_wall_seconds else None)
    print("model_revision_available=", any(result["revision"] for result in persisted.values()))
    print("all_outputs_persisted_in_temporary_db=", len(persisted) == len(unique_rows))
    if model_load_error:
        print("model_load_error=", model_load_error)
    engine.dispose()


if __name__ == "__main__":
    main()
