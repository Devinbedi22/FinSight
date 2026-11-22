"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { EmptyState, PageHeader, Panel, PanelHeading, SearchInput, StatusBadge } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
type EventItem = {
  event_type: string;
  related_companies: Array<{ ticker: string; name?: string }>;
  supporting_article_id: number;
  title: string;
  source: string;
  source_url: string;
  published_at: string | null;
  extraction_method: string;
  supporting_evidence: string;
  classification_status: string;
  novelty_status: string;
};
type EventResponse = { count: number; events: EventItem[]; methodology_note: string };

export default function EventsPage() {
  const [data, setData] = useState<EventResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetch(`${API}/events?limit=200`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail ?? `Events returned ${response.status}`);
        return payload as EventResponse;
      })
      .then(setData)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Stored event signals are unavailable.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [retry]);

  const events = (data?.events ?? []).filter((event) =>
    `${event.event_type} ${event.title} ${event.source} ${event.related_companies.map((company) => `${company.name ?? ""} ${company.ticker}`).join(" ")}`
      .toLowerCase().includes(query.trim().toLowerCase()),
  );

  return <>
    <PageHeader eyebrow="Financial news intelligence" title="Events" description="Review explainable event signals extracted from persisted financial-news headlines." action={<StatusBadge tone={error ? "red" : loading ? "muted" : "blue"}>{error ? "Unavailable" : loading ? "Loading" : `${data?.count ?? 0} signals`}</StatusBadge>} />
    <div className="mb-4 rounded-xl border border-warning/30 bg-warning/10 p-4 text-xs leading-5 text-warning">
      Headline-pattern classifications are heuristic signals, not human-verified events. Novelty scoring and a dedicated event model are unavailable. The original article, source, publication time, and matching pattern are shown for review.
    </div>
    <Panel className="overflow-hidden">
      <PanelHeading title="Stored event signals" detail={data?.methodology_note ?? "Signals are generated from persisted headlines and retain article source attribution."} />
      <div className="border-b border-line-soft p-4"><SearchInput ariaLabel="Filter stored events" placeholder="Filter by event, company, ticker, or source" value={query} onChange={setQuery} className="w-full sm:max-w-lg" /></div>
      {error ? <EmptyState title="Event signals unavailable" description={error} action={<button type="button" onClick={() => setRetry((value) => value + 1)} className="min-h-11 rounded-lg border border-line px-4 py-2 text-xs font-semibold text-text hover:bg-panel-raised">Retry</button>} />
        : loading && !data ? <div role="status" className="space-y-3 p-5"><span className="sr-only">Loading event signals</span><div className="skeleton h-4 w-1/3 rounded" /><div className="skeleton h-12 rounded" /><div className="skeleton h-12 rounded" /></div>
          : events.length === 0 ? <EmptyState title={query ? "No matching event signals" : "No classified headlines available"} description={query ? "Try a different company, ticker, source, or event term." : "No stored headlines currently contain a supported event pattern. This does not mean no financial events occurred."} action={<Link href="/news" className="inline-flex min-h-11 items-center rounded-lg border border-line bg-panel-raised px-4 py-2 text-xs font-semibold text-text">Open news archive</Link>} />
            : <ul className="divide-y divide-line-soft">{events.map((event, index) => <li key={`${event.supporting_article_id}-${event.event_type}-${index}`} className="p-4 sm:p-5">
              <div className="flex flex-wrap items-center gap-2"><StatusBadge tone="blue">{event.event_type.replaceAll("_", " ")}</StatusBadge><StatusBadge tone="amber">Heuristic</StatusBadge><time className="text-[10px] text-subtle" dateTime={event.published_at ?? undefined}>{event.published_at ? new Date(event.published_at).toLocaleString() : "Publication time unavailable"}</time></div>
              <a href={event.source_url} target="_blank" rel="noreferrer" className="mt-3 block text-sm font-semibold leading-6 text-text underline decoration-transparent underline-offset-4 hover:text-accent-strong hover:decoration-accent-strong">{event.title}</a>
              <p className="mt-1 text-[10px] text-muted">{event.source} · Pattern: {event.extraction_method} · Novelty unavailable</p>
              {event.related_companies.length > 0 && <div className="mt-3 flex flex-wrap gap-2">{event.related_companies.map((company) => <Link key={company.ticker} href={`/companies/${encodeURIComponent(company.ticker)}`} className="inline-flex min-h-9 items-center rounded-md border border-line px-2.5 text-[10px] font-semibold text-accent-strong hover:bg-panel-raised">{company.name ?? company.ticker} · {company.ticker}</Link>)}</div>}
              <p className="mt-3 border-l-2 border-line pl-3 text-xs leading-5 text-muted">Matched headline evidence: “{event.supporting_evidence}”</p>
            </li>)}</ul>}
    </Panel>
  </>;
}
