"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { WatchlistButton } from "@/components/watchlist";
import { SearchInput } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
export type CompanyOption = { ticker: string; name: string; sector: string; price?: number | null; quote_time?: string | null };

export function CompanySearch({
  selectedTickers = [],
  onSelect,
  disabled = false,
}: {
  selectedTickers?: string[];
  onSelect?: (company: CompanyOption) => void;
  disabled?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CompanyOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [directoryNote, setDirectoryNote] = useState("");

  useEffect(() => {
    const search = query.trim();
    if (!search) { setResults([]); setError(""); setLoading(false); return; }
    let active = true;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`${API}/companies?limit=8&include_quotes=false&search=${encodeURIComponent(search)}`, { cache: "no-store" });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail ?? `Company search returned ${response.status}`);
        if (active) {
          setResults((data.companies ?? []) as CompanyOption[]);
          setDirectoryNote(data.directory?.status === "stale_limited_fallback" ? data.directory.detail : "");
        }
      } catch (reason) {
        if (active) { setResults([]); setError(reason instanceof Error ? reason.message : "Company search is unavailable."); }
      } finally { if (active) setLoading(false); }
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [query]);

  return <div className="space-y-2">
    <SearchInput ariaLabel="Search companies by name or ticker" placeholder="Search by company name or ticker…" value={query} onChange={setQuery} className="w-full" />
    {loading && <p className="text-[10px] text-[var(--muted)]" role="status">Searching the company directory…</p>}
    {error && <p className="text-[10px] text-negative" role="alert">{error}</p>}
    {directoryNote && <p className="rounded-md border border-warning/30 bg-warning/10 p-2.5 text-[10px] leading-4 text-warning" role="status">{directoryNote}</p>}
    {!loading && !error && query.trim() && results.length === 0 && <p className="text-[10px] text-[var(--muted)]">No S&amp;P 500 companies matched “{query.trim()}”.</p>}
    {results.length > 0 && <ul className="max-h-80 divide-y divide-[var(--line-soft)] overflow-y-auto rounded-lg border border-[var(--line-soft)] bg-[var(--panel-soft)]" aria-label="Company search results">
      {results.map((company) => {
        const selected = selectedTickers.includes(company.ticker);
        return <li key={company.ticker} className="flex flex-wrap items-center justify-between gap-2 p-3">
          <div className="min-w-0"><Link href={`/companies/${company.ticker}`} className="truncate text-xs font-semibold text-[var(--text)] hover:text-white">{company.name} <span className="text-[var(--accent-strong)]">{company.ticker}</span></Link><p className="mt-1 text-[10px] text-[var(--subtle)]">{company.sector}</p></div>
          <div className="flex flex-wrap items-center gap-2">
            {onSelect && <button type="button" disabled={selected || disabled} onClick={() => onSelect(company)} className="min-h-11 rounded-lg border border-[var(--line)] px-3 py-2 text-[11px] font-semibold text-[var(--text)] hover:bg-[var(--panel-raised)] disabled:cursor-not-allowed disabled:opacity-40">{selected ? "Added" : "Add to comparison"}</button>}
            <WatchlistButton company={{ ticker: company.ticker, name: company.name, sector: company.sector }} className="min-h-11 px-2.5 py-2 text-[11px]" />
          </div>
        </li>;
      })}
    </ul>}
  </div>;
}
