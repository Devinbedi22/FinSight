"""RSS collection, model inference, and persistence for financial headlines."""

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import re
import logging
from functools import lru_cache
from threading import Lock
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import NewsArticle
from app.db.models import IngestionState
from app.ml.financialbert import classify_impact
from app.ml.financial_relevance import score_financial_relevance
from app.ml.stocky import retrieve_tickers
from app.services.universe import get_sp500_universe, get_us_listed_universe
from app.services.sentiment import enqueue_sentiment

logger = logging.getLogger(__name__)


_SECURITY_SUFFIXES = re.compile(
    r"\s+(?:common stock|common shares|ordinary shares|ordinary share|"
    r"american depositary shares?.*|depositary shares?.*|class [a-z].*|"
    r"units?.*|warrants?.*|rights?.*)$",
    re.IGNORECASE,
)
_LEGAL_SUFFIXES = re.compile(
    r"[\s,.-]+(?:incorporated|inc|corporation|corp|limited|ltd|plc|llc|lp|company|co)\.?$",
    re.IGNORECASE,
)
_ingestion_lock = Lock()
_stocky_retrieval_unavailable = False
_NEGATIVE_MOVE = re.compile(
    r"\b(?:fell|falls|fall|dropped|drops|drop|sank|sink|slid|slides|slumps?|tumbles?|"
    r"plunges?|declines?|lower|down|lost|loses|hammered|hammers|slammed|slams|selloff)\b",
    re.IGNORECASE,
)
_POSITIVE_MOVE = re.compile(
    r"\b(?:rose|rises|rise|gained|gains|surged|surges|jumped|jumps|rallied|rallies|"
    r"higher|up|soared|soars|climbed|climbs)\b",
    re.IGNORECASE,
)
_TICKER_CONTEXT = re.compile(
    r"\b(?:shares?|stocks?|equities|ticker|symbol|earnings|revenues?|profits?|investors?|"
    r"company|corporation|corp\.?|inc\.?|plc|markets?|price|rose|fell|surged|slid|"
    r"gained|dropped|tumbled|traded|trading|acquires?|acquired|announces?|healthcare|"
    r"hospitals?|medical|patients?|insurance|drugs?)\b",
    re.IGNORECASE,
)
_GENERIC_NAME_WORDS = {
    "american", "first", "general", "national", "international", "united", "global", "news",
}
_AMBIGUOUS_COMPANY_ALIASES = {"apple", "target", "gap", "block", "shell", "match", "toast"}
_COMPANY_REFERENCE_CONTEXT = re.compile(
    r"\b(?:shares?|stocks?|ticker|earnings|revenues?|quarter(?:ly)?|q[1-4]|fiscal|guidance|"
    r"dividend|acquisition|merger|reported|reports?|results?|announced?|CEO|CFO|Nasdaq|NYSE|market cap)\b",
    re.IGNORECASE,
)


def _name_aliases(security_name: str) -> tuple[str, ...]:
    name = _SECURITY_SUFFIXES.sub("", security_name).strip(" ,.-")
    aliases = {name} if len(name) >= 4 else set()
    shorter = _LEGAL_SUFFIXES.sub("", name).strip(" ,.-")
    shorter = re.sub(r"^the\s+", "", shorter, flags=re.IGNORECASE)
    shorter = re.sub(r"\s+(?:and|&)\s*$", "", shorter, flags=re.IGNORECASE).strip(" ,.-")
    if len(shorter) >= 4 and shorter.casefold() not in _GENERIC_NAME_WORDS:
        aliases.add(shorter)
        first_word = re.split(r"\s+", shorter, maxsplit=1)[0].strip(" ,.-")
        if len(first_word) >= 5 and first_word.lower() not in _GENERIC_NAME_WORDS:
            aliases.add(first_word)
        if shorter.lower().endswith(" us") and len(shorter[:-3]) >= 4:
            aliases.add(shorter[:-3])
    return tuple(sorted(aliases, key=len, reverse=True))


@lru_cache(maxsize=16384)
def _alias_pattern(alias: str) -> re.Pattern:
    return re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.IGNORECASE)


def _company_name_alias_is_supported(text: str, alias: str) -> bool:
    """Require issuer-specific context for common words used as company names."""
    pattern = _alias_pattern(alias)
    for match in pattern.finditer(text):
        if alias.casefold() not in _AMBIGUOUS_COMPANY_ALIASES:
            return True
        window = text[max(0, match.start() - 90):match.end() + 90]
        if _COMPANY_REFERENCE_CONTEXT.search(window):
            return True
    return False


def _company_is_mentioned(text: str, ticker: str, security_name: str) -> bool:
    """Match a full security/company name or an unambiguous uppercase ticker token."""
    if any(_company_name_alias_is_supported(text, alias) for alias in _name_aliases(security_name)):
        return True
    # Short symbols (CL, T, V, etc.) collide with ordinary words and commodities.
    # For 3-letter symbols such as ICE, require finance context or `$TICKER`.
    if len(ticker) < 3:
        return False
    for match in re.finditer(rf"(?<![A-Za-z0-9]){re.escape(ticker)}(?![A-Za-z0-9])", text):
        if ticker.startswith("$") or (match.start() > 0 and text[match.start() - 1] == "$"):
            return True
        window = text[max(0, match.start() - 60):match.end() + 60]
        if _TICKER_CONTEXT.search(window):
            return True
    return False


def _normalize_phrase(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


@lru_cache(maxsize=2)
def _company_alias_index(signature: tuple[tuple[str, str], ...]) -> tuple[dict[str, tuple[str, ...]], int]:
    aliases: dict[str, set[str]] = {}
    max_words = 1
    for ticker, security_name in signature:
        for alias in _name_aliases(security_name):
            normalized = _normalize_phrase(alias)
            if normalized:
                aliases.setdefault(normalized, set()).add(ticker)
                max_words = max(max_words, len(normalized.split()))
    return {alias: tuple(tickers) for alias, tickers in aliases.items()}, max_words


def rerank_company_news(company_name: str, documents: list[dict], top_k: int) -> list[dict]:
    """Cohere rerank when configured; stable company-specific local fallback otherwise."""
    if not documents:
        return []
    settings = get_settings()
    if settings.cohere_api_key:
        try:
            import cohere

            client = cohere.ClientV2(api_key=settings.cohere_api_key)
            response = client.rerank(
                model=settings.cohere_rerank_model,
                query=(
                    f"News descriptions reporting factors that influence {company_name}'s stock price, "
                    "including company results, corporate actions, regulation, competition, and industry news."
                ),
                documents=[item["description"] for item in documents],
                top_n=min(top_k, len(documents)),
            )
            return [documents[result.index] for result in response.results]
        except Exception:
            logger.exception("Cohere rerank failed for company=%s; using Stocky/entity ranked candidates", company_name)
    return sorted(
        documents,
        key=lambda item: (bool(item.get("explicit_company_mention")), float(item.get("relevance_score") or 0.0),
                          item.get("published_at") or ""),
        reverse=True,
    )[:top_k]


def _explicitly_named_companies(text: str, universe: list[dict[str, str]]) -> list[dict[str, str]]:
    """Resolve named issuers independently of Stocky's top-k shortlist."""
    signature = tuple((company["ticker"], company["name"]) for company in universe)
    alias_index, max_words = _company_alias_index(signature)
    words = _normalize_phrase(text).split()
    mentioned: set[str] = set()
    for width in range(1, min(max_words, len(words)) + 1):
        for start in range(len(words) - width + 1):
            alias = " ".join(words[start:start + width])
            if alias in _AMBIGUOUS_COMPANY_ALIASES and not _company_name_alias_is_supported(text, alias):
                continue
            mentioned.update(alias_index.get(alias, ()))
    ticker_index = {
        company["ticker"]: company
        for company in universe if len(company["ticker"]) >= 3
    }
    for symbol in re.findall(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9.$-]{2,})(?![A-Za-z0-9])", text):
        company = ticker_index.get(symbol)
        if company and _company_is_mentioned(text, symbol, company["name"]):
            mentioned.add(symbol)
    return [company for company in universe if company["ticker"] in mentioned]


def _reported_direction(text: str, ticker: str, security_name: str) -> str | None:
    """Use a reported share move only when it occurs in a sentence naming the issuer."""
    sentences = re.split(r"(?<=[.!?;])\s+", text)
    for sentence in sentences:
        company_spans = [
            match.span()
            for alias in _name_aliases(security_name)
            for match in _alias_pattern(alias).finditer(sentence)
        ]
        if not company_spans and len(ticker) >= 3:
            company_spans = [
                match.span()
                for match in re.finditer(rf"(?<![A-Za-z0-9]){re.escape(ticker)}(?![A-Za-z0-9])", sentence)
            ]
        if not company_spans:
            continue
        moves = [
            (match.span(), "negative") for match in _NEGATIVE_MOVE.finditer(sentence)
        ] + [
            (match.span(), "positive") for match in _POSITIVE_MOVE.finditer(sentence)
        ]
        if moves:
            distance, direction = min(
                (
                    max(0, max(company_span[0] - move_span[1], move_span[0] - company_span[1])),
                    label,
                )
                for company_span in company_spans
                for move_span, label in moves
            )
            if distance <= 100:
                return direction
    return None


def _reconcile_reported_moves(article: NewsArticle) -> bool:
    """Prefer a directly reported share move over an issuer-conditioned model guess."""
    changed = False
    predictions = {item.get("ticker", "").upper(): item for item in article.impact_predictions or []}
    for candidate in article.ticker_candidates or []:
        ticker = candidate.get("ticker", "").upper()
        if (
            not ticker
            or not candidate.get("entity_mentioned")
            or candidate.get("security_type", "common_or_adr") != "common_or_adr"
        ):
            continue
        direction = _reported_direction(
            article.title, ticker, candidate.get("name", ticker)
        )
        prediction = predictions.get(ticker)
        if direction is None or prediction is None:
            continue
        if prediction.get("impact") == direction and prediction.get("status") == "reported_market_move":
            continue
        prediction.update({
            "impact": direction,
            "expected_return": None,
            "status": "reported_market_move",
            "model": None,
            "evidence_status": "explicit_company_mention_reported_market_move",
        })
        changed = True
        logger.info(
            "Reported share move overrides model article_id=%s ticker=%s direction=%s",
            article.id, ticker, direction,
        )
    return changed


def _classify_usefulness(text: str, explicitly_named_count: int = 0) -> dict:
    """Use a pretrained market-relevance model; issuer matches are metadata only."""
    try:
        result = score_financial_relevance(text)
    except Exception:
        logger.exception("Financial relevance model failed; refusing rule-based fallback")
        result = {
            "label": "unavailable",
            "score": None,
            "threshold": get_settings().financial_relevance_threshold,
            "model": get_settings().financial_relevance_model_id,
            "method": "model_error",
            "error": str(exc)[:400],
        }
    return {
        **result,
        "reason": ("model_score_above_threshold" if result["label"] == "useful" else
                   "model_score_below_threshold" if result["label"] == "not_useful" else "model_unavailable"),
        "explicitly_named_company_count": explicitly_named_count,
    }


_EVENT_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("earnings_announcement", re.compile(
        r"\b(?:quarterly|annual|financial)\s+results\b|"
        r"\b(?:first|second|third|fourth)[- ]quarter\s+(?:20\d{2}\s+)?results\b|"
        r"\bq[1-4](?:\s+20\d{2})?\s+(?:earnings|results)\b|"
        r"\b(?:quarterly|annual|q[1-4]|fourth[- ]quarter|full[- ]year)?\s*"
        r"(?:earnings|revenue results)\b|"
        r"\b(?:reports?|reported)\s+(?:quarterly\s+)?results\b", re.I)),
    ("guidance", re.compile(r"\b(?:guidance|outlook|forecast)\b", re.I)),
    ("merger_acquisition", re.compile(r"\b(?:acquir(?:e|es|ed|ing)|acquisition|merger|buyout|takeover)\b", re.I)),
    ("regulatory_development", re.compile(r"\b(?:SEC|FTC|DOJ|FDA|antitrust|regulator\w*|regulatory|investigation|approved by the FDA)\b", re.I)),
    ("product_launch", re.compile(
        r"\b(?:launch(?:es|ed)?|unveil(?:s|ed)?|debut(?:s|ed)?|introduc(?:es|ed))\b"
        r".{0,60}\b(?:product|service|platform|device|model|chip|drug|solution|system|tool)\b|"
        r"\b(?:product|service|platform|device|model|chip|drug|solution|system|tool)\b"
        r".{0,50}\b(?:launch(?:es|ed)?|goes live|rolls out|debut(?:s|ed)?)\b", re.I)),
    ("management_change", re.compile(r"\b(?:CEO|CFO|chief executive|chief financial officer)\b.{0,70}\b(?:resign\w*|step\w* down|appoint\w*|name\w*|replace\w*)\b|\b(?:resign\w*|step\w* down|appoint\w*|name\w*|replace\w*)\b.{0,70}\b(?:CEO|CFO|chief executive|chief financial officer)\b", re.I)),
    ("financial_operational_announcement", re.compile(r"\b(?:layoffs?|restructur\w*|bankrupt\w*|dividend|share buyback|stock repurchase|plant closure|workforce reduction)\b", re.I)),
)


def extract_financial_events(
    title: str, ticker_candidates: list[dict] | None, article_id: int,
    published_at: datetime | None, source: str,
) -> list[dict]:
    """Extract explainable title-level event signals; no model confidence is implied."""
    records = []
    related = [
        {"ticker": item.get("ticker"), "name": item.get("name")}
        for item in (ticker_candidates or []) if item.get("ticker")
    ]
    for event_type, pattern in _EVENT_PATTERNS:
        match = pattern.search(title)
        if match:
            records.append({
                "event_type": event_type,
                "related_companies": related,
                "supporting_article_id": article_id,
                "published_at": published_at.isoformat() if published_at else None,
                "source": source,
                "supporting_evidence": title,
                "extraction_method": "financial_headline_patterns_v1",
            })
    return records


def canonicalize_news_url(url: str) -> str:
    """Normalize common tracking variants while retaining publisher URL identity."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    port = f":{parts.port}" if parts.port and parts.port not in {80, 443} else ""
    netloc = f"{host}{port}" if host else parts.netloc.lower()
    tracking = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"}
    query = urlencode(sorted(
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in tracking
    ))
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def backfill_canonical_news_urls(session: Session, limit: int = 250) -> int:
    """Populate canonical lookup keys incrementally without rewriting original URLs."""
    rows = list(session.scalars(
        select(NewsArticle).where(NewsArticle.canonical_url.is_(None))
        .order_by(NewsArticle.id.asc()).limit(max(1, min(limit, 1000)))
    ))
    for article in rows:
        article.canonical_url = canonicalize_news_url(article.url)
    if rows:
        session.commit()
    return len(rows)


def _security_type(security_name: str) -> str:
    name = security_name.lower()
    for kind, marker in (("preferred", "preferred stock"), ("warrant", "warrant"),
                         ("unit", " units"), ("right", " rights")):
        if marker in name:
            return kind
    return "common_or_adr"


def review_stored_article(article: NewsArticle, refresh_usefulness: bool = True) -> NewsArticle:
    """Hydrate display metadata and current evidence for persisted legacy rows."""
    # Google News RSS summaries contain linked headline/source boilerplate, so
    # only the headline is reliable for issuer-name matching and direction.
    text = article.title
    try:
        sp500_sectors = {company["ticker"].upper(): company["sector"] for company in get_sp500_universe()}
    except Exception:
        logger.exception("Could not hydrate S&P 500 sectors for stored article_id=%s", article.id)
        sp500_sectors = {}
    for candidate in article.ticker_candidates:
        # Preserve the sector captured at inference time if a ticker is no
        # longer a current constituent; enrich old rows from the live universe.
        candidate["business_sector"] = candidate.get("business_sector") or sp500_sectors.get(
            candidate["ticker"].upper()
        )
        candidate["entity_mentioned"] = _company_is_mentioned(
            text, candidate["ticker"], candidate.get("name", candidate["ticker"])
        )
        candidate["evidence_status"] = (
            "explicit_company_mention" if candidate["entity_mentioned"] else "indirect_stocky_candidate"
        )
        candidate["relevance_evidence"] = (
            (["stocky_ticker_retrieval"] if candidate.get("candidate_source") == "stocky" else [])
            + (["company_name_or_contextual_ticker_match"] if candidate["entity_mentioned"]
               else ["indirect_stocky_candidate"])
        )
        if candidate.get("candidate_source") == "exact_company_name":
            candidate["relevance_method"] = "explicit_company_name_match_v1"
        elif candidate.get("candidate_source") == "stocky":
            candidate["relevance_method"] = "stocky_retrieval_and_company_entity_v1"
        candidate.setdefault("security_type", _security_type(candidate.get("name", "")))
    article.ticker_candidates = [
        candidate for candidate in article.ticker_candidates
        if not (
            candidate.get("candidate_source") == "exact_company_name"
            and not candidate.get("entity_mentioned")
        )
    ]
    # Re-evaluate legacy rows against the current screen so newly recognized
    # market headlines aren't permanently hidden by stale classifications.
    if refresh_usefulness:
        article.usefulness = _classify_usefulness(
            text, sum(bool(candidate["entity_mentioned"]) for candidate in article.ticker_candidates)
        )
    _reconcile_reported_moves(article)
    return article


def refresh_stored_usefulness(session: Session, limit: int = 100) -> int:
    """Re-score a bounded batch of legacy rows with the current pretrained model."""
    state = session.get(IngestionState, 1)
    if state is None:
        state = IngestionState(id=1, archive_day="")
        session.add(state)
        session.flush()
    query = select(NewsArticle).order_by(NewsArticle.id.desc()).limit(max(1, min(limit, 500)))
    if state.relevance_backfill_before_id is not None:
        query = query.where(NewsArticle.id < state.relevance_backfill_before_id)
    rows = list(session.scalars(query))
    changed = 0
    for article in rows:
        article.usefulness = _classify_usefulness(
            article.title,
            sum(bool(item.get("entity_mentioned")) for item in (article.ticker_candidates or [])),
        )
        changed += 1
    if rows:
        state.relevance_backfill_before_id = min(article.id for article in rows)
    else:
        state.relevance_backfill_before_id = None
    session.commit()
    logger.info("Legacy relevance classifier backfill updated=%d", changed)
    return changed


def analyze_headline(title: str, summary: str | None = None) -> dict:
    global _stocky_retrieval_unavailable
    # The RSS summary is just a duplicate linked title plus publisher metadata;
    # use the actual headline as source text for both retrieval and evidence.
    text = title.strip()
    universe, universe_retrieved_at = get_us_listed_universe()
    sp500 = get_sp500_universe()
    sp500_tickers = {company["ticker"] for company in sp500}
    named_companies = [company for company in _explicitly_named_companies(text, universe)
                       if company["ticker"] in sp500_tickers]
    usefulness = {
        **_classify_usefulness(text, len(named_companies)),
        "ticker_inference": "stocky-sp500-v1",
    }
    relevance_unavailable = usefulness["label"] == "unavailable"
    if usefulness["label"] != "useful" and not (relevance_unavailable and named_companies):
        logger.info("Stocky retrieval skipped non-market story title=%r", title)
        return {
            "usefulness": usefulness,
            "ticker_candidates": [],
            "scope": "S&P 500 constituents",
            "universe_count": len(sp500),
            "universe_retrieved_at": universe_retrieved_at,
            "interpretation": "No stock inference was run because the story lacks a market/company signal.",
        }
    logger.info("Stocky retrieval started title=%r universe=S&P500 count=%d", title, len(sp500))
    stocky_available = not _stocky_retrieval_unavailable
    if stocky_available:
        try:
            candidates = retrieve_tickers(title, [company["ticker"] for company in sp500])
        except Exception:
            # Keep ingestion durable when optional Stocky checkpoints are missing.
            # Exact issuer mentions below remain auditable; never fabricate a
            # relevance score or imply that the model produced these links.
            logger.exception("Stocky ticker retrieval unavailable; using explicit issuer matches only")
            _stocky_retrieval_unavailable = True
            stocky_available = False
            candidates = []
    else:
        candidates = []
        logger.warning("Stocky retrieval remains unavailable for this process; using explicit issuer matches only")
    if not stocky_available:
        usefulness["ticker_inference"] = "explicit-name-fallback-v1"
        usefulness["ticker_inference_status"] = "model_unavailable"
        usefulness["ticker_inference_error"] = "Stocky retrieval unavailable; only explicit company-name matches are linked."
    names = {company["ticker"]: company for company in universe}
    for company in sp500:
        names.setdefault(company["ticker"], {
            **company, "listing_exchange": "", "listing_exchange_name": "S&P 500",
        })
    candidate_by_ticker = {candidate["ticker"]: {**candidate, "candidate_source": "stocky"}
                           for candidate in candidates if candidate["ticker"] in names}
    for company in named_companies:
        candidate_by_ticker.setdefault(company["ticker"], {
            "ticker": company["ticker"], "relevance_score": None,
            "candidate_source": "exact_company_name",
        })
    try:
        sectors = ({company["ticker"]: company["sector"] for company in get_sp500_universe()}
                   if candidate_by_ticker else {})
    except Exception:
        sectors = {}
    enriched_candidates = []
    for ticker, candidate in candidate_by_ticker.items():
        company = names[ticker]
        mentioned = _company_is_mentioned(title, ticker, company["name"])
        name_mentioned = any(
            _alias_pattern(alias).search(title) for alias in _name_aliases(company["name"])
        )
        relevance_evidence = []
        if candidate.get("candidate_source") == "stocky":
            relevance_evidence.append("stocky_ticker_retrieval")
        if name_mentioned:
            relevance_evidence.append("company_name_match")
        elif mentioned:
            relevance_evidence.append("ticker_with_financial_context")
        else:
            relevance_evidence.append("indirect_stocky_candidate")
        enriched_candidates.append({
            **candidate,
            "name": company["name"],
            "listing_exchange": company["listing_exchange"],
            "listing_exchange_name": company["listing_exchange_name"],
            "business_sector": sectors.get(ticker),
            "security_type": _security_type(company["name"]),
            "entity_mentioned": mentioned,
            "evidence_status": "explicit_company_mention" if mentioned else "indirect_stocky_candidate",
            "relevance_evidence": relevance_evidence,
            "relevance_method": (
                "explicit_company_name_match_v1"
                if candidate.get("candidate_source") == "exact_company_name" or not stocky_available
                else "stocky_retrieval_and_company_entity_v1"
            ),
        })
    logger.info(
        "Stocky retrieval complete title=%r candidates=%s",
        title,
        [(candidate["ticker"], candidate.get("relevance_score")) for candidate in enriched_candidates],
    )
    return {
        "usefulness": usefulness,
        "ticker_candidates": enriched_candidates,
        "scope": "S&P 500 constituents",
        "universe_count": len(sp500),
        "universe_retrieved_at": universe_retrieved_at,
        "interpretation": (
            "Stocky retrieval was unavailable; only explicit company-name matches are linked. No model score was produced."
            if not stocky_available else
            "Stocky ranks S&P 500 ticker candidates for each headline; FinancialBERT Model v2 estimates "
            "the direction for each candidate using company context and prior stored headlines."
        ),
    }


def add_impact_predictions(session: Session, article: NewsArticle) -> list[dict]:
    """Estimate headline impact for every Stocky ticker using company and history context."""
    ticker_contexts: list[tuple[str, list[NewsArticle], str]] = []
    event_time = article.published_at
    current_text = article.title
    for candidate in article.ticker_candidates:
        ticker = candidate["ticker"]
        company_name = candidate.get("name", ticker)
        mentioned = candidate.get("entity_mentioned")
        if mentioned is None:
            mentioned = _company_is_mentioned(current_text, ticker, company_name)
        prior = []
        if event_time is not None:
            prior_query = (
                select(NewsArticle)
                .where(NewsArticle.id != article.id)
                .where(NewsArticle.published_at.is_not(None))
                .where(NewsArticle.published_at < event_time)
                .order_by(NewsArticle.published_at.desc())
                .limit(1000)
            )
            prior = [
                row for row in session.scalars(prior_query)
                if any(
                    item.get("ticker", "").upper() == ticker.upper()
                    and _company_is_mentioned(row.title, ticker, company_name)
                    for item in row.ticker_candidates
                )
            ][: get_settings().impact_context_limit]
        prior.reverse()
        ticker_contexts.append((ticker, prior, candidate.get("name", ticker)))

    predictions = []
    for ticker, prior, company_name in ticker_contexts:
        candidate = next(item for item in article.ticker_candidates if item["ticker"] == ticker)
        mentioned = candidate.get("entity_mentioned")
        if mentioned is None:
            mentioned = _company_is_mentioned(current_text, ticker, company_name)
        prior_text = " ".join(item.title for item in prior)
        business_sector = candidate.get("business_sector")
        business_context = f"Business profile: {company_name}; sector: {business_sector or 'not available'}; security: {candidate.get('security_type', 'common_or_adr')}."
        model_result = classify_impact(
            f"{business_context} Prior news about {company_name} ({ticker}): {prior_text}. Current news: {current_text}"
        )
        logger.info(
            "FinancialBERT impact complete ticker=%s article_id=%s impact=%s expected_return=%s status=%s context_count=%d",
            ticker, article.id, model_result.get("impact"), model_result.get("expected_return"),
            model_result.get("status"), len(prior),
        )
        predictions.append({
            **model_result,
            "ticker": ticker,
            "evidence_status": (
                "explicit_company_mention_model_estimate" if mentioned else
                "indirect_company_profile_model_estimate" if business_sector else
                "indirect_name_conditioned_model_estimate"
            ),
            "context_count": len(prior),
            "context_article_ids": [item.id for item in prior],
        })
    article.impact_predictions = predictions
    _reconcile_reported_moves(article)
    return article.impact_predictions


def _published_at(entry) -> datetime | None:
    raw = entry.get("published")
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError, OverflowError):
        return None


def _google_news_url(query: str) -> str:
    return str(
        httpx.URL("https://news.google.com/rss/search").copy_add_param("q", query)
        .copy_add_param("hl", "en-US").copy_add_param("gl", "US").copy_add_param("ceid", "US:en")
    )


def _default_rss_url() -> str:
    configured = get_settings().google_news_rss_url
    configured_query = httpx.URL(configured).params.get("q", "").strip().casefold()
    if configured_query in {"when:1d", "when:7d", "when:30d"}:
        # Existing .env files may retain the old query-only value, which
        # Google treats as a literal phrase and returns as an empty feed.
        return "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
    return configured


def _feed_queries(query: str | None = None, days: int = 30) -> list[str | None]:
    """Return one latest feed plus daily archive windows; caller checkpoints each day."""
    if query:
        return [query]
    today = datetime.now(timezone.utc).date()
    # A query term is required; a bare `when:30d` is treated as literal text
    # by RSS and returns an empty feed. `news` keeps discovery broad rather
    # than applying a market-relevance filter to the News tab.
    # Recent days first. A feed page is shallow, but each independent time
    # window exposes older stories; URL uniqueness in the DB accumulates them.
    archive_days = max(1, days)
    oldest = today - timedelta(days=archive_days)
    return [None, *[
        f"news after:{(today - timedelta(days=offset + 1)).isoformat()} "
        f"before:{(today - timedelta(days=offset)).isoformat()}"
        for offset in range(archive_days)
    ], f"news after:{(oldest - timedelta(days=1)).isoformat()} before:{oldest.isoformat()}"]


def _ingest_latest(
    session: Session, limit: int = 25, query: str | None = None, archive_only: bool = False
) -> dict:
    target = max(1, min(limit, 100))
    page_size = 100
    created = 0
    skipped = 0
    fetched = 0
    seen_urls: set[str] = set()
    pending_articles: list[NewsArticle] = []
    queries = _feed_queries(query)
    state = session.get(IngestionState, 1)
    if state is None:
        state = IngestionState(id=1, archive_day="")
        session.add(state)
    state.latest_attempt_at = datetime.now(timezone.utc)
    state.last_error = None
    session.flush()
    pending_archive_day = None
    if query is None and len(queries) > 1:
        stored_day = state.archive_day if state.archive_day not in (None, "") else None
        start_index = 1
        if stored_day:
            for index, candidate in enumerate(queries[1:], 1):
                if candidate and f"before:{stored_day}" in candidate:
                    start_index = index + 1
                    if start_index >= len(queries):
                        oldest = datetime.now(timezone.utc).date() - timedelta(days=30)
                        queries.append(
                            f"news after:{(oldest - timedelta(days=1)).isoformat()} "
                            f"before:{oldest.isoformat()}"
                        )
                        start_index = len(queries) - 1
                    break
        if stored_day is None:
            archive_query = queries[1]
        else:
            archive_query = queries[start_index]
        # On first startup ingest a broad recent window plus an older date
        # slice, not only the front-page RSS list. Subsequent polls advance
        # the persistent archive cursor by one day at a time.
        queries = [queries[0]]
        if stored_day is None:
            queries.extend(_feed_queries(days=3)[1:4])
        else:
            queries.append(archive_query)
        day_match = re.search(r"after:(\d{4}-\d{2}-\d{2})", archive_query or "")
        pending_archive_day = day_match.group(1) if day_match else None
    actual_queries = len(queries)
    logger.info("News ingestion started sources=%d target_new_articles=%d archive_day=%s", actual_queries, target, state.archive_day)
    try:
        for feed_query in queries:
            page_url = _default_rss_url() if feed_query is None else _google_news_url(feed_query)
            response = httpx.get(page_url, timeout=30, follow_redirects=True)
            response.raise_for_status()
            parsed = feedparser.parse(getattr(response, "content", response.text))
            entries = parsed.entries[:page_size]
            logger.info(
                "News ingestion feed fetched query=%r status=%d entries=%d malformed=%s",
                feed_query, getattr(response, "status_code", 200), len(entries), getattr(parsed, "bozo", False),
            )
            if not entries:
                logger.warning("News ingestion returned an empty feed query=%r url=%s", feed_query, page_url)
                continue
            fetched += len(entries)
            for entry in entries:
                url = entry.get("link")
                title = entry.get("title")
                if not url or not title:
                    skipped += 1
                    continue
                canonical_url = canonicalize_news_url(url)
                if canonical_url in seen_urls:
                    skipped += 1
                    continue
                seen_urls.add(canonical_url)
                existing = session.scalar(select(NewsArticle.id).where(
                    (NewsArticle.url == url) | (NewsArticle.canonical_url == canonical_url)
                ))
                if existing is not None:
                    skipped += 1
                    continue
                summary = entry.get("summary")
                if archive_only:
                    # Archive discovery must not wait for per-story Stocky and
                    # per-ticker impact inference. The scheduled backfill
                    # enriches these persisted rows after the archive exists.
                    analysis = {
                        "usefulness": {
                            "label": "pending",
                            "method": "archive_only_pending_enrichment",
                            "ticker_inference": "pending",
                        },
                        "ticker_candidates": [],
                    }
                else:
                    analysis = analyze_headline(title, summary)
                article = NewsArticle(
                    title=title,
                    summary=summary,
                    url=url,
                    canonical_url=canonical_url,
                    source=entry.get("source", {}).get("title", "Google News RSS"),
                    published_at=_published_at(entry),
                    sentiment=None,
                    sentiment_score=None,
                    sentiment_scores=None,
                    ticker_candidates=analysis["ticker_candidates"],
                    impact_predictions=[],
                    usefulness=analysis["usefulness"],
                )
                article.impact_predictions = (
                    [] if archive_only else add_impact_predictions(session, article)
                )
                pending_articles.append(article)
                created += 1
                if created >= target:
                    break
            if created >= target:
                # Stop at the requested number of new articles. Leave the
                # archive cursor unchanged so an unscanned window is retried;
                # canonical URL deduplication makes that retry safe.
                break
        if created < target and pending_archive_day:
            # Advance the archive cursor only after all selected windows were
            # scanned. A capped run must not skip the remainder of a window.
            state.archive_day = pending_archive_day
        session.add_all(pending_articles)
        session.flush()
        for article in pending_articles:
            if (article.usefulness or {}).get("label") == "useful" or article.ticker_candidates:
                article.financial_events = extract_financial_events(
                    article.title, article.ticker_candidates, article.id,
                    article.published_at, article.source,
                )
        result = {"fetched": fetched, "created": created, "skipped": skipped,
                  "archive_only": archive_only, "feed_windows": actual_queries,
                  "archive_day": state.archive_day or None}
        state.latest_success_at = datetime.now(timezone.utc)
        state.last_result = result
        session.commit()
        pending_sentiment = [
            article.id for article in pending_articles
            if not archive_only and (
                (article.usefulness or {}).get("label") == "useful" or article.ticker_candidates
            )
        ]
        queued_sentiment = enqueue_sentiment(pending_sentiment)
        result["sentiment_queued"] = queued_sentiment
        logger.info("News ingestion persisted fetched=%d created=%d skipped=%d archive_day=%s", fetched, created, skipped, state.archive_day or None)
        return result
    except Exception as exc:
        session.rollback()
        failed_state = session.get(IngestionState, 1)
        if failed_state is None:
            failed_state = IngestionState(id=1, archive_day="")
            session.add(failed_state)
        failed_state.latest_attempt_at = datetime.now(timezone.utc)
        failed_state.last_error = str(exc)[:2000]
        session.commit()
        logger.exception("News ingestion failed; error persisted to ingestion_state")
        raise


def ingest_latest(session: Session, limit: int = 25, query: str | None = None) -> dict:
    """Serialize scheduled/manual ingest inside this process."""
    if not _ingestion_lock.acquire(blocking=False):
        raise RuntimeError("News ingestion is already running; wait for it to finish and retry.")
    try:
        return _ingest_latest(session, limit, query)
    finally:
        _ingestion_lock.release()


def bootstrap_news_archive(session: Session) -> dict:
    """Build a recent archive in bounded, durable daily batches before normal polling."""
    settings = get_settings()
    maximum = max(1, settings.news_archive_bootstrap_articles)
    days = max(1, settings.news_archive_bootstrap_days)
    logger.info("News archive bootstrap started days=%d article_budget=%d", days, maximum)
    totals = {"fetched": 0, "created": 0, "skipped": 0, "windows_completed": 0}
    for query in _feed_queries(days=days)[1:]:
        if totals["created"] >= maximum:
            break
        remaining = min(100, maximum - totals["created"])
        with _ingestion_lock:
            result = _ingest_latest(session, limit=remaining, query=query, archive_only=True)
        for key in ("fetched", "created", "skipped"):
            totals[key] += result[key]
        totals["windows_completed"] += 1
    logger.info("News archive bootstrap complete result=%s", totals)
    return totals


def backfill_missing_impacts(session: Session, limit: int = 10) -> int:
    """Run impact inference for stored legacy stories in small scheduled batches."""
    # Scan the whole archive so backfill can progress beyond the newest 1,000
    # rows. Completed model work is marked in usefulness and skipped below.
    query = select(NewsArticle).order_by(
        NewsArticle.published_at.desc(), NewsArticle.ingested_at.desc()
    )
    completed = 0
    changed = False
    sentiment_ids: list[int] = []
    with session.no_autoflush:
        for article in session.scalars(query):
            if (
                article.sentiment_status == "not_processed"
                and ((article.usefulness or {}).get("label") == "useful" or article.ticker_candidates)
            ):
                sentiment_ids.append(article.id)
            if (
                not article.financial_events
                and ((article.usefulness or {}).get("label") == "useful" or article.ticker_candidates)
            ):
                article.financial_events = extract_financial_events(
                    article.title, article.ticker_candidates, article.id,
                    article.published_at, article.source,
                )
                changed = changed or bool(article.financial_events)
            if not article.usefulness or article.usefulness.get("ticker_inference") not in {
                "stocky-sp500-v1", "explicit-name-fallback-v1",
            }:
                analysis = analyze_headline(article.title, article.summary)
                article.ticker_candidates = analysis["ticker_candidates"]
                article.usefulness = analysis["usefulness"]
                if article.usefulness.get("label") == "useful" or article.ticker_candidates:
                    article.financial_events = extract_financial_events(
                        article.title, article.ticker_candidates, article.id,
                        article.published_at, article.source,
                    )
                    if article.sentiment_status == "not_processed":
                        sentiment_ids.append(article.id)
                changed = True
                logger.info("Legacy story Stocky candidates refreshed article_id=%s count=%d", article.id, len(article.ticker_candidates))
                # Empty retrieval is still a completed model step. The marker
                # prevents expensive full-universe inference every poll.
                if not article.ticker_candidates:
                    completed += 1
                    if completed >= max(1, limit):
                        break
                    continue
            reported_move_changed = _reconcile_reported_moves(article)
            if not article.ticker_candidates:
                if reported_move_changed:
                    completed += 1
                    logger.info("Reported market moves reconciled article_id=%s", article.id)
                    if completed >= max(1, limit):
                        break
                continue
            completed_tickers = {prediction.get("ticker") for prediction in article.impact_predictions
                                 if prediction.get("status") in {"financialbert_model_v2", "financialbert_checkpoint_missing"}}
            if all(candidate["ticker"] in completed_tickers for candidate in article.ticker_candidates):
                if reported_move_changed:
                    completed += 1
                    logger.info("Reported market moves reconciled article_id=%s", article.id)
                    if completed >= max(1, limit):
                        break
                continue
            review_stored_article(article)
            article.impact_predictions = add_impact_predictions(session, article)
            completed += 1
            logger.info("Legacy story impact backfilled article_id=%s ticker_count=%d", article.id, len(article.impact_predictions))
            if completed >= max(1, limit):
                break
    if completed or changed:
        session.commit()
    enqueue_sentiment(list(dict.fromkeys(sentiment_ids)))
    return completed
