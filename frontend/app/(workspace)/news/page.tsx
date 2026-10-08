"use client";

import { useMemo, useState } from "react";
import { DemoNotice, NewsCard } from "@/components/cards";
import { Button, EmptyState, FilterBar, FilterSelect, Icon, PageHeader, Panel, PanelHeading, SearchInput, StatusBadge } from "@/components/ui";
import { demoNews } from "@/lib/demo-data";

export default function NewsPage() {
  const [query, setQuery] = useState("");
  const [sentiment, setSentiment] = useState("All sentiment");
  const filtered = useMemo(() => demoNews.filter((item) =>
    `${item.ticker} ${item.company} ${item.headline}`.toLowerCase().includes(query.toLowerCase()) &&
    (sentiment === "All sentiment" || item.sentiment === sentiment),
  ), [query, sentiment]);

  return (
    <>
      <PageHeader eyebrow="Intelligence feed" title="News" description="Company-linked headlines with sentiment and event context." action={<StatusBadge tone="amber">Demo feed</StatusBadge>} />
      <DemoNotice />
      <Panel>
        <PanelHeading title="News stream" detail={`${filtered.length} illustrative headlines`} action={<Button variant="ghost"><Icon name="sliders" size={15} />Display</Button>} />
        <div className="border-b border-[#252d36] p-4">
          <FilterBar>
            <SearchInput placeholder="Search headlines or ticker..." className="w-full sm:w-[280px]" value={query} onChange={setQuery} />
            <select value={sentiment} onChange={(e) => setSentiment(e.target.value)} className="rounded-lg border border-[#29323c] bg-[#10151b] px-3 py-2.5 text-xs text-[#b8c1ca]">
              {["All sentiment", "Positive", "Neutral", "Negative"].map((value) => <option key={value}>{value}</option>)}
            </select>
            <FilterSelect label="Event type" options={["Earnings", "Guidance", "Regulatory", "Product"]} />
            <FilterSelect label="Date range" options={["Today", "7 days", "30 days"]} />
            <span className="ml-auto hidden items-center gap-1.5 text-[10px] text-[#78838e] md:flex"><Icon name="calendar" size={14} />Local demo data</span>
          </FilterBar>
          <div className="mt-3 flex gap-2 overflow-x-auto pb-0.5">
            {["All companies", "AAPL", "MSFT", "NVDA", "TSLA"].map((ticker, index) => <button key={ticker} className={`whitespace-nowrap rounded-md px-2.5 py-1.5 text-[10px] ${index === 0 ? "bg-[#252e39] text-[#e0e6ec]" : "text-[#87929e] hover:bg-[#1a2027] hover:text-white"}`}>{ticker}</button>)}
          </div>
        </div>
        {filtered.length ? filtered.map((item) => <NewsCard key={item.id} item={item} />) : <EmptyState title="No matching headlines" description="Try a broader search or change your selected sentiment." />}
      </Panel>
      <p className="mt-3 text-[10px] text-[#68737e]">Headline examples are illustrative UI content and do not represent a current news feed.</p>
    </>
  );
}
