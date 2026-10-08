"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { CompanyCard, DemoNotice } from "@/components/cards";
import { Button, CompanyLink, DataTable, PageHeader, SearchInput, SentimentBadge, StatusBadge } from "@/components/ui";
import { demoCompanies } from "@/lib/demo-data";

export default function CompaniesPage() {
  const [query, setQuery] = useState("");
  const rows = useMemo(() => demoCompanies.filter((c) => `${c.ticker} ${c.name} ${c.sector}`.toLowerCase().includes(query.toLowerCase())), [query]);
  return (
    <>
      <PageHeader eyebrow="Coverage universe" title="Companies" description="Explore company coverage and analysis availability." action={<Button variant="secondary">Universe · 20</Button>} />
      <DemoNotice>Illustrative company directory based on the prototype ticker universe. Sentiment and event counts are demo labels, not current analysis results.</DemoNotice>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row">
        <SearchInput placeholder="Search company or ticker..." className="w-full sm:max-w-md" value={query} onChange={setQuery} />
        <div className="flex gap-2"><Button variant="secondary">Sector <span className="text-[#798591]">⌄</span></Button><Button variant="secondary">Analysis status <span className="text-[#798591]">⌄</span></Button></div>
        <Button variant="ghost" className="sm:ml-auto">Grid view</Button>
      </div>
      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {rows.slice(0, 3).map((company) => <CompanyCard key={company.ticker} {...company} />)}
      </div>
      <div className="overflow-hidden rounded-xl border border-[#252d36]">
        <DataTable headers={["Company", "Sector", "Latest sentiment", "Recent events", "Market regime", "Analysis"]}>
          {rows.map((company) => <tr key={company.ticker} className="transition-colors hover:bg-[#131920]">
            <td className="px-5 py-4"><CompanyLink ticker={company.ticker}>{company.name}</CompanyLink><p className="mt-1 text-[10px] text-[#76818d]">{company.ticker}</p></td>
            <td className="px-5 py-4 text-xs text-[#a2acb6]">{company.sector}</td>
            <td className="px-5 py-4"><SentimentBadge sentiment={company.sentiment} /></td>
            <td className="px-5 py-4 text-xs text-[#a2acb6]">{company.events} <span className="text-[10px] text-[#737f8a]">demo</span></td>
            <td className="px-5 py-4"><StatusBadge>Unavailable</StatusBadge></td>
            <td className="px-5 py-4"><Link href={`/companies/${company.ticker}`} className="text-xs text-[#afc0ff] hover:text-white">Open company →</Link></td>
          </tr>)}
        </DataTable>
        {!rows.length && <p className="bg-[#10151b] px-5 py-8 text-center text-xs text-[#89939f]">No companies match “{query}”.</p>}
      </div>
    </>
  );
}
