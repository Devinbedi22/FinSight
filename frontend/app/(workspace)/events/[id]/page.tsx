import Link from "next/link";
import { DemoNotice, EventCard } from "@/components/cards";
import { Button, EmptyState, PageHeader, Panel, PanelHeading, SentimentBadge, StatCard, StatusBadge } from "@/components/ui";
import { demoNews } from "@/lib/demo-data";

export default async function EventDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const item = demoNews.find((event) => event.id === id) ?? demoNews[0];
  return (
    <>
      <div className="mb-5 text-[11px] text-[#75808c]"><Link href="/events" className="hover:text-white">Events</Link><span className="px-2">/</span>{item.id}</div>
      <PageHeader eyebrow={`${item.ticker} · ${item.time}`} title="Event analysis" description={item.headline} action={<Button variant="secondary">Save analysis</Button>} />
      <DemoNotice>Every event attribute on this screen is illustrative. No model has analyzed this headline; the prediction and confidence remain unavailable.</DemoNotice>
      <Panel className="mb-5"><PanelHeading title="Source headline" detail={`Illustrative item · ${item.company}`} action={<StatusBadge tone="amber">Demo content</StatusBadge>} /><div className="p-5"><p className="max-w-4xl text-base font-medium leading-7 text-[#e1e6eb]">{item.headline}</p><p className="mt-3 text-xs text-[#89939f]">Publication time shown for interface demonstration · {item.time}</p></div></Panel>
      <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Company" value={item.ticker} note={item.company} />
        <StatCard label="Event type" value={item.eventType} note="Illustrative classification" />
        <div className="rounded-xl border border-[#252d36] bg-[#10151b] p-4"><p className="text-xs text-[#89939f]">Sentiment / direction</p><div className="mt-4"><SentimentBadge sentiment={item.sentiment} /></div><p className="mt-2 text-[10px] text-[#74808c]">Demo label · not FinBERT output</p></div>
        <StatCard label="Severity" value={item.severity} note="Illustrative severity label" icon="spark" />
      </div>
      <div className="grid gap-5 xl:grid-cols-[1.3fr_0.7fr]">
        <div className="space-y-5">
          <Panel><PanelHeading title="Information profile" detail="Novelty and surprise availability" /><div className="grid gap-4 p-5 sm:grid-cols-2"><div><p className="text-[10px] uppercase tracking-wider text-[#7d8995]">Novelty</p><p className="mt-2 text-sm font-medium text-[#e1e6eb]">{item.novelty} <span className="text-[10px] text-[#77828e]">(demo label)</span></p><p className="mt-2 text-xs text-[#89939f]">No historical similarity analysis has run.</p></div><div><p className="text-[10px] uppercase tracking-wider text-[#7d8995]">Information surprise</p><p className="mt-2 text-sm font-medium text-[#89939f]">Not available yet</p><p className="mt-2 text-xs text-[#89939f]">Requires real expectation and outcome data.</p></div></div></Panel>
          <Panel><PanelHeading title="Market context" detail="Features at the event timestamp" /><EmptyState title="Market features unavailable" description="Price trend, volatility, and regime context will be populated when historical market data is connected." /></Panel>
          <Panel><PanelHeading title="Analysis explanation" detail="Decision rationale" /><EmptyState title="No analysis has been generated" description="FinSight has not evaluated this illustrative headline. No explanation or confidence is available." /></Panel>
        </div>
        <div className="space-y-5">
          <Panel><PanelHeading title="Reaction prediction" detail="Requested horizon: 1d" /><EmptyState title="Reaction model unavailable" description="No trained and evaluated model artifact is available for this horizon." /></Panel>
          <Panel><PanelHeading title="Decision" detail="Trade · Watch · Abstain" /><div className="p-5"><StatusBadge tone="amber">Not available yet</StatusBadge><p className="mt-3 text-xs leading-5 text-[#89939f]">FinSight will show a decision only when an eligible model and compatible inputs are available.</p><p className="mt-4 border-t border-[#252d36] pt-4 text-[10px] text-[#6f7b87]">Confidence: unavailable</p></div></Panel>
          <Panel><PanelHeading title="Related event record" detail={item.id} /><div className="p-3"><EventCard item={item} /></div></Panel>
        </div>
      </div>
    </>
  );
}
