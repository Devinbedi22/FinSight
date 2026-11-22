import Link from "next/link";
import { EmptyState, PageHeader, Panel, PanelHeading, StatusBadge } from "@/components/ui";

export default async function EventDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <>
    <PageHeader eyebrow="Financial news intelligence" title="Event detail" description={`No event record exists for ${id}.`} action={<StatusBadge tone="amber">Not available</StatusBadge>} />
    <Panel>
      <PanelHeading title="Stored headline signals" detail="Persisted rule-based event classifications are available on the Events page." />
      <EmptyState title="No event record to show" description="FinSight exposes heuristic signals from stored headline patterns, with source attribution. Novelty scoring and human-verified event analysis are not available." action={<Link href="/events" className="inline-flex min-h-11 items-center rounded-lg border border-[var(--line)] bg-[var(--panel-raised)] px-4 py-2.5 text-xs font-semibold text-[var(--text)] hover:bg-[var(--panel-raised)]">Open event signals</Link>} />
    </Panel>
  </>;
}
