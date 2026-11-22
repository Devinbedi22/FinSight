"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PageHeader, Panel, StatusBadge } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
type Company = { ticker: string; name: string; sector: string };
type Directory = { status: string; detail: string };

export default function PredictionsPage() {
  const router = useRouter();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [ticker, setTicker] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [directory, setDirectory] = useState<Directory | null>(null);
  useEffect(() => {
    let active = true;
    void fetch(`${API}/universe/sp500`, { cache: "force-cache" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Company universe returned ${response.status}`);
        const data = await response.json();
        if (active) { setCompanies(data.constituents ?? []); setDirectory(data.directory ?? null); }
      })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Could not load S&P 500."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  const matches = companies.filter((company) => `${company.ticker} ${company.name} ${company.sector}`.toLowerCase().includes(query.toLowerCase()));
  const selected = companies.find((company) => company.ticker === ticker.toUpperCase());
  return <>
    <PageHeader eyebrow={directory?.status === "stale_limited_fallback" ? "FinancialBERT · local research universe" : "FinancialBERT Model v2 · S&P 500"} title="Predictions" description="Open a company’s existing experimental news-conditioned forecast and observed price history." action={<StatusBadge tone={error ? "red" : loading ? "muted" : directory?.status === "stale_limited_fallback" ? "amber" : "blue"}>{error || (loading ? "Loading companies" : `${companies.length} companies`)}</StatusBadge>} />
    {directory?.status === "stale_limited_fallback" && <div role="status" className="mb-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs leading-5 text-warning">{directory.detail} Price and forecast inputs still depend on their existing providers and may be unavailable.</div>}
    <Panel className="p-5 sm:p-7">
      <label htmlFor="company-search" className="block text-sm font-medium text-[var(--text)]">Choose a company</label>
      <input id="company-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search ticker, company, or sector" className="mt-3 w-full max-w-xl rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] px-3 py-2.5 text-sm text-[var(--text)] placeholder:text-[var(--subtle)]" />
      {error && <p className="mt-2 text-xs text-negative">{error}</p>}
      <div className="mt-4 max-h-[58vh] overflow-y-auto rounded-lg border border-[var(--line-soft)]">
        {matches.map((company) => <button key={company.ticker} onClick={() => setTicker(company.ticker)} className={`flex w-full items-center justify-between gap-4 border-b border-[var(--line-soft)] px-4 py-3 text-left last:border-0 hover:bg-[var(--panel-raised)] focus-ring ${ticker === company.ticker ? "bg-accent/15" : ""}`}><span><span className="mr-3 inline-block w-14 font-semibold text-[var(--accent-strong)]">{company.ticker}</span><span className="text-sm text-[var(--text)]">{company.name}</span></span><span className="hidden text-xs text-[var(--subtle)] sm:block">{company.sector}</span></button>)}
        {!loading && matches.length === 0 && <p className="p-4 text-sm text-[var(--muted)]">No matching supported companies.</p>}
      </div>
      <div className="mt-4 flex items-center justify-between gap-4"><span className="text-xs text-[var(--subtle)]">{selected ? `${selected.ticker} · ${selected.sector}` : "Select a company to open its prediction."}</span><button disabled={!selected} onClick={() => selected && router.push(`/companies/${selected.ticker}`)} className="min-h-11 rounded-lg bg-accent px-4 py-2.5 text-xs font-semibold text-[#241f32] hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-40">Open prediction →</button></div>
    </Panel>
  </>;
}
