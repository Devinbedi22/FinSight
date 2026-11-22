"use client";

import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Panel, PanelHeading, StatusBadge } from "@/components/ui";

const axisStyle = { fill: "var(--subtle)", fontSize: 10 };
const gridColor = "var(--line-soft)";
const tooltipStyle = {
  background: "var(--panel-raised)",
  border: "1px solid var(--line)",
  borderRadius: 8,
  color: "var(--text)",
  fontSize: 11,
};

export type ForecastPoint = { date: string; close: number; open?: number | null; high?: number | null; low?: number | null; volume?: number | null };
export type NewsMarker = { id: number; title: string; published_at: string };
export type EvidenceCandidate = {
  ticker: string;
  name: string;
  entity_mentioned?: boolean;
  relevance_score?: number | null;
};

type AnalyticsArticle = {
  id: number;
  published_at: string | null;
  sentiment?: string | null;
};

function ChartStatus({
  loading,
  error,
  hasData,
}: {
  loading: boolean;
  error: string;
  hasData: boolean;
}) {
  if (loading && !hasData) {
    return <p className="p-6 text-xs text-[var(--muted)]" role="status">Loading live article data…</p>;
  }
  if (error && !hasData) {
    return <p className="p-6 text-xs text-negative">Live article data is unavailable. {error}</p>;
  }
  return null;
}

export function NewsVolumeChart({
  articles,
  loading,
  error,
}: {
  articles: AnalyticsArticle[];
  loading: boolean;
  error: string;
}) {
  const datedArticles = articles.filter((article) => article.published_at);
  const data = useMemo(() => {
    const counts = new Map<string, number>();
    for (const article of datedArticles) {
      const date = article.published_at?.slice(0, 10);
      if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
        counts.set(date, (counts.get(date) ?? 0) + 1);
      }
    }
    return [...counts.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([date, count]) => ({ date, count }));
  }, [datedArticles]);
  const firstDate = data[0]?.date;
  const lastDate = data.at(-1)?.date;
  const hasData = data.length > 0;
  const detail = hasData
    ? `${datedArticles.length} dated of ${articles.length} loaded articles · ${firstDate} to ${lastDate} · live API sample`
    : "Publication dates from the currently loaded live API articles";

  return (
    <Panel>
      <PanelHeading
        title="Article volume over time"
        detail={detail}
        action={error ? <StatusBadge tone="amber">Refresh failed</StatusBadge> : undefined}
      />
      {error && hasData && <p className="px-5 pt-3 text-[10px] text-warning">Showing previously fetched live data; the latest refresh failed.</p>}
      <ChartStatus loading={loading} error={error} hasData={hasData} />
      {!loading && !error && !hasData && (
        <p className="p-6 text-xs text-[var(--muted)]">No dated articles are available in the loaded API sample.</p>
      )}
      {hasData && <div className="h-60 p-3 sm:h-64 sm:p-4">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 12, bottom: 18, left: 0 }}>
            <CartesianGrid vertical={false} stroke={gridColor} />
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              tick={axisStyle}
              minTickGap={28}
              tickFormatter={(date: string) => date.slice(5)}
              label={{ value: "Publication date", position: "insideBottom", offset: -12, fill: "var(--subtle)", fontSize: 10 }}
            />
            <YAxis
              allowDecimals={false}
              tickLine={false}
              axisLine={false}
              tick={axisStyle}
              width={30}
              label={{ value: "Articles", angle: -90, position: "insideLeft", fill: "var(--subtle)", fontSize: 10 }}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              labelFormatter={(date) => `Published ${date}`}
              formatter={(value) => [value, "Articles"]}
            />
            <Bar dataKey="count" name="Articles" fill="var(--accent-strong)" radius={[4, 4, 0, 0]} maxBarSize={32} />
          </BarChart>
        </ResponsiveContainer>
      </div>}
    </Panel>
  );
}

const sentimentColors: Record<string, string> = {
  positive: "var(--positive)",
  neutral: "var(--accent-strong)",
  negative: "var(--negative)",
};

export function SentimentDistributionChart({
  articles,
  loading,
  error,
}: {
  articles: AnalyticsArticle[];
  loading: boolean;
  error: string;
}) {
  const counts = useMemo(() => {
    const result = new Map<string, number>();
    for (const article of articles) {
      const label = article.sentiment?.toLowerCase();
      if (label && ["positive", "neutral", "negative"].includes(label)) {
        result.set(label, (result.get(label) ?? 0) + 1);
      }
    }
    return ["positive", "neutral", "negative"]
      .map((label) => ({ label, count: result.get(label) ?? 0 }))
      .filter((item) => item.count > 0);
  }, [articles]);
  const classifiedCount = counts.reduce((sum, item) => sum + item.count, 0);
  const hasData = classifiedCount > 0;

  return (
    <Panel>
      <PanelHeading
        title="Stored article sentiment"
        detail={`${classifiedCount} classified of ${articles.length} loaded articles · API sentiment labels`}
        action={error ? <StatusBadge tone="amber">Refresh failed</StatusBadge> : undefined}
      />
      {error && articles.length > 0 && <p className="px-5 pt-3 text-[10px] text-warning">Showing previously fetched live data; the latest refresh failed.</p>}
      <ChartStatus loading={loading} error={error} hasData={hasData} />
      {!loading && !error && !hasData && (
        <p className="p-6 text-xs leading-5 text-[var(--muted)]">
          No sentiment labels are present in the loaded API articles. The backend currently leaves article sentiment unclassified; no sample values are substituted.
        </p>
      )}
      {hasData && <>
        <div className="h-48 p-2">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={counts}
                dataKey="count"
                nameKey="label"
                innerRadius="52%"
                outerRadius="78%"
                paddingAngle={3}
                stroke="none"
              >
                {counts.map((item) => <Cell key={item.label} fill={sentimentColors[item.label]} />)}
              </Pie>
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(value, name) => [value, `${String(name)} articles`]}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap justify-center gap-x-4 gap-y-2 px-4 pb-4 text-[10px] text-[var(--muted)]">
          {counts.map((item) => (
            <span key={item.label} className="flex items-center gap-1.5">
              <i className="h-2 w-2 rounded-full" style={{ backgroundColor: sentimentColors[item.label] }} />
              {item.label} · {item.count}
            </span>
          ))}
        </div>
      </>}
    </Panel>
  );
}

export function EventIntelligenceRadar({
  usefulnessScore,
  candidates,
}: {
  usefulnessScore?: number | null;
  candidates: EvidenceCandidate[];
}) {
  const [selectedTicker, setSelectedTicker] = useState(candidates[0]?.ticker ?? "");
  const selected = candidates.find((candidate) => candidate.ticker === selectedTicker) ?? candidates[0];
  const data = useMemo(() => {
    const dimensions: { dimension: string; value: number; sourceValue: string }[] = [];
    if (typeof usefulnessScore === "number" && Number.isFinite(usefulnessScore)) {
      const score = Math.max(0, Math.min(10, usefulnessScore));
      dimensions.push({
        dimension: "Financial relevance",
        value: score,
        sourceValue: `${score.toFixed(2)} / 10`,
      });
    }
    if (typeof selected?.relevance_score === "number" && Number.isFinite(selected.relevance_score)) {
      const score = Math.max(0, Math.min(1, selected.relevance_score));
      dimensions.push({
        dimension: "Stocky match",
        value: score * 10,
        sourceValue: `${score.toFixed(3)} / 1 (display scaled ×10)`,
      });
    }
    if (typeof selected?.entity_mentioned === "boolean") {
      dimensions.push({
        dimension: "Issuer named",
        value: selected.entity_mentioned ? 10 : 0,
        sourceValue: selected.entity_mentioned ? "Yes (binary evidence)" : "No (binary evidence)",
      });
    }
    return dimensions;
  }, [selected, usefulnessScore]);

  if (data.length < 2) {
    return (
      <div className="rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] px-4 py-3 text-[10px] leading-5 text-[var(--muted)]">
        <p className="font-medium text-[var(--muted)]">Event Intelligence Radar unavailable</p>
        <p>At least two numeric analysis/evidence fields are needed. Missing dimensions are not estimated.</p>
      </div>
    );
  }

  return (
    <section className="my-3 rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] p-3" aria-label="Event intelligence evidence radar">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-[11px] font-semibold text-[var(--text)]">Event Intelligence Radar</h3>
          <p className="mt-1 text-[9px] text-[var(--muted)]">Stored analysis evidence · not event severity or a future-return prediction</p>
        </div>
        {candidates.length > 1 && (
          <label className="text-[9px] text-[var(--muted)]">
            Issuer{" "}
            <select
              aria-label="Radar issuer"
              value={selected?.ticker ?? ""}
              onChange={(event) => setSelectedTicker(event.target.value)}
              className="rounded border border-[var(--line)] bg-[var(--panel-raised)] px-2 py-1 text-[10px] text-[var(--text)]"
            >
              {candidates.map((candidate) => (
                <option key={candidate.ticker} value={candidate.ticker}>{candidate.ticker}</option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} outerRadius="68%">
            <PolarGrid stroke={gridColor} />
            <PolarAngleAxis dataKey="dimension" tick={{ fill: "var(--muted)", fontSize: 9 }} />
            <PolarRadiusAxis angle={30} domain={[0, 10]} ticks={[0, 5, 10]} tick={{ fill: "var(--subtle)", fontSize: 8 }} />
            <Radar
              name="Stored evidence"
              dataKey="value"
              stroke="var(--accent-strong)"
              fill="var(--accent-strong)"
              fillOpacity={0.28}
              isAnimationActive={false}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(_value, _name, item) => {
                const point = item.payload as { sourceValue?: string };
                return [point.sourceValue ?? "Unavailable", "Stored value"];
              }}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <p className="px-1 text-[9px] leading-4 text-[var(--subtle)]">
        Display scale 0–10. Stocky’s 0–1 score is scaled ×10; issuer-mentioned is binary (0 or 10). Values are article fields, not comparable calibrated probabilities.
      </p>
    </section>
  );
}

type ChartPayload = {
  payload?: { title?: string; date?: string; count?: number };
};

export function PricePredictionChart({
  history,
  forecast,
  news = [],
  currency = "USD",
}: {
  history: ForecastPoint[];
  forecast: { date: string; price: number; expectedReturn: number } | null;
  news?: NewsMarker[];
  currency?: string;
}) {
  const money = new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 });
  const indexedHistory = history.map((point, index) => ({ index, actual: point.close }));
  const chartData = forecast
    ? [...indexedHistory, { index: history.length, actual: null }]
    : indexedHistory;
  const maxIndex = Math.max(1, history.length - 1 + (forecast ? 1 : 0));
  const ticks = [...new Set(
    Array.from({ length: 6 }, (_, index) => Math.round((maxIndex * index) / 5))
      .concat(forecast ? [history.length] : []),
  )];
  const formatDate = (index: number) => {
    if (forecast && index >= history.length) return forecast.date;
    return history[Math.max(0, Math.min(history.length - 1, Math.round(index)))]?.date ?? "";
  };
  const markerGroups = new Map<number, NewsMarker[]>();
  if (history.length) {
    for (const article of news) {
      if (!article.published_at) continue;
      const publishedDate = new Date(article.published_at);
      if (!Number.isFinite(publishedDate.getTime())) continue;
      const calendarDate = publishedDate.toISOString().slice(0, 10);
      if (calendarDate < history[0].date || calendarDate > history[history.length - 1].date) continue;
      const index = history.findIndex((point) => point.date >= calendarDate);
      if (index < 0) continue;
      markerGroups.set(index, [...(markerGroups.get(index) ?? []), article]);
    }
  }
  const newsPoints = [...markerGroups.entries()].map(([index, items]) => ({
    x: index,
    y: history[index].close,
    date: formatDate(index),
    count: items.length,
    title: items.map((item) => item.title).join(" · "),
  }));
  const forecastPoint = forecast && history.length
    ? [{ x: history.length, y: forecast.price, date: forecast.date, title: "30-day model point forecast" }]
    : [];
  const newsArticleCount = newsPoints.reduce((sum, point) => sum + point.count, 0);

  return (
    <Panel>
      <PanelHeading
        title="Price history, news & 30-day forecast"
        detail="Observed adjusted closes with publication-date markers and an isolated model point"
        action={<StatusBadge tone={forecast ? "blue" : "muted"}>{forecast ? "Point forecast" : "No forecast"}</StatusBadge>}
      />
      {history.length ? <>
        <div className="h-[340px] p-3 sm:h-[420px] sm:p-4">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 12, right: 16, bottom: 12, left: 4 }}>
              <CartesianGrid vertical={false} stroke={gridColor} />
              <XAxis
                type="number"
                dataKey="index"
                name="Date"
                domain={[0, maxIndex]}
                ticks={ticks}
                tickLine={false}
                axisLine={false}
                tick={axisStyle}
                tickFormatter={(value: number) => formatDate(value)}
                label={{ value: "Trading date", position: "insideBottom", offset: -8, fill: "var(--subtle)", fontSize: 10 }}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tick={axisStyle}
                width={66}
                domain={["auto", "auto"]}
                tickFormatter={(value: number) => money.format(value)}
                label={{ value: "Adjusted close (USD)", angle: -90, position: "insideLeft", fill: "var(--subtle)", fontSize: 10 }}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                labelFormatter={(value) => formatDate(Number(value))}
                formatter={(value, name, item) => {
                  const point = (item as ChartPayload).payload ?? {};
                  if (name === "News publication") {
                    return [`${point.count ?? 1} article${point.count === 1 ? "" : "s"} · ${point.title ?? ""}`, "Published (date only)"];
                  }
                  if (name === "30-day forecast point") return [money.format(Number(value)), "Forecast point only"];
                  return [money.format(Number(value)), "Observed adjusted close"];
                }}
              />
              <Line
                type="monotone"
                dataKey="actual"
                name="Observed adjusted close"
                stroke="var(--accent-strong)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                connectNulls={false}
                isAnimationActive={false}
              />
              {newsPoints.length > 0 && (
                <Scatter
                  name="News publication"
                  data={newsPoints}
                  dataKey="y"
                  fill="var(--warning)"
                  shape="triangle"
                  isAnimationActive={false}
                />
              )}
              {forecastPoint.length > 0 && (
                <Scatter
                  name="30-day forecast point"
                  data={forecastPoint}
                  dataKey="y"
                  fill="var(--positive)"
                  shape="diamond"
                  isAnimationActive={false}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-5 pb-4 text-[10px] text-[var(--muted)]">
          <span className="flex items-center gap-2"><i className="h-0.5 w-4 bg-[var(--accent-strong)]" />Observed close</span>
          {newsArticleCount > 0 && <span className="flex items-center gap-2"><i className="h-2 w-2 rotate-45 bg-warning" />News published · {newsArticleCount}</span>}
          {forecast && <><span className="flex items-center gap-2"><i className="h-2 w-2 rotate-45 bg-[var(--positive)]" />30-day forecast point only</span><span className="tabular-nums">Model return: {forecast.expectedReturn >= 0 ? "+" : ""}{(forecast.expectedReturn * 100).toFixed(2)}%</span></>}
          <p className="basis-full text-[9px] leading-4 text-[var(--subtle)]">
            News markers indicate publication dates and are anchored to the next available daily close for display; they do not represent measured market reactions. {newsArticleCount === 0 ? "No selected articles fall within this displayed price history." : ""}
          </p>
        </div>
      </> : <p className="p-6 text-sm text-[var(--muted)]">No price history is available for this company.</p>}
    </Panel>
  );
}

export function CompanyPriceChart({
  history,
  period,
  onPeriodChange,
  source,
  loading,
  error,
}: {
  history: ForecastPoint[];
  period: string;
  onPeriodChange: (period: string) => void;
  source: string;
  loading: boolean;
  error: string;
}) {
  const periods = ["1mo", "3mo", "6mo", "1y", "5y", "max"];
  return (
    <Panel>
      <div className="flex flex-col gap-3 border-b border-[var(--line-soft)] px-4 py-4 sm:flex-row sm:items-start sm:justify-between sm:px-5">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-[var(--text)]">Historical price and volume</h2>
          <p className="mt-1 break-words text-xs leading-5 text-[var(--muted)]">{source || "Adjusted daily OHLCV from Yahoo Finance through yfinance"}</p>
        </div>
        <div className="grid w-full grid-cols-3 gap-1 sm:w-auto sm:flex sm:flex-wrap sm:justify-end" role="group" aria-label="Price history range">
          {periods.map((value) => <button key={value} type="button" aria-pressed={period === value} onClick={() => onPeriodChange(value)} className={`min-h-10 rounded-lg border px-3 py-2 text-[10px] font-semibold transition-colors focus-ring ${period === value ? "border-accent/50 bg-accent/20 text-accent-strong" : "border-transparent text-muted hover:bg-panel-raised hover:text-text"}`}>{value.toUpperCase()}</button>)}
        </div>
      </div>
      {loading ? <div className="p-7 text-xs text-[var(--muted)]" role="status">Loading {period} of daily prices and volume…</div>
        : error ? <div className="p-7 text-xs text-negative" role="status">{error}</div>
          : history.length === 0 ? <div className="p-7 text-xs text-[var(--muted)]">No price history is available for this company and period.</div>
            : <>
              <div className="h-[280px] p-3 sm:h-[350px] sm:p-4"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={history} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}><CartesianGrid vertical={false} stroke={gridColor} /><XAxis dataKey="date" tickLine={false} axisLine={false} tick={axisStyle} minTickGap={35} tickFormatter={(value: string) => value.slice(0, 7)} /><YAxis tickLine={false} axisLine={false} tick={axisStyle} width={68} domain={["auto", "auto"]} tickFormatter={(value: number) => `$${value.toFixed(0)}`} /><Tooltip contentStyle={tooltipStyle} labelFormatter={(value) => String(value)} formatter={(value) => [`$${Number(value).toFixed(2)}`, "Adjusted close"]} /><Line type="monotone" dataKey="close" name="Adjusted close" stroke="var(--accent-strong)" strokeWidth={2} dot={false} activeDot={{ r: 3 }} isAnimationActive={false} /></ComposedChart></ResponsiveContainer></div>
              {history.some((point) => point.volume != null) && <div className="h-[100px] border-t border-[var(--line-soft)] px-3 py-2 sm:h-[120px]"><ResponsiveContainer width="100%" height="100%"><BarChart data={history} margin={{ top: 4, right: 12, bottom: 0, left: 4 }}><XAxis dataKey="date" hide /><YAxis tickLine={false} axisLine={false} tick={axisStyle} width={68} tickFormatter={(value: number) => new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(value)} /><Tooltip contentStyle={tooltipStyle} labelFormatter={(value) => String(value)} formatter={(value) => [new Intl.NumberFormat().format(Number(value)), "Volume"]} /><Bar dataKey="volume" name="Volume" fill="var(--accent-strong)" maxBarSize={10} isAnimationActive={false} /></BarChart></ResponsiveContainer></div>}
              <p className="px-5 pb-4 text-[10px] text-[var(--subtle)]">Prices are adjusted daily bars; the selected range is {period.toUpperCase()}. Volume is reported shares traded per session.</p>
            </>}
    </Panel>
  );
}
