"use client";

import { useState } from "react";
import Link from "next/link";
import { DemoNotice } from "@/components/cards";
import { Button, CompanyLink, DataTable, EmptyState, PageHeader, SearchInput, SentimentBadge, StatusBadge } from "@/components/ui";
import { demoCompanies } from "@/lib/demo-data";

export default function WatchlistPage() {
  const [tickers, setTickers] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const candidates = demoCompanies.filter((item) => !tickers.includes(item.ticker) && `${item.ticker} ${item.name}`.toLowerCase().includes(query.toLowerCase()));
  const saved = demoCompanies.filter((item) => tickers.includes(item.ticker));
  return (
    <>
      <PageHeader eyebrow="Personal workspace" title="Watchlist" description="Keep a focused view of companies and their latest analysis status." action={<StatusBadge>Local UI only</StatusBadge>} />
      <DemoNotice>Watchlist changes are stored only in this page's temporary browser state and will reset when you leave. No account or persistence is connected.</DemoNotice>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center"><SearchInput placeholder="Find a company to add..." className="w-full sm:max-w-md" value={query} onChange={setQuery} /><span className="text-[11px] text-[#7a8691] sm:ml-auto">{saved.length} saved in this session</span></div>
      <div className="mb-6 flex flex-wrap gap-2">
        {candidates.slice(0, 6).map((company) => <button key={company.ticker} onClick={() => setTickers((current) => [...current, company.ticker])} className="inline-flex items-center gap-2 rounded-md border border-[#303a45] bg-[#12181f] px-3 py-2 text-[11px] text-[#b9c3cc] transition-colors hover:border-[#6177aa] hover:text-white"><span className="text-[#c5d3f3]">{company.ticker}</span><span className="text-[#78838e]">＋</span></button>)}
        {candidates.length === 0 && <span className="text-xs text-[#76818c]">No more demo companies match.</span>}
      </div>
      {saved.length ? (
        <div className="overflow-hidden rounded-xl border border-[#252d36]">
          <DataTable headers={["Company", "Sector", "Latest event", "Sentiment", "Market condition", "Analysis", ""]}>
            {saved.map((company) => <tr key={company.ticker} className="hover:bg-[#131920]">
              <td className="px-5 py-4"><CompanyLink ticker={company.ticker}>{company.name}</CompanyLink><p className="mt-1 text-[10px] text-[#76818d]">{company.ticker}</p></td>
              <td className="px-5 py-4 text-xs text-[#a2acb6]">{company.sector}</td>
              <td className="px-5 py-4 text-xs text-[#89939f]">No analyzed event</td>
              <td className="px-5 py-4"><SentimentBadge sentiment={company.sentiment} /></td>
              <td className="px-5 py-4"><StatusBadge>Unavailable</StatusBadge></td>
              <td className="px-5 py-4 text-xs text-[#89939f]">No analysis yet</td>
              <td className="px-5 py-4"><button onClick={() => setTickers((current) => current.filter((ticker) => ticker !== company.ticker))} className="text-[10px] text-[#8b96a2] hover:text-rose-300">Remove</button></td>
            </tr>)}
          </DataTable>
        </div>
      ) : <div className="rounded-xl border border-[#252d36] bg-[#10151b]"><EmptyState title="Your watchlist is empty" description="Add one of the illustrative companies above to preview the watchlist layout." action={<Link href="/companies" className="text-xs font-semibold text-[#b2c1fb]">Browse companies →</Link>} /></div>}
      <div className="mt-4 flex items-center gap-2 text-[10px] text-[#75808c]"><Button variant="secondary" disabled>Add company</Button><span>Company directory is demo content.</span></div>
    </>
  );
}
