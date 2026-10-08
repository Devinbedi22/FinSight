import Link from "next/link";
import { MarketReactionChart, SentimentTrendChart } from "@/components/charts";
import { DemoNotice, NewsCard, PredictionCard } from "@/components/cards";
import { Button, EmptyState, PageHeader, Panel, PanelHeading, StatCard, StatusBadge } from "@/components/ui";
import { demoNews } from "@/lib/demo-data";

export default function DashboardPage() {
  return (
    <>
      <PageHeader
        eyebrow="Monday, October 12 · Market session"
        title="Market Intelligence"
        description="A concise view of financial news, event activity, and analysis readiness."
        action={<div className="flex items-center gap-2"><StatusBadge tone="amber">Market data unavailable</StatusBadge><Button variant="secondary">Last 7 days</Button></div>}
      />
      <DemoNotice />

      <section aria-label="Market summary" className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Market regime" value="Unavailable" note="Requires market history" icon="pulse" />
        <StatCard label="News events" value="—" note="No backend analysis available" icon="news" />
        <StatCard label="Bullish signals" value="—" note="Reaction model unavailable" icon="arrow" />
        <StatCard label="High-impact events" value="—" note="Severity analysis unavailable" icon="spark" />
      </section>

      <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.7fr)_minmax(310px,0.9fr)]">
        <div className="space-y-5">
          <MarketReactionChart />
          <Panel>
            <PanelHeading title="Recent news & events" detail="Illustrative headlines · not connected to a live feed" action={<Link href="/news" className="text-[11px] font-medium text-[#aabaff] hover:text-white">View feed →</Link>} />
            {demoNews.slice(0, 3).map((item) => <NewsCard key={item.id} item={item} />)}
          </Panel>
        </div>
        <div className="space-y-5">
          <Panel>
            <PanelHeading title="Latest predictions" detail="No model results are being presented" />
            <div className="space-y-3 p-4">
              <EmptyState title="Reaction model unavailable" description="Predictions will appear after a genuine, evaluated reaction model is available." />
              <div className="grid grid-cols-3 gap-2">
                <PredictionCard decision="TRADE" ticker="—" title="No prediction" detail="Demo state only" />
                <PredictionCard decision="WATCH" ticker="—" title="No prediction" detail="Demo state only" />
                <PredictionCard decision="ABSTAIN" ticker="—" title="No prediction" detail="Demo state only" />
              </div>
            </div>
          </Panel>
          <SentimentTrendChart />
          <Panel>
            <PanelHeading title="Watchlist snapshot" detail="No saved companies yet" action={<Link href="/watchlist" className="text-[11px] text-[#aabaff] hover:text-white">Open watchlist →</Link>} />
            <EmptyState title="Your watchlist is clear" description="Add companies to keep their news and analysis close at hand." action={<Link href="/watchlist" className="text-xs font-semibold text-[#afc0ff]">Explore companies</Link>} />
          </Panel>
        </div>
      </div>
    </>
  );
}
