"use client";

import { useMemo, useState } from "react";
import { DemoNotice, EventCard } from "@/components/cards";
import { EmptyState, FilterBar, FilterSelect, PageHeader, Panel, PanelHeading, SearchInput, StatusBadge } from "@/components/ui";
import { demoNews } from "@/lib/demo-data";

export default function EventsPage() {
  const [query, setQuery] = useState("");
  const events = useMemo(() => demoNews.filter((item) => `${item.ticker} ${item.headline} ${item.eventType}`.toLowerCase().includes(query.toLowerCase())), [query]);
  return (
    <>
      <PageHeader eyebrow="Event intelligence" title="Events" description="A structured view of company-specific developments and their analysis readiness." action={<StatusBadge tone="amber">Illustrative records</StatusBadge>} />
      <DemoNotice>Example event records are mock UI content. No event extraction or market-reaction prediction has been performed.</DemoNotice>
      <Panel>
        <PanelHeading title="Event explorer" detail={`${events.length} illustrative entries`} />
        <div className="border-b border-[#252d36] p-4">
          <FilterBar>
            <SearchInput placeholder="Search company or event..." className="w-full sm:w-[260px]" value={query} onChange={setQuery} />
            <FilterSelect label="Event type" options={["Earnings", "Guidance", "Regulatory", "Product"]} />
            <FilterSelect label="Severity" options={["High", "Medium", "Low"]} />
            <FilterSelect label="Sentiment" options={["Positive", "Neutral", "Negative"]} />
            <FilterSelect label="Novelty" options={["Elevated", "Moderate", "Low"]} />
            <FilterSelect label="Date range" options={["Today", "7 days", "30 days"]} />
          </FilterBar>
        </div>
        <div className="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-3">
          {events.map((item) => <EventCard key={item.id} item={item} />)}
          {!events.length && <EmptyState title="No matching events" description="Adjust your search to see the demo event records." />}
        </div>
      </Panel>
    </>
  );
}
