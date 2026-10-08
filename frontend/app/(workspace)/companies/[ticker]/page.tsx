import Link from "next/link";
import { MarketReactionChart, SentimentTrendChart } from "@/components/charts";
import { DemoNotice, EventCard, NewsCard } from "@/components/cards";
import { Button, EmptyState, PageHeader, Panel, PanelHeading, SentimentBadge, StatCard, StatusBadge } from "@/components/ui";
import { demoCompanies, demoNews } from "@/lib/demo-data";

export default async function CompanyDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;
  const company = demoCompanies.find((entry) => entry.ticker.toLowerCase() === ticker.toLowerCase());
  const name = company?.name ?? `${ticker.toUpperCase()} coverage`;
  const relevantNews = demoNews.filter((item) => item.ticker.toLowerCase() === ticker.toLowerCase());
  return (
    <>
      <div className="mb-5 text-[11px] text-[#75808c]"><Link href="/companies" className="hover:text-white">Companies</Link><span className="px-2">/</span>{ticker.toUpperCase()}</div>
      <PageHeader eyebrow={`${company?.sector ?? "Company"} · ${ticker.toUpperCase()}`} title={name} description="Company intelligence, market context, and event history." action={<><Button variant="secondary"><span aria-hidden>＋</span> Add to watchlist</Button><Button variant="ghost">•••</Button></>} />
      <DemoNotice>Company information and sentiment labels below are illustrative UI content. Market data and model analysis are not connected.</DemoNotice>
      <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Last price" value="Unavailable" note="Market data not connected" />
        <StatCard label="Daily change" value="—" note="No current quote" />
        <StatCard label="News sentiment" value={company?.sentiment ?? "—"} note="Illustrative placeholder" icon="spark" />
        <StatCard label="Market regime" value="Unavailable" note="Requires historical data" icon="pulse" />
      </div>
      <div className="grid gap-5 xl:grid-cols-[1.4fr_0.8fr]">
        <div className="space-y-5"><MarketReactionChart /><SentimentTrendChart /></div>
        <div className="space-y-5">
          <Panel><PanelHeading title="Market condition" detail="Feature summary" /><EmptyState title="Context unavailable" description="Trend, volatility, and regime context will appear when market data is connected." /></Panel>
          <Panel><PanelHeading title="Reaction analysis" detail="Prediction status" /><EmptyState title="Reaction model unavailable" description="No prediction or confidence estimate is available for this company." /></Panel>
          <Panel><PanelHeading title="Recent events" detail="Illustrative event records" />{relevantNews.length ? relevantNews.map((item) => <div className="p-3" key={item.id}><EventCard item={item} /></div>) : <EmptyState title="No demo events" description="No illustrative event record is configured for this ticker." />}</Panel>
        </div>
      </div>
      <Panel className="mt-5"><PanelHeading title="News timeline" detail="Illustrative headlines only" action={<SentimentBadge sentiment={company?.sentiment ?? "Neutral"} />} />{relevantNews.length ? relevantNews.map((item) => <NewsCard item={item} key={item.id} />) : <EmptyState title="No timeline items" description="News items will appear here once a feed is connected." />}</Panel>
      <div className="mt-4 flex items-center gap-2 text-[10px] text-[#77828e]"><StatusBadge tone="amber">Demo state</StatusBadge><span>Do not interpret as an investment signal.</span></div>
    </>
  );
}
