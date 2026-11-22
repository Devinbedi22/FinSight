"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CompanySearch, type CompanyOption } from "@/components/company-search";
import { EmptyState, PageHeader, Panel, PanelHeading, StatusBadge } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const periods = ["1mo", "3mo", "6mo", "1y", "5y"] as const;
const colors = ["var(--accent-strong)", "var(--positive)", "var(--warning)", "var(--negative)"];
type Period = typeof periods[number];
type CompanyResult = { ticker: string; name: string; sector: string | null; status: string; observation_count: number; common_session_count: number; dropped_observed_sessions: number; first_common_session: string | null; last_common_session: string | null; cumulative_return: number | null; annualized_volatility: number | null; maximum_drawdown: number | null; benchmark_relative_return: number | null; benchmark_observation_start: string | null; benchmark_observation_end: string | null };
type Comparison = { status: string; tickers: string[]; period: string; chart: Record<string, string | number | null>[]; common_session_count: number; companies: CompanyResult[]; benchmark: { ticker: string; source: string; observation_count: number; common_session_count: number }; source: string; adjustment: string; methodology: Record<string, string>; retrieved_at: string; provider_errors?: Record<string, string> };
type FinancialMetric = { value: number | null; unit: string; period_type?: string; period_end?: string | null; filing_date?: string | null; price_as_of?: string | null; source?: string } | null;
type Fundamentals = { source?: string; retrieved_at?: string; metrics?: Record<string, FinancialMetric> };
type Article = { id: number; title: string; source: string; published_at: string | null; sentiment: string | null; sentiment_status: string; sentiment_model?: string | null; sentiment_inferred_at?: string | null };
type Context = { status: string; as_of_date: string; latest_observation_date: string | null; source: string; indicators: Record<string, { value: number | null; unit: string; observation_date: string | null; freshness: string; methodology: string }>; regime: { label: string; criteria: string }; };
type DetailState<T> = { data?: T; loading?: boolean; error?: string };

function percent(value: number | null) { return value == null || !Number.isFinite(value) ? "Unavailable" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`; }
function money(value: number | null | undefined) { return value == null || !Number.isFinite(value) ? "Unavailable" : new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 2 }).format(value); }
function metricValue(metric: FinancialMetric, key: string) {
  if (!metric || metric.value == null) return "Unavailable";
  if (metric.unit.includes("USD")) return money(metric.value);
  if (["revenue_growth", "profit_margin", "return_on_equity"].includes(key)) return `${(metric.value * 100).toFixed(1)}%`;
  if (key === "pe_ratio") return `${metric.value.toFixed(2)}×`;
  if (metric.unit.includes("multiple")) return `${metric.value.toFixed(2)}×`;
  return metric.value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
function contextValue(metric: Context["indicators"][string] | undefined) {
  if (!metric || metric.value == null) return "Unavailable";
  if (["ratio", "annualized_ratio", "percentage_points"].includes(metric.unit)) return `${(metric.value * 100).toFixed(1)}%`;
  if (metric.unit === "index_0_100") return metric.value.toFixed(1);
  if (metric.unit === "USD") return `$${metric.value.toFixed(2)}`;
  if (metric.unit === "multiple") return `${metric.value.toFixed(2)}×`;
  return metric.value.toFixed(2);
}

export default function ComparePage() {
  const [selected, setSelected] = useState<CompanyOption[]>([]);
  const tickers = useMemo(() => selected.map((company) => company.ticker), [selected]);
  const [period, setPeriod] = useState<Period>("1y");
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [detailRetry, setDetailRetry] = useState(0);
  const [fundamentals, setFundamentals] = useState<Record<string, DetailState<Fundamentals>>>({});
  const [news, setNews] = useState<Record<string, DetailState<Article[]>>>({});
  const [contexts, setContexts] = useState<Record<string, DetailState<Context>>>({});
  const fundamentalsCache = useRef<Record<string, DetailState<Fundamentals>>>({});
  const newsCache = useRef<Record<string, DetailState<Article[]>>>({});
  const fundamentalsInFlight = useRef(new Map<string, Promise<DetailState<Fundamentals>>>());
  const newsInFlight = useRef(new Map<string, Promise<DetailState<Article[]>>>());

  useEffect(() => {
    if (tickers.length < 2) { setComparison(null); setError(""); setLoading(false); return; }
    let active = true;
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ tickers: tickers.join(","), period });
    void fetch(`${API}/companies/compare?${params}`, { cache: "no-store" })
      .then(async (response) => { const data = await response.json(); if (!response.ok) throw new Error(data.detail ?? `Comparison returned ${response.status}`); return data as Comparison; })
      .then((data) => { if (active) setComparison(data); })
      .catch((reason) => { if (active) { setComparison(null); setError(reason instanceof Error ? reason.message : "Comparison data is unavailable."); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [tickers.join(","), period, retry]);

  useEffect(() => {
    if (tickers.length < 2) { setFundamentals({}); setNews({}); return; }
    let active = true;
    setFundamentals(Object.fromEntries(tickers.map((ticker) => [ticker, fundamentalsCache.current[ticker] ?? { loading: true }])));
    setNews(Object.fromEntries(tickers.map((ticker) => [ticker, newsCache.current[ticker] ?? { loading: true }])));
    const loadFundamentals = (ticker: string) => {
      if (fundamentalsCache.current[ticker]) return Promise.resolve(fundamentalsCache.current[ticker]);
      const pending = fundamentalsInFlight.current.get(ticker);
      if (pending) return pending;
      const request = fetch(`${API}/companies/${encodeURIComponent(ticker)}/fundamentals`, { cache: "no-store" })
        .then(async (response) => { const data = await response.json(); if (!response.ok) throw new Error(data.detail ?? `Fundamentals returned ${response.status}`); return { data: data as Fundamentals }; })
        .catch((reason) => ({ error: reason instanceof Error ? reason.message : "Fundamentals unavailable." }))
        .then((result) => { fundamentalsCache.current[ticker] = result; fundamentalsInFlight.current.delete(ticker); return result; });
      fundamentalsInFlight.current.set(ticker, request);
      return request;
    };
    const loadNews = (ticker: string) => {
      if (newsCache.current[ticker]) return Promise.resolve(newsCache.current[ticker]);
      const pending = newsInFlight.current.get(ticker);
      if (pending) return pending;
      const request = fetch(`${API}/news?limit=40&ticker=${encodeURIComponent(ticker)}`, { cache: "no-store" })
        .then(async (response) => { const data = await response.json(); if (!response.ok) throw new Error(data.detail ?? `News returned ${response.status}`); return { data: data as Article[] }; })
        .catch((reason) => ({ error: reason instanceof Error ? reason.message : "Company news unavailable." }))
        .then((result) => { newsCache.current[ticker] = result; newsInFlight.current.delete(ticker); return result; });
      newsInFlight.current.set(ticker, request);
      return request;
    };
    void Promise.all(tickers.map(async (ticker) => {
      const [fundamentalResult, newsResult] = await Promise.all([loadFundamentals(ticker), loadNews(ticker)]);
      return { ticker, fundamentalResult, newsResult };
    })).then((results) => {
      if (!active) return;
      setFundamentals(Object.fromEntries(results.map(({ ticker, fundamentalResult }) => [ticker, fundamentalResult])));
      setNews(Object.fromEntries(results.map(({ ticker, newsResult }) => [ticker, newsResult])));
    });
    return () => { active = false; };
  }, [tickers.join(","), detailRetry]);

  const retryDetails = () => {
    for (const ticker of tickers) {
      if (fundamentalsCache.current[ticker]?.error) delete fundamentalsCache.current[ticker];
      if (newsCache.current[ticker]?.error) delete newsCache.current[ticker];
    }
    setDetailRetry((value) => value + 1);
  };

  const loadContext = async (ticker: string) => {
    setContexts((previous) => ({ ...previous, [ticker]: { loading: true } }));
    try {
      const response = await fetch(`${API}/companies/${encodeURIComponent(ticker)}/market-context`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? `Market context returned ${response.status}`);
      setContexts((previous) => ({ ...previous, [ticker]: { data: data as Context } }));
    } catch (reason) {
      setContexts((previous) => ({ ...previous, [ticker]: { error: reason instanceof Error ? reason.message : "Market context unavailable." } }));
    }
  };

  const addCompany = (company: CompanyOption) => setSelected((previous) => previous.length >= 4 || previous.some((item) => item.ticker === company.ticker) ? previous : [...previous, company]);
  const removeCompany = (ticker: string) => {
    setSelected((previous) => previous.filter((item) => item.ticker !== ticker));
    setContexts((previous) => { const next = { ...previous }; delete next[ticker]; return next; });
  };

  return <>
    <PageHeader eyebrow="Relative market research" title="Compare companies" description="Compare adjusted historical prices, available SEC fundamentals, market context, and stored company news side by side. Observations are descriptive, not forecasts." action={<StatusBadge tone={selected.length >= 2 ? "blue" : "muted"}>{selected.length}/4 selected</StatusBadge>} />
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(16rem,0.8fr)_minmax(0,1.5fr)]">
      <Panel className="overflow-hidden"><PanelHeading title="Select companies" detail="Search the existing S&amp;P 500 directory by name or ticker. Choose 2–4." /><div className="space-y-4 p-4">
        <CompanySearch selectedTickers={tickers} onSelect={addCompany} disabled={selected.length >= 4} />
        <ul className="space-y-2" aria-label="Selected companies">{selected.map((company, index) => <li key={company.ticker} className="flex items-center justify-between gap-3 rounded-lg border border-[var(--line-soft)] bg-[var(--panel-soft)] px-3 py-2.5"><div className="min-w-0"><p className="truncate text-xs font-semibold text-[var(--text)]"><span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ backgroundColor: colors[index] }} />{company.name}</p><p className="mt-1 text-[10px] text-[var(--muted)]">{company.ticker} · {company.sector}</p></div><button type="button" onClick={() => removeCompany(company.ticker)} aria-label={`Remove ${company.ticker} from comparison`} className="min-h-11 min-w-11 rounded-md border border-[var(--line)] px-3 text-[11px] text-[var(--muted)] hover:bg-[var(--panel-raised)]">Remove</button></li>)}</ul>
        {selected.length < 2 && <p className="rounded-lg border border-dashed border-[var(--line)] p-3 text-[10px] leading-5 text-[var(--muted)]">Select at least two companies to load the comparison. Price histories are requested only for your selected companies and the SPY benchmark.</p>}
        {selected.length === 4 && <p role="status" className="text-[10px] text-[var(--muted)]">Maximum reached. Remove a company before adding another.</p>}
        <div className="flex flex-wrap gap-2" role="group" aria-label="Comparison date range">{periods.map((choice) => <button key={choice} type="button" onClick={() => setPeriod(choice)} aria-pressed={period === choice} className={`min-h-11 rounded-md border px-3 py-2 text-[11px] font-semibold ${period === choice ? "border-[var(--accent-strong)] bg-[var(--panel-raised)] text-[var(--accent-strong)]" : "border-[var(--line)] text-[var(--muted)] hover:bg-[var(--panel-raised)]"}`}>{choice.toUpperCase()}</button>)}</div>
      </div></Panel>

      <Panel className="min-w-0 overflow-hidden"><PanelHeading title="Normalized adjusted performance" detail="Each company starts at 100 on the first session common to all selected companies." action={comparison ? <StatusBadge tone="blue">{comparison.common_session_count} sessions</StatusBadge> : undefined} />
        {loading ? <div className="space-y-4 p-5" role="status"><p className="text-xs text-[var(--muted)]">Loading aligned adjusted daily histories…</p><div className="h-64 animate-pulse rounded-lg bg-[var(--panel-raised)]" /></div> : error ? <div className="p-5"><p role="alert" className="text-xs text-negative">{error}</p><button type="button" onClick={() => setRetry((value) => value + 1)} className="mt-3 min-h-11 rounded-lg border border-[var(--line)] px-3 text-xs text-[var(--text)]">Retry comparison</button></div> : selected.length < 2 ? <EmptyState title="Choose companies to compare" description="Use the search panel to add two or more companies. No sample market data is shown." /> : comparison && comparison.chart.length >= 2 ? <div className="p-2 pt-5 sm:p-4"><div role="group" aria-label="Normalized adjusted closing price chart; index starts at 100 on the first common session" className="h-72 w-full sm:h-80"><ResponsiveContainer width="100%" height="100%"><LineChart accessibilityLayer data={comparison.chart} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}><CartesianGrid stroke="var(--line)" strokeDasharray="3 3" /><XAxis dataKey="date" tick={{ fill: "var(--subtle)", fontSize: 10 }} tickFormatter={(value: string) => new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "2-digit" })} minTickGap={24} /><YAxis tick={{ fill: "var(--subtle)", fontSize: 10 }} width={48} domain={[(dataMin: number) => Math.floor(dataMin / 10) * 10, (dataMax: number) => Math.ceil(dataMax / 10) * 10]} tickFormatter={(value: number) => value.toFixed(0)} /><Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 8, color: "var(--text)", fontSize: 11 }} labelFormatter={(label) => String(label)} formatter={(value, name) => [typeof value === "number" ? `${value.toFixed(2)} index` : "Unavailable", name === "SPY" ? "SPY benchmark" : String(name)]} /><Legend wrapperStyle={{ color: "var(--muted)", fontSize: 10 }} />{tickers.map((ticker, index) => <Line key={ticker} type="monotone" dataKey={(row: Comparison["chart"][number]) => row[ticker]} name={ticker} stroke={colors[index]} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />)}<Line type="monotone" dataKey={(row: Comparison["chart"][number]) => row.SPY} name="SPY benchmark" stroke="var(--subtle)" strokeDasharray="5 4" strokeWidth={1.5} dot={false} connectNulls={false} isAnimationActive={false} /></LineChart></ResponsiveContainer></div><p className="px-3 pb-2 text-[9px] leading-4 text-[var(--subtle)]">Adjusted closing prices indexed to 100. Dates without an observation for any selected company are excluded; lines are not forward-filled.</p></div> : selected.length >= 2 ? <EmptyState title="Insufficient common history" description="Selected companies do not have at least two matching observed sessions in this range. Try a longer range or remove a company with sparse data." action={<button type="button" onClick={() => setRetry((value) => value + 1)} className="min-h-11 rounded-lg border border-[var(--line)] px-3 text-xs text-[var(--text)]">Retry data</button>} /> : null}
      </Panel>
    </div>

    {selected.length >= 2 && <>
      {comparison && (comparison.status !== "available" || Object.values(comparison.provider_errors ?? {}).length > 0 || comparison.benchmark.observation_count === 0) && <div role="status" className="mt-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs text-warning">{comparison.status !== "available" ? `Only ${comparison.common_session_count} common adjusted session(s) are available. Return and risk metrics may be unavailable. ` : "Some provider data is unavailable. "}{comparison.benchmark.observation_count === 0 ? "SPY data is unavailable; benchmark-relative returns cannot be calculated. " : ""}{Object.entries(comparison.provider_errors ?? {}).map(([symbol, message]) => `${symbol}: ${message}`).join(" ")}</div>}
      {!comparison && error && <div role="status" className="mt-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs text-warning">Historical comparison is unavailable. Fundamentals and stored news may still be shown below.</div>}
      {comparison && <Panel className="mt-5 overflow-hidden">
        <PanelHeading title="Performance and coverage" detail={`${comparison.source} · retrieved ${new Date(comparison.retrieved_at).toLocaleString()}`} />
        <div className="grid gap-3 p-3 xl:hidden">
          {comparison.companies.map((company) => <article key={company.ticker} className="rounded-lg border border-[var(--line-soft)] bg-[var(--panel-soft)] p-4">
            <h3 className="text-sm font-semibold text-[var(--text)]">{company.name} <span className="text-[var(--accent-strong)]">{company.ticker}</span></h3>
            <p className="mt-1 text-[10px] text-[var(--muted)]">{company.sector ?? "Sector unavailable"} · {company.first_common_session ?? "No common start"} – {company.last_common_session ?? "No common end"}</p>
            <dl className="mt-3 grid grid-cols-2 gap-3">
              {[["Cumulative return", percent(company.cumulative_return)], ["Annualized volatility", company.annualized_volatility == null ? "Unavailable" : `${(company.annualized_volatility * 100).toFixed(1)}%`], ["Max drawdown · aligned dates", percent(company.maximum_drawdown)], ["Excess vs SPY", percent(company.benchmark_relative_return)], ["Common sessions", `${company.common_session_count} aligned`], ["Observed coverage gaps", String(company.dropped_observed_sessions)]].map(([label, value]) => <div key={label}><dt className="text-[9px] uppercase tracking-wide text-[var(--subtle)]">{label}</dt><dd className="mt-1 text-xs tabular-nums text-[var(--text)]">{value}</dd></div>)}
            </dl>
            {company.benchmark_observation_start && <p className="mt-3 text-[9px] text-[var(--subtle)]">SPY window {company.benchmark_observation_start}–{company.benchmark_observation_end}</p>}
          </article>)}
        </div>
        <div className="hidden overflow-x-auto xl:block"><table className="w-full min-w-[780px] text-left text-xs"><thead className="bg-[var(--panel-raised)] text-[10px] uppercase tracking-wide text-[var(--muted)]"><tr><th className="px-4 py-3">Company</th><th className="px-3 py-3">Cumulative return</th><th className="px-3 py-3">Annualized volatility</th><th className="px-3 py-3">Max drawdown · aligned dates</th><th className="px-3 py-3">Vs SPY</th><th className="px-3 py-3">Common coverage</th></tr></thead><tbody className="divide-y divide-[var(--line-soft)]">{comparison.companies.map((company) => <tr key={company.ticker}><td className="px-4 py-3"><p className="font-semibold text-[var(--text)]">{company.name}</p><p className="mt-1 text-[10px] text-[var(--muted)]">{company.ticker} · {company.sector ?? "Sector unavailable"}</p><p className="mt-1 text-[9px] text-[var(--subtle)]">{company.first_common_session ?? "No common start"} – {company.last_common_session ?? "No common end"}</p></td><td className="px-3 py-3 tabular-nums text-[var(--text)]">{percent(company.cumulative_return)}</td><td className="px-3 py-3 tabular-nums text-[var(--text)]">{company.annualized_volatility == null ? "Unavailable" : `${(company.annualized_volatility * 100).toFixed(1)}%`}</td><td className="px-3 py-3 tabular-nums text-[var(--text)]">{percent(company.maximum_drawdown)}</td><td className="px-3 py-3 tabular-nums text-[var(--text)]">{percent(company.benchmark_relative_return)}{company.benchmark_observation_start && <p className="mt-1 text-[9px] text-[var(--subtle)]">SPY window {company.benchmark_observation_start}–{company.benchmark_observation_end}</p>}</td><td className="px-3 py-3 text-[var(--muted)]">{company.common_session_count} aligned · {company.dropped_observed_sessions} observed gaps</td></tr>)}</tbody></table></div>
        <p className="border-t border-[var(--line-soft)] p-4 text-[10px] leading-5 text-[var(--subtle)]">{comparison.adjustment} Volatility uses sample standard deviation between consecutive common observations × √252 and is unavailable when selected-company coverage has observed gaps. Drawdown is measured on aligned common dates. Benchmark-relative return subtracts SPY return over identical start/end dates. Missing sessions are not filled.</p>
      </Panel>}

      <Panel className="mt-5 overflow-hidden">
        <PanelHeading title="Fundamentals and company data" detail="SEC values keep their reported period, filing date, source, and market-price date where relevant. Unavailable data is not estimated." action={Object.values(fundamentals).some((item) => item.error) || Object.values(news).some((item) => item.error) ? <button type="button" onClick={retryDetails} className="min-h-11 text-[11px] text-[var(--accent-strong)] hover:text-white">Retry fundamentals and news</button> : undefined} />
        {Object.keys(fundamentals).length === 0 ? <p className="p-4 text-xs text-[var(--muted)]" role="status">Select at least two companies to load fundamentals.</p> : <>
          <div className="grid gap-3 p-3 xl:hidden">{selected.map((company) => { const state = fundamentals[company.ticker]; const metrics = state?.data?.metrics ?? {}; return <article key={company.ticker} className="rounded-lg border border-[var(--line-soft)] bg-[var(--panel-soft)] p-4"><h3 className="text-sm font-semibold text-[var(--text)]">{company.name} <span className="text-[var(--accent-strong)]">{company.ticker}</span></h3><p className="mt-1 text-[10px] text-[var(--muted)]">{company.sector}{state?.data?.retrieved_at ? ` · SEC retrieved ${new Date(state.data.retrieved_at).toLocaleDateString()}` : ""}</p><dl className="mt-3 grid grid-cols-2 gap-3">{[["Market cap", "market_cap"], ["P/E", "pe_ratio"], ["EPS", "eps"], ["Revenue", "revenue"], ["Net income", "net_income"], ["Assets", "assets"], ["Liabilities", "liabilities"], ["Revenue growth", "revenue_growth"], ["Profit margin", "profit_margin"]].map(([label, key]) => { const metric = metrics[key] ?? null; return <div key={key} className="min-w-0"><dt className="text-[9px] uppercase tracking-wide text-[var(--subtle)]">{label}</dt><dd className="mt-1 text-xs tabular-nums text-[var(--text)]">{state?.loading ? "Loading…" : state?.error ? "Unavailable" : metricValue(metric, key)}</dd>{metric && <dd className="mt-1 break-words text-[9px] leading-4 text-[var(--subtle)]">{metric.period_type?.replaceAll("_", " ") ?? "Period unavailable"}{metric.period_end ? ` · ${metric.period_end}` : ""}{metric.filing_date ? ` · filed ${metric.filing_date}` : ""}{metric.price_as_of ? ` · price ${new Date(metric.price_as_of).toLocaleDateString()}` : ""}{metric.source ? ` · ${metric.source}` : ""}</dd>}</div>; })}</dl>{state?.error && <p role="status" className="mt-3 text-[10px] text-warning">{state.error}</p>}</article>; })}</div>
          <div className="hidden overflow-x-auto xl:block"><table className="w-full min-w-[1180px] text-left text-xs"><thead className="bg-[var(--panel-raised)] text-[10px] uppercase tracking-wide text-[var(--muted)]"><tr><th className="px-4 py-3">Company</th><th className="px-3 py-3">Market cap</th><th className="px-3 py-3">P/E</th><th className="px-3 py-3">EPS</th><th className="px-3 py-3">Revenue</th><th className="px-3 py-3">Net income</th><th className="px-3 py-3">Assets</th><th className="px-3 py-3">Liabilities</th><th className="px-3 py-3">Revenue growth</th><th className="px-3 py-3">Profit margin</th></tr></thead><tbody className="divide-y divide-[var(--line-soft)]">{selected.map((company) => <tr key={company.ticker}><td className="px-4 py-3 font-semibold text-[var(--text)]">{company.name}<p className="mt-1 text-[10px] font-normal text-[var(--muted)]">{company.ticker} · {company.sector}</p>{fundamentals[company.ticker]?.data?.retrieved_at && <p className="mt-1 text-[9px] font-normal text-[var(--subtle)]">SEC facts retrieved {new Date(fundamentals[company.ticker].data!.retrieved_at!).toLocaleDateString()}</p>}</td>{["market_cap", "pe_ratio", "eps", "revenue", "net_income", "assets", "liabilities", "revenue_growth", "profit_margin"].map((key) => { const metric = fundamentals[company.ticker]?.data?.metrics?.[key] ?? null; const state = fundamentals[company.ticker]; return <td key={key} className="px-3 py-3 text-[var(--muted)]">{state?.loading ? "Loading…" : state?.error ? "Unavailable" : metricValue(metric, key)}{metric && <p className="mt-1 max-w-40 text-[9px] leading-4 text-[var(--subtle)]">{metric.period_type?.replaceAll("_", " ") ?? "Period unavailable"}{metric.period_end ? ` · ${metric.period_end}` : ""}{metric.filing_date ? ` · filed ${metric.filing_date}` : ""}{metric.price_as_of ? ` · price ${new Date(metric.price_as_of).toLocaleDateString()}` : ""}{metric.source ? ` · ${metric.source}` : ""}</p>}{state?.error && <p className="mt-1 max-w-32 text-[9px] leading-4 text-warning">{state.error}</p>}</td>; })}</tr>)}</tbody></table></div>
        </>}
      </Panel>

      <Panel className="mt-5 overflow-hidden"><PanelHeading title="Technical context by company" detail="Market-context requests are deferred until requested to limit extra provider traffic. Results are observations, not predictions." />{selected.length > 0 && <div className="grid gap-px bg-[var(--line-soft)] md:grid-cols-2">{selected.map((company) => { const state = contexts[company.ticker]; return <section key={company.ticker} className="min-w-0 bg-[var(--panel)] p-4 sm:p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-xs font-semibold text-[var(--text)]">{company.name} <span className="text-[var(--accent-strong)]">{company.ticker}</span></h3><p className="mt-1 text-[10px] text-[var(--subtle)]">{company.sector}</p></div>{!state?.data && <button type="button" disabled={state?.loading} onClick={() => void loadContext(company.ticker)} className="rounded-md border border-[var(--line)] px-3 py-2 text-[10px] font-semibold text-[var(--muted)] hover:bg-[var(--panel-raised)] disabled:opacity-50">{state?.loading ? "Loading context…" : state?.error ? "Retry" : "Load technical context"}</button>}</div>{state?.error && <p role="status" className="mt-3 text-[10px] text-warning">{state.error}</p>}{state?.data && <><div className="mt-3 flex flex-wrap items-center gap-2"><StatusBadge tone="muted">{state.data.regime.label.replaceAll("_", " ")}</StatusBadge><span className="text-[9px] text-[var(--subtle)]">{state.data.latest_observation_date ?? "Date unavailable"}</span></div><p className="mt-2 text-[9px] leading-4 text-[var(--subtle)]">{state.data.regime.criteria}</p><div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">{[["RSI 14", "rsi_14"], ["20d momentum", "momentum_20d"], ["Relative return vs S&P", "relative_return_20d_vs_sp500"], ["Relative return vs sector", "relative_return_20d_vs_sector"], ["20d volatility", "historical_volatility_20d"], ["Volume / avg", "volume_vs_20d_average"]].map(([label, key]) => { const metric = state.data!.indicators[key]; return <div key={key} className="rounded-md border border-[var(--line-soft)] p-2"><p className="text-[9px] text-[var(--subtle)]">{label}</p><p className="mt-1 text-xs tabular-nums text-[var(--text)]">{contextValue(metric)}</p><p className="mt-1 text-[8px] leading-3 text-[var(--subtle)]">{metric?.observation_date ?? "No observation"} · {metric?.freshness ?? "unavailable"}</p></div>; })}</div><p className="mt-2 text-[9px] text-[var(--subtle)]">Source: {state.data.source} · as of {state.data.as_of_date}</p></>}</section>; })}</div>}</Panel>

      <Panel className="mt-5 overflow-hidden"><PanelHeading title="Recent news and sentiment coverage" detail="Coverage counts are shown separately from classified outputs. Sentiment is an article-level model signal, not a return predictor." />{selected.length > 0 && <div className="grid gap-px bg-[var(--line-soft)] md:grid-cols-2">{selected.map((company) => { const state = news[company.ticker]; const articles = state?.data ?? []; const classified = articles.filter((article) => article.sentiment_status === "processed" && article.sentiment); const unavailable = articles.filter((article) => ["model_unavailable", "inference_failed"].includes(article.sentiment_status)).length; const counts = ["positive", "neutral", "negative"].map((label) => ({ label, count: classified.filter((article) => article.sentiment?.toLowerCase() === label).length })); return <section key={company.ticker} className="min-w-0 bg-[var(--panel)] p-4 sm:p-5"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-xs font-semibold text-[var(--text)]">{company.name} <span className="text-[var(--accent-strong)]">{company.ticker}</span></h3><StatusBadge tone={state?.loading ? "muted" : state?.error ? "amber" : classified.length ? "blue" : "muted"}>{state?.loading ? "Loading" : state?.error ? "Unavailable" : `${classified.length}/${articles.length} classified`}</StatusBadge></div>{state?.error ? <p className="mt-3 text-[10px] text-warning">{state.error}</p> : state?.loading ? <p className="mt-3 text-[10px] text-[var(--muted)]">Loading recent stored news…</p> : <><div className="mt-3 flex flex-wrap gap-3 text-[10px] text-[var(--muted)]">{counts.map((item) => <span key={item.label} className="capitalize">{item.label} {item.count}</span>)}<span>Unclassified / unavailable {articles.length - classified.length}</span></div>{unavailable > 0 && <p className="mt-2 text-[9px] text-warning">{unavailable} article model output(s) failed or were unavailable; no sentiment was inferred here.</p>}<ul className="mt-3 space-y-2">{articles.slice(0, 3).map((article) => <li key={article.id} className="border-l border-[var(--line)] pl-2.5"><p className="line-clamp-2 text-[10px] leading-4 text-[var(--muted)]">{article.title}</p><p className="mt-1 text-[9px] text-[var(--subtle)]">{article.source} · {article.published_at ? new Date(article.published_at).toLocaleDateString() : "Date unavailable"} · {article.sentiment_status.replaceAll("_", " ")}{article.sentiment ? ` · ${article.sentiment}` : ""}</p></li>)}</ul>{articles.length === 0 && <p className="mt-3 text-[10px] text-[var(--muted)]">No stored company news is currently available.</p>}</>}</section>; })}</div>}</Panel>
      <p className="mt-4 text-[9px] leading-4 text-[var(--subtle)]">SEC CompanyFacts may be unavailable when SEC_USER_AGENT is not configured or a filing does not contain a supported tag. Yahoo adjusted daily prices are unofficial and can be revised after corporate actions. Sector labels use the existing S&amp;P 500 directory; SPY is an ETF benchmark proxy. Comparison is descriptive and not investment advice.</p>
    </>}
  </>;
}
