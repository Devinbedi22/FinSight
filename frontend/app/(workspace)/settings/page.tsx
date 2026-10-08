"use client";

import { useState } from "react";
import { DemoNotice } from "@/components/cards";
import { Button, PageHeader, Panel, PanelHeading, StatusBadge } from "@/components/ui";

function PreferenceRow({
  title,
  detail,
  defaultChecked = false,
}: {
  title: string;
  detail: string;
  defaultChecked?: boolean;
}) {
  const [checked, setChecked] = useState(defaultChecked);
  return <div className="flex items-center justify-between gap-4 border-b border-[#222a32] py-4 last:border-0"><div><p className="text-xs font-medium text-[#dce2e8]">{title}</p><p className="mt-1 text-[10px] leading-4 text-[#89939f]">{detail}</p></div><button type="button" role="switch" aria-checked={checked} aria-label={title} onClick={() => setChecked(!checked)} className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${checked ? "bg-[#8199d7]" : "bg-[#343d47]"}`}><span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${checked ? "translate-x-[18px]" : "translate-x-0.5"}`} /></button></div>;
}

export default function SettingsPage() {
  return (
    <>
      <PageHeader eyebrow="Workspace configuration" title="Settings" description="Manage interface and analysis preferences." action={<StatusBadge>Demo preferences</StatusBadge>} />
      <DemoNotice>Preference controls are local UI state only; there is no account or settings persistence.</DemoNotice>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Panel><PanelHeading title="Appearance" detail="Personalize your workspace" /><div className="p-5"><PreferenceRow title="Dark appearance" detail="Use the FinSight dark-first color theme." defaultChecked /><PreferenceRow title="Compact data density" detail="Show more rows and signals per screen." /><div className="mt-5"><span className="mb-2 block text-[11px] font-medium text-[#aeb8c2]">Default landing page</span><select className="w-full rounded-md border border-[#29323c] bg-[#0c1116] px-3 py-2.5 text-xs text-[#c4ccd4]"><option>Overview</option><option>News</option><option>Watchlist</option></select></div></div></Panel>
        <Panel><PanelHeading title="Notifications" detail="UI preview; no notifications are sent" /><div className="p-5"><PreferenceRow title="High-impact event alerts" detail="Show alerts for events marked high impact." /><PreferenceRow title="Watchlist activity" detail="Highlight new illustrative activity in your watchlist." /><PreferenceRow title="Daily summary" detail="Receive a daily digest of analysis activity." /></div></Panel>
        <Panel><PanelHeading title="Analysis preferences" detail="Default display settings" /><div className="p-5"><div className="mb-5"><span className="mb-2 block text-[11px] font-medium text-[#aeb8c2]">Preferred prediction horizon</span><select className="w-full rounded-md border border-[#29323c] bg-[#0c1116] px-3 py-2.5 text-xs text-[#c4ccd4]"><option>1d</option><option>30m</option><option>1h</option><option>4h</option><option>3d</option><option>5d</option></select></div><PreferenceRow title="Show abstentions" detail="Keep abstained analysis visible in lists." defaultChecked /><PreferenceRow title="Display demo labels" detail="Mark illustrative content as demo data." defaultChecked /></div></Panel>
        <Panel><PanelHeading title="Account" detail="Authentication is not implemented" /><div className="p-5"><div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-full bg-[#202a36] text-xs font-bold text-[#c3d2f4]">FS</span><div><p className="text-xs font-semibold text-[#dce2e8]">Demo analyst</p><p className="mt-1 text-[10px] text-[#89939f]">No account connected</p></div></div><Button variant="secondary" className="mt-5" disabled>Manage account</Button></div></Panel>
      </div>
      <div className="mt-5 flex justify-end"><Button variant="secondary" disabled>Save preferences</Button></div>
    </>
  );
}
