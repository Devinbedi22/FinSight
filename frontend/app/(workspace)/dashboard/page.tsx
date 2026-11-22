"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EmptyState, PageHeader, Panel, PanelHeading, StatusBadge } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
type Company = { ticker: string; name: string; sector: string; price: number | null; change_percent: number | null; quote_time: string | null; quote_status: string };
type Directory = { status: string; detail: string; snapshot_date: string };
type Article = { id: number; title: string; source: string; published_at: string | null; ticker_candidates: { ticker: string; name: string }[] };

export default function DashboardPage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [articles, setArticles] = useState<Article[]>([]);
  const [companySource, setCompanySource] = useState("");
  const [directory, setDirectory] = useState<Directory | null>(null);
  const [marketError, setMarketError] = useState("");
  const [newsError, setNewsError] = useState("");
  const [marketLoading, setMarketLoading] = useState(true);
  const [newsLoading, setNewsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const loadMarket = async () => {
      try {
        for (let attempt = 0; active && attempt < 20; attempt += 1) {
          const response = await fetch(`${API}/companies?limit=12&offset=0`, { cache: "no-store" });
          if (!response.ok) throw new Error(`Market data returned ${response.status}`);
          const data = await response.json();
          const rows = (data.companies ?? []) as Company[];
          if (!active) return;
          setCompanies(rows);
          setCompanySource(data.source ?? "");
          setDirectory(data.directory ?? null);
          setMarketError("");
          setMarketLoading(false);
          if (!rows.some((company) => company.quote_status === "pending")) return;
          await new Promise((resolve) => window.setTimeout(resolve, 3000));
        }
      } catch (reason) {
        if (active) setMarketError(reason instanceof Error ? reason.message : "Market data is unavailable.");
      } finally {
        if (active) setMarketLoading(false);
      }
    };
    void loadMarket();
    void fetch(`${API}/news?limit=8`, { cache: "no-store" })
        .then(async (response) => {
          if (!response.ok) throw new Error(`News data returned ${response.status}`);
          return response.json() as Promise<Article[]>;
        })
        .then((data) => { if (active) setArticles(data); })
        .catch((reason: unknown) => { if (active) setNewsError(reason instanceof Error ? reason.message : "News is unavailable."); })
        .finally(() => { if (active) setNewsLoading(false); });
    return () => { active = false; };
  }, []);

  const availablePrices = companies.filter((company) => company.price != null);
  const positive = availablePrices.filter((company) => company.change_percent != null && company.change_percent > 0).length;
  const negative = availablePrices.filter((company) => company.change_percent != null && company.change_percent < 0).length;
  const latestQuote = availablePrices.map((company) => company.quote_time).filter((value): value is string => Boolean(value)).sort().at(-1);
  const quotesPending = companies.some((company) => company.quote_status === "pending");
  const quotesUnavailable = !marketLoading && !marketError && companies.length > 0 && availablePrices.length === 0 && !quotesPending;

  return <>
    <PageHeader eyebrow={directory?.status === "stale_limited_fallback" ? "Local market research snapshot" : "Market overview · S&P 500"} title="Market Overview" description="Available company-directory information, delayed market quotes, and the latest stored financial news." action={<StatusBadge tone={marketError || newsError || quotesUnavailable || directory?.status === "stale_limited_fallback" ? "amber" : marketLoading || newsLoading ? "muted" : "green"}>{marketError || newsError || quotesUnavailable || directory?.status === "stale_limited_fallback" ? "Partial data" : marketLoading || newsLoading ? "Loading" : "API connected"}</StatusBadge>} />
    {directory?.status === "stale_limited_fallback" && <div role="status" className="mb-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs leading-5 text-warning">{directory.detail}</div>}
    {quotesUnavailable && <div role="status" className="mb-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs leading-5 text-warning">Company information is available, but Yahoo Finance returned no current quotes. Prices and daily moves remain unavailable rather than estimated.</div>}
    {(marketError || newsError) && <div role="status" className="mb-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs text-warning">{[marketError, newsError].filter(Boolean).join(" · ")} Check that the backend is running at {API}.</div>}

    <div className="mb-5 grid gap-3 sm:grid-cols-3">
      <div className="rounded-xl border border-[var(--line-soft)] bg-[var(--panel)] p-4"><p className="text-xs text-[var(--muted)]">Companies shown</p><p className="mt-3 text-2xl font-semibold tabular-nums text-[var(--text)]">{marketLoading ? "—" : marketError ? "Unavailable" : companies.length}</p><p className="mt-1 text-[11px] text-[var(--subtle)]">{marketLoading ? "Loading company directory" : directory?.status === "stale_limited_fallback" ? "Limited local research symbols" : "First page of S&P 500 constituents"}</p></div>
      <div className="rounded-xl border border-[var(--line-soft)] bg-[var(--panel)] p-4"><p className="text-xs text-[var(--muted)]">Quotes available</p><p className="mt-3 text-2xl font-semibold tabular-nums text-[var(--text)]">{marketLoading ? "—" : marketError ? "Unavailable" : `${availablePrices.length} / ${companies.length}`}</p><p className="mt-1 text-[11px] text-[var(--subtle)]">{latestQuote ? `Latest quote date ${new Date(latestQuote).toLocaleDateString()}` : "Latest daily close, when available"}</p></div>
      <div className="rounded-xl border border-[var(--line-soft)] bg-[var(--panel)] p-4"><p className="text-xs text-[var(--muted)]">Daily direction</p><p className="mt-3 text-2xl font-semibold tabular-nums text-[var(--text)]">{marketLoading || quotesPending ? "Loading" : marketError || quotesUnavailable ? "Unavailable" : `${positive} up · ${negative} down`}</p><p className="mt-1 text-[11px] text-[var(--subtle)]">Among the companies shown with quote changes</p></div>
    </div>

    <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
      <Panel className="min-w-0 overflow-hidden">
        <PanelHeading title="Company snapshot" detail={companySource || (marketLoading ? "Loading available market data…" : "S&P 500 companies and latest available daily closes")} action={<Link href="/companies" className="shrink-0 text-xs text-[var(--accent-strong)] hover:text-white">All companies →</Link>} />
        {marketLoading ? <p className="p-6 text-xs text-[var(--muted)]" role="status">Loading company quotes…</p> : marketError ? <EmptyState title="Market data unavailable" description="The existing company endpoint could not provide a market snapshot. Company and price APIs remain available when the backend and data source respond." action={<Link href="/companies" className="text-xs text-[var(--accent-strong)]">Open companies</Link>} /> : companies.length === 0 ? <EmptyState title="No company data available" description="The company endpoint returned no rows. No sample prices are shown." /> : <div className="overflow-x-auto"><table className="w-full min-w-[540px] text-left"><thead className="bg-[var(--panel-soft)] text-[10px] uppercase tracking-wide text-[var(--subtle)]"><tr><th className="px-4 py-3 font-medium">Company</th><th className="px-4 py-3 font-medium">Sector</th><th className="px-4 py-3 text-right font-medium">Latest close</th><th className="px-4 py-3 text-right font-medium">Day change</th></tr></thead><tbody>{companies.map((company) => <tr key={company.ticker} className="border-t border-[var(--line-soft)] text-xs hover:bg-[var(--panel-soft)]"><td className="px-4 py-3"><Link href={`/companies/${company.ticker}`} className="font-medium text-[var(--text)] hover:text-white">{company.ticker}<span className="ml-2 hidden text-[var(--muted)] sm:inline">{company.name}</span></Link></td><td className="max-w-40 truncate px-4 py-3 text-[var(--muted)]">{company.sector}</td><td className="px-4 py-3 text-right tabular-nums text-[var(--text)]">{company.price == null ? company.quote_status === "pending" ? "Fetching…" : "Unavailable" : `$${company.price.toFixed(2)}`}</td><td className={`px-4 py-3 text-right tabular-nums ${company.change_percent == null ? "text-[var(--muted)]" : company.change_percent >= 0 ? "text-positive" : "text-negative"}`}>{company.change_percent == null ? "Unavailable" : `${company.change_percent >= 0 ? "+" : ""}${(company.change_percent * 100).toFixed(2)}%`}</td></tr>)}</tbody></table></div>}
        {!marketLoading && !marketError && companies.length > 0 && <p className="border-t border-[var(--line-soft)] px-4 py-3 text-[10px] text-[var(--subtle)]">{companySource || "Latest available daily close; not real-time."}</p>}
      </Panel>

      <Panel className="min-w-0 overflow-hidden">
        <PanelHeading title="Latest financial news" detail="Newest stories currently stored by FinSight" action={<Link href="/news" className="shrink-0 text-xs text-[var(--accent-strong)] hover:text-white">News archive →</Link>} />
        {newsLoading ? <p className="p-6 text-xs text-[var(--muted)]" role="status">Loading stored news…</p> : newsError ? <EmptyState title="News unavailable" description="The news endpoint could not be reached. No sample headlines are substituted." action={<Link href="/news" className="text-xs text-[var(--accent-strong)]">Open news</Link>} /> : articles.length === 0 ? <EmptyState title="No stories stored yet" description="The news feed has not returned any archived stories. Check ingestion status on the News page." action={<Link href="/news" className="text-xs text-[var(--accent-strong)]">View news archive</Link>} /> : <div>{articles.map((article) => <article key={article.id} className="border-b border-[var(--line-soft)] px-4 py-4 last:border-0"><div className="flex flex-wrap items-center gap-2 text-[10px] text-[var(--subtle)]"><span className="font-medium text-[var(--muted)]">{article.source}</span><span aria-hidden="true">·</span><time dateTime={article.published_at ?? undefined}>{article.published_at ? new Date(article.published_at).toLocaleString() : "Date unavailable"}</time></div><Link href="/news" className="mt-2 block text-sm leading-6 text-[var(--text)] hover:text-white">{article.title}</Link>{article.ticker_candidates?.length > 0 && <p className="mt-2 text-[10px] text-[var(--subtle)]">Matched: {article.ticker_candidates.slice(0, 4).map((candidate) => candidate.ticker).join(" · ")}</p>}</article>)}</div>}
      </Panel>
    </div>
    <p className="mt-4 text-[10px] text-[var(--subtle)]">Market quotes are delayed latest available adjusted daily closes through yfinance. News and quotes can be unavailable or stale; check source dates before relying on them.</p>
  </>;
}
