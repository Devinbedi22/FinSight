"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EmptyState, PageHeader, Panel, PanelHeading, SearchInput, StatusBadge } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
type Company = { ticker: string; name: string; sector: string; price: number | null; previous_close: number | null; change_percent: number | null; quote_time: string | null; quote_status: string };
type Directory = { status: string; source: string; snapshot_date: string; detail: string };

export default function CompaniesPage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [source, setSource] = useState("");
  const [directory, setDirectory] = useState<Directory | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setOffset(0);
      setSearch(query.trim());
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      for (let attempt = 0; active && attempt < 20; attempt += 1) {
        try {
          const params = new URLSearchParams({ limit: "50", offset: String(offset) });
          if (search) params.set("search", search);
          const response = await fetch(`${API}/companies?${params}`, { cache: "no-store" });
          const data = await response.json();
          if (!response.ok) throw new Error(data.detail ?? `API returned ${response.status}`);
          if (!active) return;
          const rows = (data.companies ?? []) as Company[];
          setCompanies(rows);
          setSource(data.source ?? "");
          setDirectory(data.directory ?? null);
          setTotal(data.total ?? 0);
          setError("");
          setLoading(false);
          if (!rows.some((company) => company.quote_status === "pending")) return;
        } catch (reason) {
          if (active) {
            setError(reason instanceof Error ? reason.message : "Could not load companies.");
            setLoading(false);
          }
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 3000));
      }
      if (active) setLoading(false);
    };
    void load();
    return () => { active = false; };
  }, [offset, search]);

  return <>
    <PageHeader eyebrow={directory?.status === "stale_limited_fallback" ? "Limited local research universe" : "Live company coverage"} title="Companies" description={directory?.status === "stale_limited_fallback" ? "Search the dated local research ticker set. Current S&P 500 membership is not verified; quotes are requested separately." : "Search and browse S&P 500 constituents. Quotes show the latest available daily market values."} action={<StatusBadge tone={error ? "red" : loading ? "muted" : directory?.status === "stale_limited_fallback" ? "amber" : "green"}>{loading ? "Loading" : error ? "API unavailable" : directory?.status === "stale_limited_fallback" ? "Limited snapshot" : `${total} matches`}</StatusBadge>} />
    {directory?.status === "stale_limited_fallback" && <div role="status" className="mb-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs leading-5 text-warning">{directory.detail}</div>}
    {error && <div role="status" className="mb-4 rounded-lg border border-negative/30 bg-negative/10 p-3 text-xs text-negative">{error}. Confirm the backend and market-data connection are running.</div>}
    <Panel className="overflow-hidden">
      <PanelHeading title={directory?.status === "stale_limited_fallback" ? "Locally supported companies" : "S&P 500 directory"} detail={source || (loading ? "Fetching companies and quotes…" : "Search is filtered on the server before quotes are requested.")} />
      <div className="border-b border-[var(--line-soft)] p-4"><SearchInput placeholder="Search all companies by name, ticker, or sector…" className="w-full sm:max-w-md" value={query} onChange={setQuery} /></div>
      {loading && companies.length === 0 ? <p className="p-6 text-xs text-[var(--muted)]" role="status">Loading company list…</p> : companies.length ? <>
        <div className="overflow-x-auto"><table className="w-full min-w-[780px] text-left"><thead className="bg-[var(--panel-soft)] text-[10px] uppercase tracking-wide text-[var(--subtle)]"><tr>{["Company", "Ticker", "Sector", "Latest close", "Day change", "Quote date"].map((heading) => <th key={heading} className="px-4 py-3 font-medium">{heading}</th>)}</tr></thead><tbody>{companies.map((company) => <tr key={company.ticker} className="border-t border-[var(--line-soft)] text-xs hover:bg-[var(--panel-soft)]"><td className="px-4 py-3"><Link className="font-medium text-[var(--text)] hover:text-white" href={`/companies/${company.ticker}`}>{company.name}</Link></td><td className="px-4 py-3 font-semibold text-[var(--accent-strong)]">{company.ticker}</td><td className="px-4 py-3 text-[var(--muted)]">{company.sector}</td><td className="px-4 py-3 tabular-nums text-[var(--text)]">{company.price == null ? company.quote_status === "pending" ? "Fetching…" : "Unavailable" : `$${company.price.toFixed(2)}`}</td><td className={`px-4 py-3 tabular-nums ${company.change_percent == null ? "text-[var(--muted)]" : company.change_percent >= 0 ? "text-positive" : "text-negative"}`}>{company.change_percent == null ? company.quote_status === "pending" ? "Fetching…" : "Unavailable" : `${company.change_percent >= 0 ? "+" : ""}${(company.change_percent * 100).toFixed(2)}%`}</td><td className="px-4 py-3 text-[var(--muted)]">{company.quote_time ? new Date(company.quote_time).toLocaleDateString() : "Unavailable"}</td></tr>)}</tbody></table></div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line-soft)] p-3 text-[10px] text-[var(--muted)]"><span>{total === 0 ? "Showing 0 companies" : `Showing ${offset + 1}–${offset + companies.length} of ${total}`}{loading ? " · refreshing quotes" : ""}</span><div className="flex gap-2"><button disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - 50))} className="rounded border border-[var(--line)] px-3 py-1.5 disabled:opacity-40">Previous</button><button disabled={offset + companies.length >= total || loading} onClick={() => setOffset(offset + 50)} className="rounded border border-[var(--line)] px-3 py-1.5 disabled:opacity-40">Next</button></div></div>
      </> : <EmptyState title={error ? "Company data unavailable" : "No matching companies"} description={error ? "The companies endpoint could not return constituent and quote data." : `No S&P 500 companies match “${query}”.`} />}
    </Panel>
    <p className="mt-3 text-[10px] text-[var(--subtle)]">Quotes are latest available adjusted daily closes from Yahoo Finance through yfinance—not real-time quotes. {directory?.status === "stale_limited_fallback" ? "Sector labels are ETF proxy groupings; directory membership is limited to the local research universe." : "Sector labels are from the S&P constituent dataset."}</p>
  </>;
}
