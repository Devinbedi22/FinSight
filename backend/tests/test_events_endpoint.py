from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.v1.news import list_financial_events


class _Scalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Session:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self, _query):
        return _Scalars(self.rows)


def test_events_endpoint_returns_persisted_rule_signals_with_source_and_limitations():
    article = SimpleNamespace(
        id=41,
        title="Acme reports quarterly results",
        source="Example Financial News",
        url="https://example.test/story/41",
        published_at=datetime(2026, 11, 20, 15, tzinfo=timezone.utc),
        financial_events=[{
            "event_type": "earnings_announcement",
            "related_companies": [{"ticker": "ACME", "name": "Acme"}],
            "extraction_method": "financial_headline_patterns_v1",
            "supporting_evidence": "Acme reports quarterly results",
        }],
    )

    result = list_financial_events(limit=5, ticker="ACME", session=_Session([article]))

    assert result["count"] == 1
    event = result["events"][0]
    assert event["supporting_article_id"] == 41
    assert event["source_url"] == article.url
    assert event["classification_status"] == "heuristic_headline_signal"
    assert event["novelty_status"] == "not_available"
    assert "not human-verified" in result["methodology_note"]


def test_events_endpoint_returns_empty_list_for_no_classified_articles():
    result = list_financial_events(limit=10, ticker=None, session=_Session([]))
    assert result["events"] == []
    assert result["count"] == 0
