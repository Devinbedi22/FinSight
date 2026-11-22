import Link from "next/link";
import type { DemoNewsItem, Decision } from "@/lib/demo-data";
import { DecisionBadge, Icon, SentimentBadge, StatusBadge } from "@/components/ui";

export function NewsCard({ item }: { item: DemoNewsItem }) {
  const severityTone = item.severity === "High" ? "red" : item.severity === "Medium" ? "amber" : "muted";
  return (
    <article className="group border-b border-[var(--line-soft)] px-5 py-4 last:border-0">
      <div className="flex flex-wrap items-center gap-2">
        <Link href={`/companies/${item.ticker}`} className="text-[11px] font-bold tracking-wide text-[var(--accent-strong)] hover:text-white">{item.ticker}</Link>
        <span className="text-[10px] text-[var(--subtle)]">{item.company}</span>
        <span className="ml-auto flex items-center gap-1 text-[10px] text-[var(--subtle)]"><Icon name="clock" size={12} />{item.time}</span>
      </div>
      <Link href={`/events/${item.id}`} className="mt-2 block text-[13px] font-medium leading-5 text-[var(--text)] transition-colors group-hover:text-white">{item.headline}</Link>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <SentimentBadge sentiment={item.sentiment} />
        <StatusBadge tone={severityTone}>{item.severity} impact</StatusBadge>
        <span className="rounded-md border border-[var(--line)] px-2 py-1 text-[10px] text-[var(--subtle)]">{item.eventType}</span>
        <span className="ml-auto text-[10px] text-[var(--subtle)]">Novelty: {item.novelty}</span>
      </div>
      <div className="mt-3 flex items-center gap-1.5 text-[10px] text-[var(--subtle)]"><Icon name="pulse" size={13} />Reaction model unavailable</div>
    </article>
  );
}

export function EventCard({ item }: { item: DemoNewsItem }) {
  const tone = item.severity === "High" ? "red" : "amber";
  return (
    <Link href={`/events/${item.id}`} className="block rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] p-4 transition-colors hover:border-[var(--line)] hover:bg-[var(--panel-raised)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0"><p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--subtle)]">{item.ticker} <span className="px-1 text-[var(--line)]">/</span> {item.eventType}</p><h3 className="mt-2 text-[13px] font-medium leading-5 text-[var(--text)]">{item.headline}</h3></div>
        <StatusBadge tone={tone}>{item.severity}</StatusBadge>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[var(--line-soft)] pt-3">
        <SentimentBadge sentiment={item.sentiment} />
        <span className="text-[10px] text-[var(--subtle)]">Novelty {item.novelty}</span>
        <span className="ml-auto text-[10px] text-[var(--subtle)]">Market context unavailable</span>
      </div>
    </Link>
  );
}

export function CompanyCard({
  ticker,
  name,
  sector,
  sentiment,
  events,
  regime,
}: {
  ticker: string;
  name: string;
  sector: string;
  sentiment: "Positive" | "Negative" | "Neutral";
  events: number;
  regime: string;
}) {
  return (
    <Link href={`/companies/${ticker}`} className="block rounded-xl border border-[var(--line-soft)] bg-[var(--panel)] p-4 transition-colors hover:border-[var(--line)] hover:bg-[var(--panel-raised)]">
      <div className="flex items-start justify-between">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--panel-raised)] text-[10px] font-bold tracking-wide text-[var(--accent-strong)]">{ticker.slice(0, 2)}</span>
        <Icon name="arrow" size={15} />
      </div>
      <p className="mt-4 text-sm font-semibold text-[var(--text)]">{ticker}</p>
      <p className="mt-1 truncate text-xs text-[var(--muted)]">{name}</p>
      <div className="mt-4 flex items-center justify-between border-t border-[var(--line-soft)] pt-3 text-[10px] text-[var(--subtle)]"><span>{sector}</span><span>{events} events</span></div>
      <div className="mt-3 flex flex-wrap items-center gap-2"><SentimentBadge sentiment={sentiment} /><span className="text-[10px] text-[var(--subtle)]">Regime {regime}</span></div>
      <p className="mt-3 text-[10px] text-warning/80">Demo directory · analysis unavailable</p>
    </Link>
  );
}

export function PredictionCard({
  decision,
  title,
  ticker,
  detail,
}: {
  decision: Decision;
  title: string;
  ticker: string;
  detail: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] p-4">
      <div className="flex items-center justify-between gap-2"><DecisionBadge decision={decision} /><span className="text-[10px] font-semibold text-[var(--accent-strong)]">{ticker}</span></div>
      <p className="mt-3 text-xs font-medium leading-5 text-[var(--text)]">{title}</p>
      <p className="mt-1 text-[10px] leading-4 text-[var(--muted)]">{detail}</p>
      <div className="mt-3 border-t border-[var(--line-soft)] pt-3 text-[10px] text-warning/80">Reaction model unavailable</div>
    </div>
  );
}

export function DemoNotice({ children = "Demo interface · values shown are illustrative and are not generated by the FinSight model." }: { children?: string }) {
  return <div className="mb-5 flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3.5 py-3 text-[11px] leading-5 text-warning/80"><span className="mt-0.5"><Icon name="spark" size={14} /></span><p>{children}</p></div>;
}
