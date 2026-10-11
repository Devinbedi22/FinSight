"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PageHeader, Panel, StatusBadge } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
type Company = { ticker: string; name: string; sector: string };

export default function PredictionsPage() {
  const router = useRouter();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [ticker, setTicker] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    void fetch(`${API}/universe/sp500`, { cache: "force-cache" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Company universe returned ${response.status}`);
        const data = await response.json();
        if (active) setCompanies(data.constituents ?? []);
      })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Could not load S&P 500."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  const matches = companies.filter((company) => `${company.ticker} ${company.name} ${company.sector}`.toLowerCase().includes(query.toLowerCase()));
  const selected = companies.find((company) => company.ticker === ticker.toUpperCase());
  return <>
    <PageHeader eyebrow="FinancialBERT Model v2 · S&P 500" title="Predictions" description="Open a company’s news-conditioned forecast and observed price history." action={<StatusBadge tone={error ? "red" : loading ? "muted" : "blue"}>{error || (loading ? "Loading companies" : `${companies.length} companies`)}</StatusBadge>} />
    <Panel className="p-5 sm:p-7">
      <label htmlFor="company-search" className="block text-sm font-medium text-[#e1e7ed]">Choose a company</label>
      <input id="company-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search ticker, company, or sector" className="mt-3 w-full max-w-xl rounded-lg border border-[#303a45] bg-[#0b1015] px-3 py-2.5 text-sm text-[#e2e8ef] placeholder:text-[#697581]" />
      {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}
      <div className="mt-4 max-h-[58vh] overflow-y-auto rounded-lg border border-[#252d36]">
        {matches.map((company) => <button key={company.ticker} onClick={() => setTicker(company.ticker)} className={`flex w-full items-center justify-between gap-4 border-b border-[#222a32] px-4 py-3 text-left last:border-0 hover:bg-[#151c24] ${ticker === company.ticker ? "bg-[#172130]" : ""}`}><span><span className="mr-3 inline-block w-14 font-semibold text-[#c5d3f6]">{company.ticker}</span><span className="text-sm text-[#d7dfe7]">{company.name}</span></span><span className="hidden text-xs text-[#77838f] sm:block">{company.sector}</span></button>)}
        {!loading && matches.length === 0 && <p className="p-4 text-sm text-[#89939f]">No matching S&amp;P 500 companies.</p>}
      </div>
      <div className="mt-4 flex items-center justify-between gap-4"><span className="text-xs text-[#74808c]">{selected ? `${selected.ticker} · ${selected.sector}` : "Select a company to open its prediction."}</span><button disabled={!selected} onClick={() => selected && router.push(`/companies/${selected.ticker}`)} className="rounded-lg bg-[#a9bcff] px-4 py-2.5 text-xs font-semibold text-[#101722] hover:bg-[#c4d0ff] disabled:cursor-not-allowed disabled:opacity-40">Open prediction →</button></div>
    </Panel>
  </>;
}
