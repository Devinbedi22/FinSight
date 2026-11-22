"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CompanyPriceChart, PricePredictionChart, type ForecastPoint, type NewsMarker } from "@/components/charts";
import { WatchlistButton } from "@/components/watchlist";
import { EmptyState, PageHeader, Panel, PanelHeading, StatCard, StatusBadge } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const periods = ["1mo", "3mo", "6mo", "1y", "5y", "max"];
type Profile = { ticker: string; name: string; sector: string; industry?: string | null; price: number | null; previous_close: number | null; change_percent: number | null; quote_time: string | null; quote_status: string };
type Directory = { status: string; detail: string };
type FinancialEvent = { event_type: string; published_at: string | null; source: string; supporting_evidence: string; extraction_method: string };
type Article = { id: number; title: string; url: string; source: string; published_at: string | null; ticker_candidates: { ticker: string; name: string }[]; sentiment: string | null; sentiment_score: number | null; sentiment_scores: Record<string, number> | null; sentiment_status: string; sentiment_model: string | null; sentiment_model_version: string | null; sentiment_inferred_at: string | null; sentiment_error: string | null; financial_events: FinancialEvent[] };
type Metric = { value: number; unit: string; period_type: string; period_start?: string | null; period_end?: string | null; filing_date?: string | null; price_as_of?: string | null; form?: string | null; source: string; note?: string; comparison_period_end?: string; quarters?: string[] } | null;
type Fundamentals = { company?: string; industry?: string | null; source: string; source_url: string; retrieved_at: string; market_price?: number | null; market_price_as_of?: string | null; metrics: Record<string, Metric> };
type Forecast = { history: ForecastPoint[]; latest_price?: number | null; daily_change?: number | null; prediction: { expected_return: number; forecast_price: number; as_of: string; horizon_days: number } | null; news_used: (NewsMarker & { url: string })[]; status: string; model?: string };
type ContextMetric = { value: number | null; unit: string; source: string; observation_date: string | null; as_of_date: string; freshness: string; methodology: string; reporting_period?: string | null };
type MarketContext = { ticker: string; status: string; as_of_date: string; latest_observation_date: string | null; observations: number; source: string; freshness_rule: string; benchmark: { ticker: string; name: string; proxy_limitations: string }; sector_benchmark: { ticker: string | null; name: string | null; proxy_limitations: string }; indicators: Record<string, ContextMetric>; regime: { label: string; criteria: string; probability: null }; limitations: string[] };
type EventStudy = { as_of_date: string; event_count: number; method: string; events: { article_id: number | null; title: string | null; event_type: string | null; source: string | null; published_at: string | null; publication_period_et: string; aligned_session: string | null; overlaps_nearby_event: boolean; returns: Record<string, { stock_return: number; benchmark_return: number | null; excess_return: number | null; start_date: string; end_date: string } | null> }[]; limitations: string[] };

function metricValue(key: string, metric: Metric): string {
  if (!metric || typeof metric.value !== "number" || !Number.isFinite(metric.value)) return "Unavailable";
  const value = metric.value;
  if (["revenue_growth", "profit_margin", "return_on_equity"].includes(key)) return `${(value * 100).toFixed(1)}%`;
  if (key === "pe_ratio" || key === "debt_to_equity") return `${value.toFixed(2)}×`;
  if (key === "eps") return `$${value.toFixed(2)}`;
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 2 }).format(value);
}

function metricNote(metric: Metric): string {
  if (!metric) return "Not reported in available SEC facts";
  const period = metric.period_type.replaceAll("_", " ");
  const dates = metric.period_end ? `period ending ${metric.period_end}` : "period not available";
  return `${period} · ${dates}${metric.filing_date ? ` · filed ${metric.filing_date}` : ""}${metric.price_as_of ? ` · market price as of ${new Date(metric.price_as_of).toLocaleDateString()}` : ""}${metric.form ? ` · ${metric.form}` : ""}`;
}

export default function CompanyDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const [ticker, setTicker] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [directory, setDirectory] = useState<Directory | null>(null);
  const [profileError, setProfileError] = useState("");
  const [articles, setArticles] = useState<Article[]>([]);
  const [newsError, setNewsError] = useState("");
  const [newsLoading, setNewsLoading] = useState(true);
  const [retryingSentimentId, setRetryingSentimentId] = useState<number | null>(null);
  const [history, setHistory] = useState<ForecastPoint[]>([]);
  const [historySource, setHistorySource] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [historyLoading, setHistoryLoading] = useState(true);
  const [period, setPeriod] = useState("1y");
  const [fundamentals, setFundamentals] = useState<Fundamentals | null>(null);
  const [fundamentalsError, setFundamentalsError] = useState("");
  const [fundamentalsLoading, setFundamentalsLoading] = useState(true);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [forecastError, setForecastError] = useState("");
  const [forecastLoading, setForecastLoading] = useState(true);
  const [marketContext, setMarketContext] = useState<MarketContext | null>(null);
  const [marketContextError, setMarketContextError] = useState("");
  const [marketContextLoading, setMarketContextLoading] = useState(true);
  const [eventStudy, setEventStudy] = useState<EventStudy | null>(null);
  const [eventStudyError, setEventStudyError] = useState("");
  const [eventStudyLoading, setEventStudyLoading] = useState(true);

  useEffect(() => {
    let active = true;
    let newsRefreshTimer: number | undefined;
    void params.then(({ ticker: raw }) => {
      const symbol = raw.toUpperCase();
      if (active) setTicker(symbol);
      const request = async <T,>(url: string): Promise<T> => {
        const response = await fetch(url, { cache: "no-store" });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail ?? `API returned ${response.status}`);
        return data as T;
      };
      const loadProfile = async () => {
        try {
          for (let attempt = 0; active && attempt < 20; attempt += 1) {
            const data = await request<{ companies?: Profile[]; directory?: Directory }>(`${API}/companies?search=${encodeURIComponent(symbol)}&limit=1`);
            if (!active) return;
            const company = data.companies?.[0] ?? null;
            setDirectory(data.directory ?? null);
            setProfile(company);
            setProfileError(company ? "" : `No S&P 500 company matched ${symbol}.`);
            if (company?.quote_status !== "pending") return;
            await new Promise((resolve) => window.setTimeout(resolve, 3000));
          }
        } catch (reason) {
          if (active) setProfileError(reason instanceof Error ? reason.message : "Company data unavailable.");
        }
      };
      void loadProfile();
      const loadCompanyNews = (attempt = 0) => {
        void request<Article[]>(`${API}/news?limit=100&ticker=${encodeURIComponent(symbol)}`)
          .then((data) => {
            if (!active) return;
            setArticles(data);
            const pending = data.some((article) => ["not_processed", "processing"].includes(article.sentiment_status));
            if (pending && attempt < 5) {
              newsRefreshTimer = window.setTimeout(() => loadCompanyNews(attempt + 1), 8000);
            }
          })
          .catch((reason) => { if (active) setNewsError(reason instanceof Error ? reason.message : "Company news unavailable."); })
          .finally(() => { if (active) setNewsLoading(false); });
      };
      loadCompanyNews();
      void request<Fundamentals>(`${API}/companies/${encodeURIComponent(symbol)}/fundamentals`)
        .then((data) => { if (active) setFundamentals(data); })
        .catch((reason) => { if (active) setFundamentalsError(reason instanceof Error ? reason.message : "Fundamentals unavailable."); })
        .finally(() => { if (active) setFundamentalsLoading(false); });
      void request<Forecast>(`${API}/companies/${encodeURIComponent(symbol)}/prediction`)
        .then((data) => { if (active) setForecast(data); })
        .catch((reason) => { if (active) setForecastError(reason instanceof Error ? reason.message : "Experimental forecast unavailable."); })
        .finally(() => { if (active) setForecastLoading(false); });
      void request<MarketContext>(`${API}/companies/${encodeURIComponent(symbol)}/market-context`)
        .then((data) => { if (active) setMarketContext(data); })
        .catch((reason) => { if (active) setMarketContextError(reason instanceof Error ? reason.message : "Market context unavailable."); })
        .finally(() => { if (active) setMarketContextLoading(false); });
      void request<EventStudy>(`${API}/companies/${encodeURIComponent(symbol)}/event-study`)
        .then((data) => { if (active) setEventStudy(data); })
        .catch((reason) => { if (active) setEventStudyError(reason instanceof Error ? reason.message : "News/price event study unavailable."); })
        .finally(() => { if (active) setEventStudyLoading(false); });
    }).catch((reason) => {
      if (active) setProfileError(reason instanceof Error ? reason.message : "Company details unavailable.");
    });
    return () => { active = false; if (newsRefreshTimer) window.clearTimeout(newsRefreshTimer); };
  }, [params]);

  useEffect(() => {
    if (!ticker) return;
    let active = true;
    setHistoryLoading(true);
    setHistoryError("");
    void fetch(`${API}/companies/${encodeURIComponent(ticker)}/history?period=${period}`, { cache: "no-store" })
      .then(async (response) => { const data = await response.json(); if (!response.ok) throw new Error(data.detail ?? `Price history returned ${response.status}`); return data; })
      .then((data) => { if (active) { setHistory(data.points ?? []); setHistorySource(data.source ?? ""); } })
      .catch((reason) => { if (active) setHistoryError(reason instanceof Error ? reason.message : "Price history unavailable."); })
      .finally(() => { if (active) setHistoryLoading(false); });
    return () => { active = false; };
  }, [ticker, period]);

  const metrics = fundamentals?.metrics ?? {};
  const companyName = profile?.name ?? fundamentals?.company ?? ticker;
  const stockPrice = profile?.price ?? fundamentals?.market_price ?? null;
  const change = profile?.change_percent;
  const prediction = forecast?.prediction;
  const classifiedArticles = articles.filter((article) => article.sentiment_status === "processed" && article.sentiment);
  const sentimentCounts = ["positive", "neutral", "negative"].map((label) => ({
    label,
    count: classifiedArticles.filter((article) => article.sentiment?.toLowerCase() === label).length,
  }));
  const sentimentTotal = sentimentCounts.reduce((sum, item) => sum + item.count, 0);
  const trendDays = Array.from({ length: 14 }, (_, index) => {
    const day = new Date();
    day.setDate(day.getDate() - (13 - index));
    const key = day.toISOString().slice(0, 10);
    return {
      key,
      values: ["positive", "neutral", "negative"].map((label) => classifiedArticles.filter((article) =>
        article.published_at?.slice(0, 10) === key && article.sentiment?.toLowerCase() === label,
      ).length),
    };
  });
  const maxTrendCount = Math.max(1, ...trendDays.map((day) => day.values.reduce((sum, value) => sum + value, 0)));
  const extractedEvents = articles.flatMap((article) => (article.financial_events ?? []).map((event) => ({ ...event, articleTitle: article.title }))).slice(0, 6);
  const unavailableSentimentCount = articles.filter((article) => ["model_unavailable", "inference_failed"].includes(article.sentiment_status)).length;
  const contextLabels: Record<string, string> = { sma_20: "SMA 20", sma_50: "SMA 50", sma_200: "SMA 200", ema_12: "EMA 12", ema_26: "EMA 26", ema_50: "EMA 50", rsi_14: "RSI 14", macd: "MACD", macd_signal: "MACD signal", macd_histogram: "MACD histogram", bollinger_lower: "Bollinger lower", bollinger_middle: "Bollinger middle", bollinger_upper: "Bollinger upper", atr_14: "ATR 14", historical_volatility_20d: "20-day annualized volatility", volume_vs_20d_average: "Volume / 20-day average", volume_anomaly: "Volume anomaly (≥2× average)", momentum_20d: "20-day momentum", momentum_252d: "252-day momentum", relative_return_20d_vs_sp500: "20-day return vs S&P 500", correlation_20d_vs_sp500: "20-day benchmark correlation", relative_volatility_20d_vs_sp500: "Relative volatility vs S&P 500", relative_return_20d_vs_sector: "20-day return vs sector proxy", relative_volatility_20d_vs_sector: "Relative volatility vs sector proxy" };
  const contextFormat = (metric: ContextMetric) => metric.value == null ? "Unavailable" : metric.unit === "boolean" ? metric.value ? "Yes" : "No" : metric.unit === "USD" ? `$${metric.value.toFixed(2)}` : metric.unit.includes("ratio") || metric.unit === "percentage_points" ? `${(metric.value * 100).toFixed(2)}%` : metric.unit === "annualized_ratio" ? `${(metric.value * 100).toFixed(1)}%` : metric.unit.includes("correlation") ? metric.value.toFixed(2) : metric.unit === "index_0_100" ? metric.value.toFixed(1) : metric.unit === "multiple" ? `${metric.value.toFixed(2)}×` : metric.value.toFixed(3);
  const contextIsStale = marketContext?.latest_observation_date ? (new Date(`${marketContext.as_of_date}T00:00:00Z`).getTime() - new Date(`${marketContext.latest_observation_date}T00:00:00Z`).getTime()) / 86_400_000 > 4 : false;
  const metricLabels: Record<string, string> = { market_cap: "Market capitalization", pe_ratio: "P/E ratio", eps: "Diluted EPS", revenue: "Revenue", net_income: "Net income", assets: "Total assets", liabilities: "Total liabilities", revenue_growth: "Revenue growth", profit_margin: "Profit margin", debt_to_equity: "Debt / equity", free_cash_flow: "Free cash flow", return_on_equity: "Return on equity" };
  const retrySentiment = async (articleId: number) => {
    setRetryingSentimentId(articleId);
    try {
      const response = await fetch(`${API}/news/${articleId}/sentiment/retry`, { method: "POST" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? `Retry returned ${response.status}`);
      setArticles((previous) => previous.map((article) => article.id === articleId
        ? { ...article, sentiment_status: "not_processed", sentiment_error: null }
        : article));
    } catch (reason) {
      setArticles((previous) => previous.map((article) => article.id === articleId
        ? { ...article, sentiment_error: reason instanceof Error ? reason.message : "Could not retry sentiment." }
        : article));
    } finally {
      setRetryingSentimentId(null);
    }
  };

  return <>
    <div className="mb-5 text-[11px] text-[var(--subtle)]"><Link href="/companies" className="hover:text-white">S&amp;P 500</Link><span className="px-2">/</span>{ticker}</div>
    <PageHeader eyebrow={`${profile?.sector ?? "S&P 500 company"}${fundamentals?.industry ? ` · ${fundamentals.industry}` : ""}`} title={companyName || "Company analysis"} description={`${ticker}${profile?.sector ? ` · ${profile.sector}` : ""} · Company analysis from available market, SEC filing, and stored news data.`} action={<div className="flex flex-wrap items-center gap-2">{profile && <WatchlistButton company={{ ticker: profile.ticker, name: profile.name, sector: profile.sector }} />}<StatusBadge tone={profileError ? "amber" : "green"}>{profileError ? "Partial company data" : profile ? "Company profile" : "Loading"}</StatusBadge></div>} />
    {directory?.status === "stale_limited_fallback" && <div role="status" className="mb-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs leading-5 text-warning">{directory.detail} Current quotes, historical prices, and SEC metrics are loaded independently and may be unavailable.</div>}
    {profileError && <div role="status" className="mb-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs text-warning">Company directory unavailable: {profileError}</div>}
    <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard label="Latest available close" value={stockPrice == null ? "Unavailable" : `$${stockPrice.toFixed(2)}`} note={profile?.quote_time ? `Quote date ${new Date(profile.quote_time).toLocaleDateString()}` : fundamentals?.market_price_as_of ? `Quote date ${new Date(fundamentals.market_price_as_of).toLocaleDateString()}` : "Yahoo Finance daily quote when available"} />
      <StatCard label="Daily change" value={change == null ? "Unavailable" : `${change >= 0 ? "+" : ""}${(change * 100).toFixed(2)}%`} note="Compared with prior available daily close" />
      <StatCard label="Sector" value={profile?.sector ?? "Unavailable"} note="S&P 500 constituent data" />
      <StatCard label="Industry" value={fundamentals?.industry ?? "Unavailable"} note={fundamentals?.industry ? "SEC filer classification (SIC)" : "Not available from configured sources"} />
    </div>

    <CompanyPriceChart history={history} period={period} onPeriodChange={(next) => { if (periods.includes(next)) setPeriod(next); }} source={historySource} loading={historyLoading} error={historyError} />

    <Panel className="mt-5 overflow-hidden">
      <PanelHeading title="Market context" detail="Descriptive adjusted-price indicators · observations only, not predictions" action={marketContext?.latest_observation_date ? <StatusBadge tone={contextIsStale ? "amber" : "blue"}>{contextIsStale ? "Stale data · " : "As of "}{marketContext.latest_observation_date}</StatusBadge> : undefined} />
      {marketContextLoading ? <p className="p-5 text-xs text-[var(--muted)]" role="status">Calculating market context from daily prices…</p> : marketContextError ? <EmptyState title="Market context unavailable" description={marketContextError} /> : marketContext && <>
        <div className="grid gap-px bg-[var(--line-soft)] sm:grid-cols-2 lg:grid-cols-3">
          <div className="bg-[var(--panel)] p-4 sm:col-span-2 lg:col-span-3"><p className="text-xs font-semibold text-[var(--text)]">Observed regime: {marketContext.regime.label.replaceAll("_", " ")}</p><p className="mt-1 text-[10px] leading-4 text-[var(--muted)]">Rule: {marketContext.regime.criteria}. No regime probabilities are assigned.</p></div>
          {Object.entries(marketContext.indicators).map(([key, metric]) => <div key={key} className="min-w-0 bg-[var(--panel)] p-3 sm:p-4"><p className="text-[10px] text-[var(--muted)]">{contextLabels[key] ?? key.replaceAll("_", " ")}</p><p className="mt-1.5 text-sm font-semibold tabular-nums text-[var(--text)]">{contextFormat(metric)}</p><p className="mt-1 text-[9px] leading-4 text-[var(--subtle)]">{metric.observation_date ? `Observed ${metric.observation_date} · ${metric.freshness}` : "Insufficient observations"} · {metric.methodology}</p></div>)}
        </div>
        <div className="border-t border-[var(--line-soft)] p-4"><p className="text-[10px] leading-5 text-[var(--muted)]">Benchmark: {marketContext.benchmark.name} ({marketContext.benchmark.ticker}). {marketContext.benchmark.proxy_limitations}</p><p className="text-[10px] leading-5 text-[var(--muted)]">Sector comparison: {marketContext.sector_benchmark.name ?? "Unavailable"}. {marketContext.sector_benchmark.proxy_limitations}</p><ul className="mt-1 list-disc space-y-1 pl-4 text-[10px] leading-4 text-[var(--subtle)]"><li>{marketContext.freshness_rule}</li>{marketContext.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul><p className="mt-2 text-[9px] text-[var(--subtle)]">Source: {marketContext.source} · calculations use bars no later than {marketContext.as_of_date}.</p></div>
      </>}
    </Panel>

    <Panel className="mt-5 overflow-hidden">
      <PanelHeading title="News and subsequent price observations" detail="Exploratory event study · historical association does not imply causation or predictive value" action={eventStudy ? <StatusBadge tone="muted">{eventStudy.event_count} events</StatusBadge> : undefined} />
      {eventStudyLoading ? <p className="p-5 text-xs text-[var(--muted)]" role="status">Aligning stored financial events with trading sessions…</p> : eventStudyError ? <EmptyState title="Event study unavailable" description={eventStudyError} /> : eventStudy?.events.length ? <>
        <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-[10px]"><thead className="bg-[var(--panel-raised)] text-[var(--muted)]"><tr><th className="px-4 py-2.5 font-medium">Event / source</th><th className="px-3 py-2.5 font-medium">Published / ET session</th><th className="px-3 py-2.5 font-medium">Aligned close</th><th className="px-3 py-2.5 font-medium">1 session excess</th><th className="px-3 py-2.5 font-medium">5 session excess</th><th className="px-3 py-2.5 font-medium">20 session excess</th></tr></thead><tbody className="divide-y divide-[var(--line-soft)]">{eventStudy.events.slice(0, 25).map((event, index) => <tr key={`${event.article_id}-${index}`}><td className="max-w-[20rem] px-4 py-3"><p className="font-medium text-[var(--muted)]">{event.event_type?.replaceAll("_", " ") ?? "News event"}{event.overlaps_nearby_event && <span className="ml-1.5 text-warning">· overlaps another event</span>}</p><p className="mt-1 truncate text-[var(--subtle)]">{event.title}</p><p className="mt-1 text-[var(--subtle)]">{event.source ?? "Source unavailable"}</p></td><td className="whitespace-nowrap px-3 py-3 text-[var(--muted)]">{event.published_at ? new Date(event.published_at).toLocaleString() : "Unavailable"}<p className="mt-1 text-[9px]">{event.publication_period_et.replaceAll("_", " ")}</p></td><td className="whitespace-nowrap px-3 py-3 text-[var(--muted)]">{event.aligned_session ?? "Unavailable"}</td>{["1_session", "5_session", "20_session"].map((horizon) => { const value = event.returns[horizon]?.excess_return; return <td key={horizon} className="whitespace-nowrap px-3 py-3 tabular-nums text-[var(--muted)]">{value == null ? "Unavailable" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`}</td>; })}</tr>)}</tbody></table></div>
        <p className="border-t border-[var(--line-soft)] p-4 text-[9px] leading-4 text-[var(--subtle)]">{eventStudy.method} Each excess return is stock return minus S&amp;P 500 proxy return over the same observed sessions. Only the first 25 events are shown; overlapping events are flagged, not statistically deconfounded.</p>
      </> : <EmptyState title="No eligible historical events" description="No stored, company-linked financial events with usable publication timestamps are available through this date." />}
    </Panel>

    <Panel className="mt-5 overflow-hidden">
      <PanelHeading title="Financial fundamentals" detail={fundamentals ? `Source: ${fundamentals.source} · retrieved ${new Date(fundamentals.retrieved_at).toLocaleString()}` : "Reported financial facts; unavailable values are not estimated"} action={fundamentals?.source_url ? <a href={fundamentals.source_url} target="_blank" rel="noreferrer" className="text-xs text-[var(--accent-strong)] hover:text-white">SEC filings ↗</a> : undefined} />
      {fundamentalsLoading ? <p className="p-5 text-xs text-[var(--muted)]" role="status">Loading SEC-reported facts…</p> : fundamentalsError ? <EmptyState title="Fundamentals unavailable" description={`${fundamentalsError} Configure the SEC_USER_AGENT setting with an application name and monitored contact email. Market and news sections remain independent.`} /> : <div className="grid gap-px bg-[var(--line-soft)] sm:grid-cols-2 xl:grid-cols-3">{Object.entries(metricLabels).map(([key, label]) => { const metric = metrics[key] ?? null; return <div key={key} className="bg-[var(--panel)] p-4"><p className="text-xs text-[var(--muted)]">{label}</p><p className="mt-2 text-xl font-semibold tabular-nums text-[var(--text)]">{metricValue(key, metric)}</p><p className="mt-1.5 text-[10px] leading-4 text-[var(--subtle)]">{metricNote(metric)}</p>{metric?.note && <p className="mt-1 text-[10px] text-[var(--subtle)]">{metric.note}</p>}</div>; })}</div>}
    </Panel>

    <div className="mt-5 grid gap-5 xl:grid-cols-2">
      <Panel className="min-w-0 overflow-hidden">
        <PanelHeading title="Company news intelligence" detail="Sourced stories and stored analysis · sentiment is not a stock-move prediction" action={<Link href="/news" className="text-xs text-[var(--accent-strong)] hover:text-white">Open archive →</Link>} />
        {newsLoading ? <p className="p-5 text-xs text-[var(--muted)]" role="status">Loading company news…</p> : newsError ? <EmptyState title="News unavailable" description={newsError} /> : articles.length ? <>
          <section aria-label="Sentiment coverage and trend" className="border-b border-[var(--line-soft)] p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-xs font-semibold text-[var(--text)]">FinBERT sentiment coverage</h3><p className="mt-1 text-[10px] text-[var(--subtle)]">{sentimentTotal} of {articles.length} loaded stories classified{classifiedArticles[0]?.sentiment_inferred_at ? ` · latest inference ${new Date([...classifiedArticles].map((item) => item.sentiment_inferred_at!).sort().at(-1)!).toLocaleString()}` : ""}</p></div><StatusBadge tone={sentimentTotal ? "blue" : unavailableSentimentCount ? "amber" : "muted"}>{sentimentTotal ? "Model output available" : unavailableSentimentCount ? "Some outputs unavailable" : "Awaiting analysis"}</StatusBadge></div>
            {sentimentTotal > 0 ? <>
              <div className="mt-4 flex h-2 overflow-hidden rounded-full bg-[var(--line-soft)]" aria-label={`Sentiment distribution across ${sentimentTotal} classified stories`}>
                {sentimentCounts.map((item) => <span key={item.label} className={item.label === "positive" ? "bg-positive" : item.label === "negative" ? "bg-negative" : "bg-muted"} style={{ width: `${item.count / sentimentTotal * 100}%` }} />)}
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">{sentimentCounts.map((item) => <span key={item.label} className="text-[10px] capitalize text-[var(--muted)]">{item.label} {item.count} ({Math.round(item.count / sentimentTotal * 100)}%)</span>)}</div>
              <div className="mt-5"><p className="mb-2 text-[10px] font-medium uppercase tracking-wide text-[var(--subtle)]">14-day story sentiment · publication dates</p><div className="space-y-1.5">{trendDays.map((day) => { const total = day.values.reduce((sum, value) => sum + value, 0); return <div key={day.key} className="grid grid-cols-[4rem_1fr_1.5rem] items-center gap-2"><span className="text-[9px] tabular-nums text-[var(--subtle)]">{new Date(`${day.key}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span><div className="flex h-2 overflow-hidden rounded-full bg-[var(--panel-raised)]" title={`${total} classified stories`}><span className="bg-positive" style={{ width: `${day.values[0] / maxTrendCount * 100}%` }} /><span className="bg-muted" style={{ width: `${day.values[1] / maxTrendCount * 100}%` }} /><span className="bg-negative" style={{ width: `${day.values[2] / maxTrendCount * 100}%` }} /></div><span className="text-right text-[9px] tabular-nums text-[var(--subtle)]">{total || ""}</span></div>; })}</div></div>
            </> : <p className="mt-3 text-xs leading-5 text-[var(--muted)]">No completed FinBERT classifications are available for these stories yet. Pending, unavailable, and failed model outputs are not presented as sentiment.</p>}
            {unavailableSentimentCount > 0 && <p className="mt-3 text-[10px] leading-4 text-warning/80">{unavailableSentimentCount} stories could not be classified. The model result was not fabricated; inspect status in the News archive/API.</p>}
          </section>
          {extractedEvents.length > 0 && <section aria-label="Extracted financial events" className="border-b border-[var(--line-soft)] p-4 sm:p-5"><h3 className="text-xs font-semibold text-[var(--text)]">Headline event signals</h3><p className="mt-1 text-[10px] text-[var(--subtle)]">Rule-based title matches · supporting article retained</p><ul className="mt-3 space-y-3">{extractedEvents.map((event, index) => <li key={`${event.extraction_method}-${event.articleTitle}-${index}`} className="border-l-2 border-[var(--accent-strong)] pl-3"><p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--muted)]">{event.event_type.replaceAll("_", " ")}<span className="font-normal normal-case text-[var(--subtle)]"> · {event.source}{event.published_at ? ` · ${new Date(event.published_at).toLocaleDateString()}` : ""}</span></p><p className="mt-1 text-xs leading-5 text-[var(--subtle)]">{event.supporting_evidence}</p></li>)}</ul></section>}
          <div className="divide-y divide-[var(--line-soft)]">{articles.map((article) => <article key={article.id} className="px-4 py-4 sm:px-5"><div className="flex flex-wrap items-center gap-2 text-[10px] text-[var(--subtle)]"><span>{article.source}</span><span aria-hidden="true">·</span><time>{article.published_at ? new Date(article.published_at).toLocaleString() : "Publication date unavailable"}</time>{article.sentiment_status === "processed" && article.sentiment ? <StatusBadge tone={article.sentiment === "positive" ? "green" : article.sentiment === "negative" ? "red" : "muted"}>{article.sentiment} · {article.sentiment_score == null ? "" : `${Math.round(article.sentiment_score * 100)}%`} FinBERT</StatusBadge> : <StatusBadge tone={article.sentiment_status === "inference_failed" || article.sentiment_status === "model_unavailable" ? "amber" : "muted"}>{article.sentiment_status.replaceAll("_", " ")}</StatusBadge>}</div><a href={`${API}/news/${article.id}/open`} target="_blank" rel="noreferrer" className="mt-2 block text-sm leading-6 text-[var(--text)] hover:text-white">{article.title}</a>{article.sentiment_status === "processed" && article.sentiment_model && <p className="mt-1 text-[9px] text-[var(--subtle)]">Model {article.sentiment_model}{article.sentiment_model_version ? ` · revision ${article.sentiment_model_version.slice(0, 12)}` : " · model revision unavailable"}{article.sentiment_inferred_at ? ` · analyzed ${new Date(article.sentiment_inferred_at).toLocaleString()}` : ""}</p>}{article.sentiment_error && <p className="mt-1 text-[10px] text-warning/70">Sentiment unavailable: {article.sentiment_error}</p>}{["inference_failed", "model_unavailable"].includes(article.sentiment_status) && <button type="button" onClick={() => void retrySentiment(article.id)} disabled={retryingSentimentId === article.id} className="mt-2 rounded-md border border-[var(--warning)] bg-[var(--panel-soft)] px-2.5 py-1.5 text-[10px] font-medium text-warning hover:bg-[var(--panel-raised)] disabled:opacity-50">{retryingSentimentId === article.id ? "Queuing retry…" : "Retry sentiment analysis"}</button>}</article>)}</div>
        </> : <EmptyState title="No company-linked stories" description={`No stored articles currently match ${ticker}. No sample headlines are shown.`} />}
      </Panel>

      <Panel className="min-w-0 overflow-hidden">
        <PanelHeading title="Experimental 30-day forecast" detail="Existing FinancialBERT Model v2 endpoint · uncalibrated point estimate" action={<StatusBadge tone="amber">Experimental</StatusBadge>} />
        {forecastLoading ? <p className="p-5 text-xs text-[var(--muted)]" role="status">Loading the existing forecast endpoint…</p> : forecastError ? <EmptyState title="Forecast unavailable" description={forecastError} /> : <>
          <div className="grid gap-3 p-4 sm:grid-cols-2"><StatCard label="Expected return" value={prediction ? `${prediction.expected_return >= 0 ? "+" : ""}${(prediction.expected_return * 100).toFixed(2)}%` : "Unavailable"} note={prediction ? `Raw output · ${prediction.horizon_days} days from ${prediction.as_of}` : forecast?.status.replaceAll("_", " ") ?? "No model output"} /><StatCard label="Forecast price" value={prediction ? `$${prediction.forecast_price.toFixed(2)}` : "Unavailable"} note="Single model point; no calibrated interval" /></div>
          {forecast?.history?.length ? <details className="border-t border-[var(--line-soft)]"><summary className="cursor-pointer px-5 py-3 text-xs text-[var(--accent-strong)]">Show forecast context chart</summary><PricePredictionChart history={forecast.history} news={forecast.news_used} forecast={prediction ? { date: new Date(new Date(prediction.as_of).getTime() + prediction.horizon_days * 86_400_000).toISOString().slice(0, 10), price: prediction.forecast_price, expectedReturn: prediction.expected_return } : null} /></details> : <p className="px-5 pb-4 text-xs text-[var(--muted)]">Historical forecast context is unavailable.</p>}
        </>}
        <p className="border-t border-[var(--line-soft)] p-4 text-[10px] leading-5 text-[var(--subtle)]">This is an experimental estimate, not a calibrated prediction or investment recommendation. Model quality has not been established through walk-forward evaluation in this application.</p>
      </Panel>
    </div>
    <p className="mt-4 text-[10px] leading-5 text-[var(--subtle)]">Market prices and volume: Yahoo Finance via yfinance (unofficial, delayed daily data). Filed fundamentals: SEC EDGAR CompanyFacts; periods and filing dates are shown per metric. Values not present in available filings remain unavailable.</p>
  </>;
}
