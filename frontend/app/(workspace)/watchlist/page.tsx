"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { EmptyState, PageHeader, Panel, PanelHeading, StatusBadge } from "@/components/ui";
import { useWatchlist } from "@/components/watchlist";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const PAGE_SIZE = 4;
type Quote = { ticker: string; price: number | null; previous_close: number | null; change_percent: number | null; quote_time: string | null; quote_status: string; source?: string };
type Context = { status: string; latest_observation_date: string | null; regime: { label: string; criteria: string }; indicators: Record<string, { value: number | null; unit: string; observation_date: string | null; freshness: string }>; source: string };
type ContextState = { data?: Context; loading?: boolean; error?: string };

export default function WatchlistPage() {
  const watchlist = useWatchlist();
  const [page, setPage] = useState(0);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [quoteErrors, setQuoteErrors] = useState<Record<string, string>>({});
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [contextByTicker, setContextByTicker] = useState<Record<string, ContextState>>({});
  const [retry, setRetry] = useState(0);
  const visible = useMemo(() => watchlist.items.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE), [watchlist.items, page]);

  useEffect(() => {
    if (!watchlist.items.length) { setPage(0); return; }
    setPage((current) => Math.min(current, Math.max(0, Math.ceil(watchlist.items.length / PAGE_SIZE) - 1)));
  }, [watchlist.items.length]);

  useEffect(() => {
    if (!visible.length || watchlist.status !== "ready") return;
    let active = true;
    setQuoteLoading(true);
    setQuoteErrors({});
    void Promise.all(visible.map(async (company) => {
      try {
        const response = await fetch(`${API}/companies/${encodeURIComponent(company.ticker)}`, { cache: "no-store" });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail ?? `Quote returned ${response.status}`);
        return { ticker: company.ticker, data: data as Quote, error: "" };
      } catch (reason) {
        return { ticker: company.ticker, data: null, error: reason instanceof Error ? reason.message : "Latest price unavailable." };
      }
    })).then((results) => {
      if (!active) return;
      setQuotes((previous) => ({ ...previous, ...Object.fromEntries(results.flatMap((item) => item.data ? [[item.ticker, item.data] as const] : [])) }));
      setQuoteErrors(Object.fromEntries(results.filter((item) => item.error).map((item) => [item.ticker, item.error])));
    }).finally(() => { if (active) setQuoteLoading(false); });
    return () => { active = false; };
  }, [visible.map((item) => item.ticker).join(","), watchlist.status, retry]);

  const loadContext = async (ticker: string) => {
    setContextByTicker((previous) => ({ ...previous, [ticker]: { ...previous[ticker], loading: true, error: "" } }));
    try {
      const response = await fetch(`${API}/companies/${encodeURIComponent(ticker)}/market-context`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? `Market context returned ${response.status}`);
      setContextByTicker((previous) => ({ ...previous, [ticker]: { data: data as Context } }));
    } catch (reason) {
      setContextByTicker((previous) => ({ ...previous, [ticker]: { error: reason instanceof Error ? reason.message : "Market context unavailable." } }));
    }
  };

  const formattedContext = (metric: Context["indicators"][string] | undefined) => {
    if (!metric || metric.value == null) return "Unavailable";
    if (metric.unit === "ratio" || metric.unit === "annualized_ratio" || metric.unit === "percentage_points") return `${(metric.value * 100).toFixed(1)}%`;
    if (metric.unit === "index_0_100") return metric.value.toFixed(1);
    if (metric.unit === "USD") return `$${metric.value.toFixed(2)}`;
    if (metric.unit === "multiple") return `${metric.value.toFixed(2)}×`;
    return metric.value.toFixed(2);
  };

  return <>
    <PageHeader eyebrow="Personal workspace" title="Watchlist" description="Saved companies stay in this browser using local storage. They are not synced across devices or accounts." action={<StatusBadge tone={watchlist.status === "error" ? "amber" : "blue"}>Browser local</StatusBadge>} />
    <div className="mb-5 flex flex-wrap gap-2"><Link href="/companies" className="rounded-lg border border-[var(--line)] bg-[var(--panel-raised)] px-3.5 py-2.5 text-xs font-semibold text-[var(--text)] hover:bg-[var(--panel-raised)]">Find companies</Link><Link href="/compare" className="rounded-lg border border-[var(--line)] px-3.5 py-2.5 text-xs font-semibold text-[var(--text)] hover:bg-[var(--panel-raised)]">Compare stocks</Link></div>
    {watchlist.error && <div role="alert" className="mb-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs text-warning">{watchlist.error}{watchlist.errorKind === "invalid_data" ? <button type="button" onClick={watchlist.clearInvalidData} className="ml-2 min-h-11 rounded px-2 underline underline-offset-2">Discard corrupted local data</button> : watchlist.status === "error" ? <button type="button" onClick={watchlist.retryStorage} className="ml-2 min-h-11 rounded px-2 underline underline-offset-2">Retry storage</button> : null}</div>}
    <Panel className="overflow-hidden">
      <PanelHeading title="Saved companies" detail={`${watchlist.items.length} ${watchlist.items.length === 1 ? "company" : "companies"} saved on this browser`} action={quoteLoading ? <StatusBadge>Refreshing data</StatusBadge> : undefined} />
      {watchlist.status === "loading" ? <div className="space-y-3 p-5" role="status" aria-label="Loading watchlist">{[1, 2, 3].map((item) => <div key={item} className="h-24 animate-pulse rounded-lg bg-[var(--panel-raised)]" />)}</div> : watchlist.items.length === 0 ? <EmptyState title={watchlist.status === "error" ? "Watchlist storage unavailable" : "Your watchlist is empty"} description={watchlist.status === "error" ? "FinSight could not read saved companies from this browser." : "Search the company directory or open a company page and save it here for quick access."} action={<Link href="/companies" className="rounded-lg border border-[var(--line)] bg-[var(--panel-raised)] px-4 py-2.5 text-xs font-semibold text-[var(--text)]">Browse companies</Link>} /> : <>
        <div className="grid gap-px bg-[var(--line-soft)] md:grid-cols-2">
          {visible.map((company) => {
            const quote = quotes[company.ticker];
            const context = contextByTicker[company.ticker];
            return <article key={company.ticker} className="min-w-0 bg-[var(--panel)] p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><Link href={`/companies/${company.ticker}`} className="text-sm font-semibold text-[var(--text)] hover:text-white">{company.name} <span className="text-[var(--accent-strong)]">{company.ticker}</span></Link><p className="mt-1 text-[10px] text-[var(--muted)]">{company.sector || "Sector unavailable"}</p></div><button type="button" onClick={() => watchlist.remove(company.ticker)} disabled={watchlist.status !== "ready"} className="min-h-11 min-w-11 rounded-md border border-[var(--line)] px-3 text-[11px] text-[var(--muted)] hover:bg-[var(--panel-raised)] disabled:opacity-40">Remove</button></div>
              <div className="mt-4 grid grid-cols-2 gap-3 rounded-lg border border-[var(--line-soft)] bg-[var(--panel-soft)] p-3"><div><p className="text-[9px] uppercase tracking-wide text-[var(--subtle)]">Latest available close</p><p className="mt-1 text-sm font-semibold tabular-nums text-[var(--text)]">{!quote && quoteLoading ? "Loading…" : quote?.price == null ? "Unavailable" : `$${quote.price.toFixed(2)}`}</p></div><div><p className="text-[9px] uppercase tracking-wide text-[var(--subtle)]">Daily change</p><p className={`mt-1 text-sm font-semibold tabular-nums ${quote?.change_percent == null ? "text-[var(--muted)]" : quote.change_percent >= 0 ? "text-positive" : "text-negative"}`}>{!quote && quoteLoading ? "Loading…" : quote?.change_percent == null ? "Unavailable" : `${quote.change_percent >= 0 ? "+" : ""}${(quote.change_percent * 100).toFixed(2)}%`}</p></div><p className="col-span-2 text-[10px] text-[var(--subtle)]">Session {quote?.quote_time ? new Date(quote.quote_time).toLocaleDateString() : quoteLoading && !quote ? "loading" : "unavailable"}{quote?.source ? ` · ${quote.source}` : ""}</p></div>
              {quoteErrors[company.ticker] && <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[10px] text-warning" role="status"><span>{quoteErrors[company.ticker]}</span><button type="button" onClick={() => setRetry((value) => value + 1)} className="min-h-11 rounded px-2 underline underline-offset-2">Retry quotes</button></div>}
              <div className="mt-3 rounded-lg border border-[var(--line-soft)] p-3"><div className="flex flex-wrap items-center justify-between gap-2"><div><p className="text-[10px] font-semibold text-[var(--muted)]">Market context</p><p className="mt-1 text-[10px] text-[var(--subtle)]">Descriptive trend and momentum · not a forecast</p></div>{!context?.data && <button type="button" disabled={context?.loading} onClick={() => void loadContext(company.ticker)} className="min-h-11 rounded-md border border-[var(--line)] px-3 text-[11px] font-medium text-[var(--muted)] hover:bg-[var(--panel-raised)] disabled:opacity-50">{context?.loading ? "Loading…" : context?.error ? "Retry context" : "Load context"}</button>}</div>
                {context?.error && <p className="mt-2 text-[10px] text-warning" role="status">{context.error}</p>}
                {context?.data && <div className="mt-3"><p className="text-xs font-semibold capitalize text-[var(--text)]">{context.data.regime.label.replaceAll("_", " ")}</p><p className="mt-1 text-[9px] text-[var(--subtle)]">Observed {context.data.latest_observation_date ?? "date unavailable"} · {context.data.regime.criteria}</p><div className="mt-2 flex flex-wrap gap-2 text-[10px] text-[var(--muted)]"><span>RSI 14: {formattedContext(context.data.indicators.rsi_14)}</span><span>20d momentum: {formattedContext(context.data.indicators.momentum_20d)}</span><span>vs S&amp;P 500: {formattedContext(context.data.indicators.relative_return_20d_vs_sp500)}</span></div><p className="mt-2 text-[9px] text-[var(--subtle)]">Source: {context.data.source} · as of {context.data.latest_observation_date ?? "unavailable"}</p></div>}
              </div>
            </article>;
          })}
        </div>
        {watchlist.items.length > PAGE_SIZE && <div className="flex items-center justify-between border-t border-[var(--line-soft)] p-3 text-[10px] text-[var(--muted)]"><span>Showing {page * PAGE_SIZE + 1}–{page * PAGE_SIZE + visible.length} of {watchlist.items.length}</span><div className="flex gap-2"><button type="button" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))} className="min-h-11 rounded border border-[var(--line)] px-3 disabled:opacity-40">Previous</button><button type="button" disabled={(page + 1) * PAGE_SIZE >= watchlist.items.length} onClick={() => setPage((value) => value + 1)} className="min-h-11 rounded border border-[var(--line)] px-3 disabled:opacity-40">Next</button></div></div>}
      </>}
    </Panel>
  </>;
}
