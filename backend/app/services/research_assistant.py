"""Bounded, deterministic research answers grounded in existing FinSight services.

This module intentionally does not call an LLM. Retrieved company/news text is
treated as evidence only; it is never interpreted as an instruction.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import NewsArticle
from app.services.comparison import get_company_comparison
from app.services.fundamentals import get_company_fundamentals
from app.services.market import get_company_market_row, get_company_price_history
from app.services.market_context import get_company_market_context
from app.services.research_llm import ResearchLLMError, generate_narrative
from app.services.universe import get_sp500_universe


MAX_QUESTION_LENGTH = 500
MAX_TICKERS = 4
MAX_NEWS_SCAN = 500
MAX_HISTORY_TURNS = 6
_COMMON_WORD_TICKERS = {"ALL", "ARE", "CAN", "CAT", "FOR", "GAP", "HAS", "IT", "KEY", "NOW", "ON", "OPEN", "P", "PAY", "RUN", "SEE", "THE", "TO", "UP"}


class ResearchQuestionError(ValueError):
    """A user question cannot be answered within the supported research scope."""


def _resolve_tickers(question: str, universe: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    normalized = question.casefold()
    alias_matches: dict[str, set[str]] = {}
    ticker_matches: dict[str, dict[str, Any]] = {}
    full_name_matches: dict[str, dict[str, Any]] = {}
    for company in universe:
        ticker = str(company.get("ticker", "")).upper()
        name = str(company.get("name", ""))
        if not ticker:
            continue
        if len(ticker) <= 2:
            ticker_pattern = rf"(?:\$|\b(?:ticker|symbol)\s+\$?){re.escape(ticker)}(?![A-Za-z0-9])"
            if re.search(ticker_pattern, question, re.IGNORECASE):
                ticker_matches[ticker] = company
                continue
        else:
            ticker_pattern = rf"(?<![A-Za-z0-9]){re.escape(ticker)}(?![A-Za-z0-9])"
            occurrence = re.search(ticker_pattern, question, re.IGNORECASE)
            if occurrence and (occurrence.group(0).isupper() or ticker not in _COMMON_WORD_TICKERS):
                ticker_matches[ticker] = company
                continue
        if name and re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", normalized, re.IGNORECASE):
            full_name_matches[ticker] = company
        aliases = {name}
        short_name = re.sub(r"\b(?:class\s+[a-z]|incorporated|inc\.?|corporation|corp\.?|company|co\.?|limited|ltd\.?|plc)\b", " ", name, flags=re.IGNORECASE)
        short_name = re.sub(r"\s+", " ", short_name).strip(" .,\t\n")
        if len(short_name) >= 2:
            aliases.add(short_name)
        for alias in aliases:
            if alias and re.search(rf"(?<![\w]){re.escape(alias)}(?![\w])", normalized, re.IGNORECASE):
                alias_matches.setdefault(alias.casefold(), set()).add(ticker)
    ambiguities = {alias: sorted(symbols) for alias, symbols in alias_matches.items() if len(symbols) > 1}
    selected = ticker_matches | full_name_matches
    for symbols in alias_matches.values():
        if len(symbols) == 1:
            ticker = next(iter(symbols))
            selected[ticker] = next(company for company in universe if company.get("ticker", "").upper() == ticker)
    unresolved = {
        alias: symbols for alias, symbols in ambiguities.items()
        if not set(selected).intersection(symbols)
    }
    return list(selected.values()), unresolved


def _intent(question: str) -> str:
    q = question.casefold()
    if any(word in q for word in ("buy", "sell", "should i", "target price", "price target", "will it")):
        raise ResearchQuestionError("I can summarize observed FinSight data, but I cannot make a buy/sell recommendation or price target.")
    if any(word in q for word in ("news", "headline", "sentiment", "article")):
        return "news"
    if any(word in q for word in (
        "revenue", "p/e", "pe ratio", "eps", "fundamental", "financial metric",
        "market cap", "market capitalization", "profit margin", "net income",
        "assets", "liabilities", "debt-to-equity", "return on equity", "roe",
        "revenue growth", "free cash flow",
    )):
        return "fundamentals"
    if any(word in q for word in ("rsi", "moving average", "technical", "indicator", "regime", "volatility", "volatile", "macd", "bollinger", "atr")):
        return "technical"
    if any(word in q for word in ("compare", "comparison", "versus", " vs ", "relative to")):
        return "comparison"
    if any(word in q for word in ("performed", "performance", "return", "price history", "over the last", "past year", "past month", "past six months")):
        return "performance"
    if any(word in q for word in ("overview", "about", "analyze", "analysis", "summary", "summarize", "financial overview", "bullish", "bearish", "factors")):
        return "overview"
    raise ResearchQuestionError("I can answer company overview, performance, comparison, technical, fundamentals, and persisted-news questions.")


def _period(question: str) -> str:
    q = question.casefold()
    if re.search(r"\b(5|five)\s+years?\b", q):
        return "5y"
    if re.search(r"\b(6|six)\s+months?\b", q):
        return "6mo"
    if re.search(r"\b(3|three)\s+months?\b", q):
        return "3mo"
    if re.search(r"\b(1|one)\s+month\b", q):
        return "1mo"
    return "1y"


def _evidence(evidence_id: str, source: str, claim: str, *, observed_at: str | None = None,
              reporting_period: str | None = None, url: str | None = None, value: Any = None,
              unit: str | None = None, methodology: str | None = None, freshness: str | None = None) -> dict[str, Any]:
    return {
        "id": evidence_id, "source": source, "claim": claim, "observed_at": observed_at,
        "reporting_period": reporting_period, "url": url, "value": value, "unit": unit,
        "methodology": methodology, "freshness": freshness,
    }


def _metric_evidence(ticker: str, metrics: dict[str, Any], fundamentals: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = []
    for key, metric in metrics.items():
        if metric is None:
            continue
        reporting_period = _format_reporting_period(metric)
        methodology = metric.get("note") or metric.get("methodology")
        if metric.get("price_as_of"):
            methodology = "; ".join(filter(None, [methodology, f"Price input observed {metric['price_as_of']}"]))
        evidence.append(_evidence(
            f"sec-{ticker}-{key}", metric.get("source", fundamentals.get("source", "SEC EDGAR CompanyFacts")), f"{ticker} {key.replace('_', ' ')}",
            observed_at=metric.get("filing_date") or metric.get("period_end"),
            reporting_period=reporting_period,
            url=fundamentals.get("source_url"), value=metric.get("value"), unit=metric.get("unit"),
            methodology=methodology, freshness="reported",
        ))
    return evidence


def _format_reporting_period(metric: dict[str, Any]) -> str | None:
    """Describe duration and instant facts without implying a missing start date."""
    period_type = metric.get("period_type") or metric.get("period")
    period_start, period_end = metric.get("period_start"), metric.get("period_end")
    if period_type == "instant" and period_end:
        return f"instant as of {period_end}"
    if period_start or period_end:
        return f"{period_type or 'reported period'}; {period_start or '?'} to {period_end or '?'}"
    return period_type


_FUNDAMENTAL_LABELS = {
    "market_cap": "market capitalization", "pe_ratio": "P/E ratio", "eps": "diluted EPS",
    "revenue": "revenue", "net_income": "net income", "assets": "assets",
    "liabilities": "liabilities", "revenue_growth": "revenue growth",
    "profit_margin": "profit margin", "debt_to_equity": "debt-to-equity",
    "free_cash_flow": "free cash flow", "return_on_equity": "return on equity",
}


def _requested_fundamental_metrics(question: str) -> list[str]:
    q = question.casefold()
    if "financial metric" in q or "available fundamentals" in q:
        return list(_FUNDAMENTAL_LABELS)
    aliases = {
        "market_cap": ("market cap", "market capitalization"),
        "pe_ratio": ("p/e", "pe ratio", "price-to-earnings"),
        "eps": ("eps", "earnings per share"),
        "revenue": ("revenue",),
        "net_income": ("net income",),
        "assets": ("assets",),
        "liabilities": ("liabilities",),
        "revenue_growth": ("revenue growth",),
        "profit_margin": ("profit margin",),
        "debt_to_equity": ("debt-to-equity", "debt to equity"),
        "free_cash_flow": ("free cash flow",),
        "return_on_equity": ("return on equity", "roe"),
    }
    requested = [key for key, terms in aliases.items() if any(term in q for term in terms)]
    return requested or list(_FUNDAMENTAL_LABELS)


def _history_tickers(turn: dict[str, Any], universe: list[dict[str, Any]]) -> list[str]:
    supported = {str(company.get("ticker", "")).upper() for company in universe}
    supplied = [str(item).upper() for item in turn.get("companies", []) if str(item).upper() in supported]
    if supplied:
        return list(dict.fromkeys(supplied))[:MAX_TICKERS]
    matches, _ = _resolve_tickers(str(turn.get("question", "")), universe)
    return [str(item["ticker"]).upper() for item in matches[:MAX_TICKERS]]


def _resolve_followup_question(question: str, history: list[dict[str, Any]], universe: list[dict[str, Any]]) -> str:
    """Expand common follow-ups into a fresh, independently retrieved question.

    History is untrusted and is used only to identify a topic/ticker. All facts
    and citations in the resulting answer are retrieved again from FinSight.
    """
    if not history:
        return question
    current = question.strip()
    previous = history[-1]
    previous_question = str(previous.get("question", ""))[:MAX_QUESTION_LENGTH]
    lowered = current.casefold()
    target_rows, ambiguity = _resolve_tickers(current, universe)
    target_tickers = [str(row["ticker"]).upper() for row in target_rows]
    if ambiguity:
        return current

    if re.match(r"^(?:what|how) about\b", lowered) and len(target_tickers) == 1:
        try:
            previous_intent = _intent(previous_question)
        except ResearchQuestionError:
            previous_intent = ""
        if previous_intent == "fundamentals":
            cited_metrics = []
            for citation in previous.get("finding_citations", []):
                match = re.fullmatch(r"sec-[A-Z0-9.-]+-([a-z_]+)", str(citation))
                if match and match.group(1) in _FUNDAMENTAL_LABELS:
                    cited_metrics.append(match.group(1))
            metric_keys = list(dict.fromkeys(cited_metrics)) or _requested_fundamental_metrics(previous_question)
            labels = ", ".join(_FUNDAMENTAL_LABELS[key] for key in metric_keys if key in _FUNDAMENTAL_LABELS)
            return f"What are {target_tickers[0]}'s latest {labels or 'available financial fundamentals'}?"
        if previous_intent == "technical":
            return f"What do {target_tickers[0]}'s recent technical indicators suggest?"
        if previous_intent == "news":
            return f"Summarize recent {target_tickers[0]} news and sentiment."
        if previous_intent == "performance":
            return f"How has {target_tickers[0]} performed {_period(previous_question)}?"
        if previous_intent == "overview":
            return f"Give me an overview of {target_tickers[0]}."

    if re.match(r"^(?:compare|and)\b", lowered) and target_tickers:
        old_tickers = _history_tickers(previous, universe)
        if len(old_tickers) == 1 and old_tickers[0] not in target_tickers:
            try:
                previous_intent = _intent(previous_question)
            except ResearchQuestionError:
                previous_intent = ""
            combined = [old_tickers[0], *target_tickers]
            if previous_intent == "fundamentals":
                citation_metrics = []
                for citation in previous.get("finding_citations", []):
                    match = re.fullmatch(r"sec-[A-Z0-9.-]+-([a-z_]+)", str(citation))
                    if match and match.group(1) in _FUNDAMENTAL_LABELS:
                        citation_metrics.append(match.group(1))
                metric_keys = list(dict.fromkeys(citation_metrics)) or _requested_fundamental_metrics(previous_question)
                labels = ", ".join(_FUNDAMENTAL_LABELS[key] for key in metric_keys if key in _FUNDAMENTAL_LABELS)
                return f"Compare {labels or 'available financial fundamentals'} for {' and '.join(combined)}."
            return f"Compare {' and '.join(combined)} over {_period(previous_question)}."

    if re.match(r"^(?:explain the second|explain that|what does that mean|what does it mean)\b", lowered):
        citations = [str(item) for item in previous.get("finding_citations", [])]
        if lowered.startswith("explain the second") and len(citations) >= 2:
            citation = citations[1]
            match = re.fullmatch(r"sec-([A-Z0-9.-]+)-([a-z_]+)", citation)
            if match and match.group(2) in _FUNDAMENTAL_LABELS:
                return f"Explain {match.group(1)} { _FUNDAMENTAL_LABELS[match.group(2)] }."
            match = re.fullmatch(r"context-([A-Z0-9.-]+)", citation)
            if match:
                return f"Explain the technical indicators for {match.group(1)}."
            match = re.fullmatch(r"price-([A-Z0-9.-]+)", citation)
            if match:
                return f"Explain the recent price performance of {match.group(1)}."
        if previous_question:
            return previous_question
    return current


def _format_fundamental_value(key: str, metric: dict[str, Any]) -> str:
    value = metric.get("value")
    if not isinstance(value, (int, float)):
        return "unavailable"
    if key in {"revenue_growth", "profit_margin", "return_on_equity"}:
        return f"{value:.2%}"
    if key == "pe_ratio":
        return f"{value:.2f}x"
    if key == "eps":
        return f"${value:.2f} per share"
    if metric.get("unit") == "USD":
        return f"${value:,.0f}"
    return f"{value:,.3g} {metric.get('unit', '')}".strip()


def _price_freshness(observed_at: str | None) -> str:
    if not observed_at:
        return "unavailable"
    try:
        age = (date.today() - date.fromisoformat(observed_at[:10])).days
    except ValueError:
        return "unknown"
    return "fresh" if 0 <= age <= 4 else "stale"


def _safe_source_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    return value if parsed.scheme in {"https", "http"} and parsed.netloc else None


def _news_for_tickers(session: Session, tickers: set[str]) -> list[NewsArticle]:
    rows = session.scalars(select(NewsArticle).order_by(desc(NewsArticle.published_at), desc(NewsArticle.ingested_at)).limit(MAX_NEWS_SCAN)).all()
    return [row for row in rows if any(str(candidate.get("ticker", "")).upper() in tickers for candidate in (row.ticker_candidates or []))][:10]


def answer_research_question(
    question: str,
    session: Session,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    question = question.strip()
    if not question or len(question) > MAX_QUESTION_LENGTH:
        raise ResearchQuestionError(f"Enter a question between 1 and {MAX_QUESTION_LENGTH} characters.")
    try:
        universe = get_sp500_universe()
    except Exception as exc:
        raise RuntimeError("The company directory is temporarily unavailable.") from exc
    history = (conversation_history or [])[-MAX_HISTORY_TURNS:]
    resolved_question = _resolve_followup_question(question, history, universe)
    intent = _intent(resolved_question)
    companies, ambiguities = _resolve_tickers(resolved_question, universe)
    if ambiguities:
        symbols = sorted({ticker for matches in ambiguities.values() for ticker in matches})
        raise ResearchQuestionError(f"That company name matches multiple supported share classes ({', '.join(symbols)}). Please specify a ticker.")
    if not companies:
        raise ResearchQuestionError("Name one or more supported S&P 500 companies or tickers so I can retrieve evidence.")
    if len(companies) > MAX_TICKERS:
        raise ResearchQuestionError("Please limit a research question to four companies.")
    if intent == "comparison" and len(companies) < 2:
        raise ResearchQuestionError("Name at least two supported companies to compare.")
    tickers = [str(company["ticker"]).upper() for company in companies]
    period = _period(resolved_question)
    evidence: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    limitations: list[str] = []

    if intent in {"performance", "comparison", "overview"}:
        if len(tickers) > 1:
            try:
                comparison = get_company_comparison(tickers, period)
            except Exception:
                comparison = {"companies": [], "status": "unavailable"}
                limitations.append("Comparison price data could not be retrieved from its provider.")
            for item in comparison.get("companies", []):
                ticker = item["ticker"]
                evidence_id = f"price-{ticker}"
                evidence.append(_evidence(
                    evidence_id, comparison.get("source", "Yahoo Finance via yfinance"),
                    f"{ticker} adjusted-price performance over {period}",
                    observed_at=item.get("last_common_session"), reporting_period=period,
                    value=item.get("cumulative_return"), unit="return ratio",
                    methodology="Return over aligned common sessions; historical prices are provider-adjusted.",
                    freshness=_price_freshness(item.get("last_common_session")),
                ))
                findings.append({"text": f"{ticker}: cumulative return {item.get('cumulative_return')!r} over the requested aligned window.", "citations": [evidence_id]})
                if item.get("benchmark_relative_return") is not None:
                    relative_id = f"relative-{ticker}"
                    evidence.append(_evidence(relative_id, comparison.get("source", "Yahoo Finance via yfinance"),
                        f"{ticker} return minus SPY return", observed_at=item.get("benchmark_observation_end"),
                        reporting_period=period, value=item["benchmark_relative_return"], unit="return ratio",
                        methodology="Company cumulative return minus SPY cumulative return on common observed sessions; SPY is a proxy."))
                    findings.append({"text": f"{ticker}: return relative to the S&P 500 proxy was {item['benchmark_relative_return']!r}.", "citations": [relative_id]})
            if comparison.get("benchmark", {}).get("observation_count", 0) == 0:
                limitations.append("SPY benchmark observations were unavailable, so benchmark-relative results are omitted.")
            if comparison.get("status") != "available":
                limitations.append("Comparison price data was unavailable or incomplete.")
        else:
            ticker = tickers[0]
            try:
                points = get_company_price_history(ticker, period=period)
            except Exception:
                points = []
                limitations.append(f"Price history for {ticker} could not be retrieved from its provider.")
            if points:
                first, latest = points[0], points[-1]
                result = latest["close"] / first["close"] - 1 if first.get("close") and len(points) > 1 else None
                evidence_id = f"price-{ticker}"
                evidence.append(_evidence(evidence_id, "Yahoo Finance via yfinance (adjusted daily OHLCV)",
                    f"{ticker} adjusted daily close history", observed_at=latest.get("date"), reporting_period=period,
                    value=result, unit="return ratio", methodology="Latest adjusted close divided by first returned adjusted close, minus one.",
                    freshness=_price_freshness(latest.get("date"))))
                findings.append({"text": f"{ticker}: observed {period} price-history return is {result!r} through {latest['date']}.", "citations": [evidence_id]})
                close_id = f"close-{ticker}"
                evidence.append(_evidence(close_id, "Yahoo Finance via yfinance (adjusted daily OHLCV)",
                    f"{ticker} latest available adjusted daily close", observed_at=latest.get("date"),
                    value=latest.get("close"), unit="USD per share", freshness=_price_freshness(latest.get("date")),
                    methodology="Latest returned adjusted daily close; this is not an intraday quote."))
                findings.append({"text": f"{ticker}: latest available adjusted daily close was {latest.get('close')} USD per share on {latest['date']}.", "citations": [close_id]})
                if len(points) > 1 and points[-2].get("close"):
                    change_id = f"daily-change-{ticker}"
                    daily_change = latest["close"] / points[-2]["close"] - 1
                    evidence.append(_evidence(change_id, "Yahoo Finance via yfinance (adjusted daily OHLCV)",
                        f"{ticker} daily adjusted-close change", observed_at=latest.get("date"), value=daily_change,
                        unit="return ratio", methodology="Latest returned adjusted close divided by previous returned adjusted close, minus one."))
                    findings.append({"text": f"{ticker}: adjusted close changed {daily_change!r} from the preceding returned session.", "citations": [change_id]})
            else:
                limitations.append(f"No price history was available for {ticker}.")

    if intent in {"technical", "overview"}:
        for ticker in tickers:
            try:
                context = get_company_market_context(ticker)
                context_id = f"context-{ticker}"
                indicators = context.get("indicators", {})
                latest_date = context.get("latest_observation_date")
                evidence.append(_evidence(context_id, context.get("source", "Yahoo Finance via yfinance"),
                    f"{ticker} technical indicators and market regime", observed_at=latest_date,
                    value={"indicators": indicators, "regime": context.get("regime")}, unit="mixed; see indicator units",
                    methodology="Indicators are descriptive calculations from adjusted daily bars through the latest observation.",
                    freshness=_price_freshness(latest_date)))
                requested = ("rsi_14", "sma_20", "sma_50", "sma_200", "ema_12", "ema_26", "macd", "macd_signal", "macd_histogram", "historical_volatility_20d", "momentum_20d")
                observed = []
                for key in requested:
                    metric = indicators.get(key)
                    if metric is not None:
                        value = metric.get("value")
                        shown = "unavailable" if value is None else f"{value:.4g} {metric.get('unit', '')}".strip()
                        observed.append(f"{key} {shown}")
                regime = context.get("regime") or {}
                detail = "; ".join(observed) if observed else "requested indicators unavailable"
                findings.append({"text": f"{ticker}: as of {latest_date or 'an unavailable date'}, {detail}. Market regime classification: {regime.get('label', 'unavailable')} ({regime.get('criteria', 'criteria unavailable')}). These are descriptive indicator readings, not predictions.", "citations": [context_id]})
            except Exception:
                limitations.append(f"Technical context for {ticker} is currently unavailable.")

    if intent in {"fundamentals", "overview"}:
        settings = get_settings()
        requested_metrics = _requested_fundamental_metrics(resolved_question)
        period_keys_by_ticker: dict[str, dict[str, tuple[str | None, str | None, str | None]]] = {}
        for ticker in tickers:
            if not settings.sec_user_agent or "@" not in settings.sec_user_agent:
                evidence_id = f"sec-{ticker}-unavailable"
                evidence.append(_evidence(evidence_id, "SEC EDGAR CompanyFacts", f"SEC fundamentals for {ticker} unavailable"))
                findings.append({"text": f"{ticker}: SEC fundamentals are unavailable because SEC_USER_AGENT is not configured.", "citations": [evidence_id]})
                limitations.append("SEC fundamentals were not requested because SEC_USER_AGENT is not configured.")
                continue
            try:
                quote = get_company_market_row(ticker)
                fundamentals = get_company_fundamentals(
                    ticker,
                    latest_price=quote.get("price") if quote else None,
                    latest_price_as_of=quote.get("quote_time") if quote else None,
                )
                metrics = fundamentals.get("metrics", {})
                metric_items = _metric_evidence(ticker, metrics, fundamentals)
                evidence.extend(metric_items)
                period_keys_by_ticker[ticker] = {
                    key: (metric.get("period_type"), metric.get("period_start"), metric.get("period_end"))
                    for key, metric in metrics.items() if metric is not None
                }
                available_ids = {item["id"] for item in metric_items}
                for key in requested_metrics:
                    metric = metrics.get(key)
                    if metric is None:
                        evidence_id = f"sec-{ticker}-{key}-unavailable"
                        evidence.append(_evidence(
                            evidence_id, fundamentals.get("source", "SEC EDGAR CompanyFacts"),
                            f"{ticker} {_FUNDAMENTAL_LABELS[key]} unavailable in supported SEC facts",
                            url=fundamentals.get("source_url"), freshness="unavailable",
                        ))
                        findings.append({
                            "text": f"{ticker}: {_FUNDAMENTAL_LABELS[key]} is unavailable in the supported SEC filing facts.",
                            "citations": [evidence_id],
                        })
                        limitations.append(f"{_FUNDAMENTAL_LABELS[key].capitalize()} was not available for {ticker} in supported SEC facts.")
                        continue
                    evidence_id = f"sec-{ticker}-{key}"
                    if evidence_id not in available_ids:
                        continue
                    period = _format_reporting_period(metric) or "reporting period unavailable"
                    if metric.get("filing_date"):
                        period += f", filed {metric['filing_date']}"
                    if metric.get("price_as_of"):
                        period += f", price as of {metric['price_as_of']}"
                    findings.append({
                        "text": f"{ticker}: {_FUNDAMENTAL_LABELS[key]} {_format_fundamental_value(key, metric)} ({period}).",
                        "citations": [evidence_id],
                    })
                if not metric_items:
                    limitations.append(f"No supported SEC metrics were available for {ticker}.")
            except Exception:
                evidence.append(_evidence(f"sec-{ticker}-unavailable", "SEC EDGAR CompanyFacts", f"SEC fundamentals for {ticker} unavailable"))
                limitations.append(f"SEC fundamentals for {ticker} could not be retrieved.")
        if len(tickers) > 1 and period_keys_by_ticker:
            mismatched = [
                _FUNDAMENTAL_LABELS[key]
                for key in requested_metrics
                if len({period_keys_by_ticker[t].get(key) for t in period_keys_by_ticker
                        if period_keys_by_ticker[t].get(key) is not None}) > 1
            ]
            if mismatched:
                limitations.append(
                    "Issuer reporting periods differ for " + ", ".join(mismatched)
                    + "; cited values are reported separately and are not period-aligned."
                )

    if intent in {"news", "overview"}:
        try:
            articles = _news_for_tickers(session, set(tickers))
        except Exception:
            articles = []
            evidence.append(_evidence("news-unavailable", "FinSight persisted news archive", "Stored news could not be queried."))
            limitations.append("Persisted news storage could not be queried.")
            articles_unavailable = True
        else:
            articles_unavailable = False
        if not articles and not articles_unavailable:
            evidence.append(_evidence("news-empty", "FinSight persisted news archive", "No matching company articles are currently stored in FinSight."))
            findings.append({"text": "No matching company articles were retrieved from FinSight's persisted news archive. This does not establish that no relevant news exists elsewhere.", "citations": ["news-empty"]})
            limitations.append("Persisted news evidence is empty for the selected companies.")
        elif articles:
            ids = []
            sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0, "unavailable": 0}
            for article in articles:
                evidence_id = f"news-{article.id}"
                ids.append(evidence_id)
                label = article.sentiment if article.sentiment in {"positive", "negative", "neutral"} else "unavailable"
                sentiment_counts[label] += 1
                evidence.append(_evidence(evidence_id, article.source, article.title,
                    observed_at=article.published_at.isoformat() if article.published_at else None,
                    url=_safe_source_url(article.url), value={"sentiment": label, "status": article.sentiment_status,
                        "model": article.sentiment_model, "model_version": article.sentiment_model_version,
                        "inferred_at": article.sentiment_inferred_at.isoformat() if article.sentiment_inferred_at else None}))
            findings.append({"text": f"FinSight has {len(articles)} stored matching articles; sentiment counts: {sentiment_counts}.", "citations": ids})
            limitations.append("Stored news sentiment is model output and is not a predictor of future returns.")

    evidence_ids = {item["id"] for item in evidence}
    findings = [item for item in findings if item["citations"] and all(ref in evidence_ids for ref in item["citations"])]
    if not findings:
        findings = [{"text": "FinSight could not retrieve enough supported evidence to summarize this question.", "citations": []}]
    if not limitations:
        limitations.append("This deterministic summary describes available observations; it is not investment advice or a forecast.")
    result = {
        "mode": "deterministic_research_summary",
        "llm_status": "not_configured",
        "question": question,
        "resolved_question": resolved_question,
        "intent": intent,
        "companies": [{"ticker": ticker, "name": company.get("name"), "sector": company.get("sector")} for ticker, company in zip(tickers, companies)],
        "findings": findings,
        "evidence": evidence,
        "limitations": list(dict.fromkeys(limitations)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if not result["evidence"]:
        result["llm_status"] = "no_evidence_fallback"
        return result
    try:
        narrative = generate_narrative(
            resolved_question,
            [{"question": str(item.get("question", ""))[:MAX_QUESTION_LENGTH]} for item in history],
            result["evidence"], result["findings"], result["limitations"],
        )
    except ResearchLLMError as exc:
        result["llm_status"] = exc.status
        if exc.status not in {"not_configured", "configuration_incomplete", "unsupported_provider", "no_evidence"}:
            result["limitations"].append("Optional LLM explanation was unavailable or failed validation; deterministic findings are shown.")
        return result
    result["mode"] = "llm_assisted_research_summary"
    result["llm_status"] = "generated"
    result["narrative"] = narrative.text
    result["narrative_citations"] = narrative.citations
    return result
