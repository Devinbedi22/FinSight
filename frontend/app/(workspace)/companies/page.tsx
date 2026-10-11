"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { EmptyState, PageHeader, Panel, PanelHeading, SearchInput, StatusBadge } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
type Company = { ticker: string; name: string; sector: string; price: number | null; previous_close: number | null; change_percent: number | null; quote_time: string | null; quote_status: string };

export default function CompaniesPage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [source, setSource] = useState("");
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    let active = true;
    const load = async () => {
      for (let attempt = 0; active && attempt < 20; attempt += 1) {
        try {
          const response = await fetch(`${API}/companies?limit=50&offset=${offset}`, { cache: "no-store" });
          if (!response.ok) throw new Error((await response.json()).detail ?? `API returned ${response.status}`);
          const data = await response.json();
          if (!active) return;
          setCompanies(data.companies); setSource(data.source); setTotal(data.total); setError(""); setLoading(false);
          if (!data.companies.some((company: Company) => company.quote_status === "pending")) return;
        } catch (reason) {
          if (active) setError(reason instanceof Error ? reason.message : "Could not load companies.");
          if (active) setLoading(false);
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 3000));
      }
    };
    void load();
    return () => { active = false; };
  }, [offset]);
  const rows = useMemo(() => companies.filter((company) => `${company.ticker} ${company.name} ${company.sector}`.toLowerCase().includes(query.toLowerCase())), [companies, query]);
  return <>
    <PageHeader eyebrow="Live company coverage" title="Companies" description="S&P 500 constituents with the latest available daily market values." action={<StatusBadge tone={error ? "red" : "green"}>{loading ? "Loading" : error ? "API unavailable" : `${companies.length} companies`}</StatusBadge>} />
    {error && <div className="mb-4 rounded-lg border border-red-900/50 bg-red-950/20 p-3 text-xs text-red-200">{error}. Confirm the backend and market-data connection are running.</div>}
    <Panel>
      <PanelHeading title="S&P 500" detail={source || (loading ? "Fetching constituents and quotes…" : "Company directory and quotes")} />
      <div className="border-b border-[#252d36] p-4"><SearchInput placeholder="Search company, ticker, or sector…" className="w-full sm:max-w-md" value={query} onChange={setQuery} /></div>
      {loading ? <p className="p-6 text-xs text-[#89939f]">Loading company list…</p> : rows.length ? <><div className="overflow-x-auto"><table className="w-full min-w-[780px] text-left"><thead className="bg-[#11171d] text-[10px] uppercase tracking-wide text-[#77838f]"><tr>{["Company", "Ticker", "Sector", "Latest close", "Day change", "Quote date"].map((heading) => <th key={heading} className="px-4 py-3 font-medium">{heading}</th>)}</tr></thead><tbody>{rows.map((company) => <tr key={company.ticker} className="border-t border-[#222a32] text-xs hover:bg-[#131920]"><td className="px-4 py-3"><Link className="font-medium text-[#dce2e8] hover:text-white" href={`/companies/${company.ticker}`}>{company.name}</Link></td><td className="px-4 py-3 font-semibold text-[#bdcbef]">{company.ticker}</td><td className="px-4 py-3 text-[#a2acb6]">{company.sector}</td><td className="px-4 py-3 tabular-nums text-[#dce2e8]">{company.price == null ? company.quote_status === "pending" ? "Fetching…" : "Unavailable" : `$${company.price.toFixed(2)}`}</td><td className={`px-4 py-3 tabular-nums ${company.change_percent == null ? "text-[#89939f]" : company.change_percent >= 0 ? "text-emerald-300" : "text-rose-300"}`}>{company.change_percent == null ? company.quote_status === "pending" ? "Fetching…" : "Unavailable" : `${company.change_percent >= 0 ? "+" : ""}${(company.change_percent * 100).toFixed(2)}%`}</td><td className="px-4 py-3 text-[#89939f]">{company.quote_time ? new Date(company.quote_time).toLocaleDateString() : "Unavailable"}</td></tr>)}</tbody></table></div><div className="flex items-center justify-between border-t border-[#252d36] p-3 text-[10px] text-[#89939f]"><span>Showing {offset + 1}–{offset + companies.length} of {total}</span><div className="flex gap-2"><button disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - 50))} className="rounded border border-[#394555] px-3 py-1.5 disabled:opacity-40">Previous</button><button disabled={offset + companies.length >= total || loading} onClick={() => setOffset(offset + 50)} className="rounded border border-[#394555] px-3 py-1.5 disabled:opacity-40">Next</button></div></div></> : <EmptyState title={error ? "Company data unavailable" : "No matching companies"} description={error ? "The companies endpoint could not return live constituent and quote data." : `No S&P 500 companies match “${query}”.`} />}
    </Panel>
    <p className="mt-3 text-[10px] text-[#65717d]">Quotes are latest available adjusted daily closes from Yahoo Finance through yfinance—not real-time quotes. Sector labels are from the S&P constituent dataset.</p>
  </>;
}
