"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { GlobalCompanySearch } from "@/components/global-search";
import { Icon } from "@/components/ui";

const navigation = [
  { label: "Markets", items: [
    { label: "Overview", href: "/dashboard", icon: "grid" },
    { label: "News", href: "/news", icon: "news" },
    { label: "Companies", href: "/companies", icon: "building" },
    { label: "Compare", href: "/compare", icon: "compare" },
  ] },
  { label: "Intelligence", items: [
    { label: "Research assistant", href: "/research", icon: "spark" },
    { label: "Events", href: "/events", icon: "calendar" },
    { label: "Predictions", href: "/predictions", icon: "pulse" },
  ] },
  { label: "Workspace", items: [
    { label: "Watchlist", href: "/watchlist", icon: "bookmark" },
    { label: "Backtesting", href: "/backtesting", icon: "chart" },
  ] },
];

const pageNames: Record<string, string> = {
  dashboard: "Market overview", news: "Financial news", predictions: "Predictions",
  companies: "Companies", compare: "Compare companies", research: "Research assistant",
  events: "Events", watchlist: "Watchlist", backtesting: "Backtesting",
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const section = pathname.split("/").filter(Boolean)[0] ?? "dashboard";
  const title = section === "companies" && pathname.split("/").filter(Boolean).length > 1
    ? "Company research"
    : pageNames[section] ?? "Analysis";

  useEffect(() => {
    if (!mobileOpen) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") setMobileOpen(false); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  return <div className="min-h-screen bg-canvas text-text">
    {mobileOpen && <button className="fixed inset-0 z-30 cursor-default bg-canvas/75 backdrop-blur-[2px] lg:hidden" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
    <aside className={`fixed inset-y-0 left-0 z-40 flex flex-col border-r border-line-soft bg-sidebar/95 shadow-[14px_0_48px_rgba(18,14,35,0.16)] backdrop-blur-xl transition-[width,transform] duration-200 ${collapsed ? "w-[78px]" : "w-[272px]"} ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`} aria-label="FinSight workspace navigation">
      <div className={`flex h-[76px] shrink-0 items-center border-b border-line-soft ${collapsed ? "justify-center px-2" : "justify-between px-5"}`}>
        <Link href="/dashboard" onClick={() => setMobileOpen(false)} className="group flex min-w-0 items-center gap-3" aria-label="FinSight market overview">
          <span className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-[14px] border border-accent/40 bg-gradient-to-br from-accent/25 to-panel-raised text-sm font-bold tracking-tight text-accent-strong shadow-inner shadow-accent/10"><span>F</span><span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-sidebar bg-positive" /></span>
          {!collapsed && <span className="min-w-0"><span className="block text-[17px] font-semibold tracking-[-0.045em] text-text">FinSight</span><span className="mt-0.5 block text-[9px] font-medium uppercase tracking-[0.18em] text-subtle">Market intelligence</span></span>}
        </Link>
        {!collapsed && <span className="hidden rounded-full border border-line bg-panel/70 px-2 py-1 text-[9px] font-semibold uppercase tracking-[0.12em] text-muted sm:inline-flex">Beta</span>}
      </div>

      <nav aria-label="Main navigation" className="min-h-0 flex-1 space-y-6 overflow-y-auto px-3 py-5">
        {navigation.map((group) => <div key={group.label}>
          {!collapsed && <p className="mb-2 px-3 text-[9px] font-semibold uppercase tracking-[0.17em] text-subtle">{group.label}</p>}
          <div className="space-y-1">
            {group.items.map((item) => {
              const active = item.href === "/dashboard" ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
              return <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                aria-label={item.label}
                title={collapsed ? item.label : undefined}
                onClick={() => setMobileOpen(false)}
                className={`group relative flex min-h-11 items-center gap-3 rounded-xl px-3 text-[12px] transition-[background,color,transform] duration-150 hover:translate-x-[1px] ${active ? "bg-accent/14 font-semibold text-accent-strong shadow-inner shadow-accent/5" : "text-muted hover:bg-panel/80 hover:text-text"} ${collapsed ? "justify-center px-0" : ""}`}
              >
                {active && <span className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-accent" />}
                <Icon name={item.icon} size={18} />
                {!collapsed && <span className="truncate">{item.label}</span>}
                {active && !collapsed && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-accent" />}
              </Link>;
            })}
          </div>
        </div>)}
      </nav>

      <div className="shrink-0 border-t border-line-soft px-3 py-3">
        <div className={`rounded-xl border border-line-soft bg-panel/55 p-3 ${collapsed ? "hidden" : "mb-2 block"}`}>
          <div className="flex items-center gap-2"><span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent/12 text-accent-strong"><Icon name="layers" size={14} /></span><span className="text-[10px] font-semibold text-text-soft">Data sources</span></div>
          <p className="mt-2 text-[9px] leading-4 text-subtle">Yahoo Finance · SEC EDGAR · stored news</p>
        </div>
        <div className={`flex items-center gap-2 ${collapsed ? "justify-center" : "justify-between"}`}>
          {!collapsed && <p className="px-2 text-[9px] text-subtle">FinSight research workspace</p>}
          <button onClick={() => setCollapsed((value) => !value)} className="hidden h-9 w-9 items-center justify-center rounded-lg text-muted transition-colors hover:bg-panel-raised hover:text-text focus-ring lg:flex" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed}>
            <span className={`transition-transform ${collapsed ? "rotate-180" : ""}`}><Icon name="chevron" size={16} /></span>
          </button>
        </div>
      </div>
    </aside>

    <div className={`min-h-screen transition-[margin] duration-200 ${collapsed ? "lg:ml-[78px]" : "lg:ml-[272px]"}`}>
      <header className="sticky top-0 z-20 border-b border-line-soft bg-canvas/90 shadow-[0_8px_28px_rgba(16,12,31,0.12)] backdrop-blur-xl">
        <div className="mx-auto flex min-h-[74px] max-w-[1760px] items-center gap-3 px-4 sm:gap-5 sm:px-7 lg:px-9">
          <button onClick={() => setMobileOpen(true)} aria-label="Open navigation" aria-expanded={mobileOpen} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-line-soft bg-panel/70 text-muted transition-colors hover:bg-panel-raised hover:text-text focus-ring lg:hidden"><Icon name="menu" /></button>
          <div className="hidden min-w-0 shrink-0 items-center gap-2 text-[11px] text-subtle md:flex"><span className="text-muted">Workspace</span><Icon name="chevron" size={13} /><span className="truncate font-medium text-text-soft">{title}</span></div>
          <div className="min-w-0 flex-1 md:ml-auto md:flex md:justify-end"><GlobalCompanySearch /></div>
          <div className="hidden shrink-0 items-center gap-2 rounded-xl border border-line-soft bg-panel/55 px-3 py-2.5 text-[10px] text-muted xl:flex"><span className="h-1.5 w-1.5 rounded-full bg-positive shadow-[0_0_10px_rgba(119,201,178,0.4)]" /><span>U.S. equities</span><span className="text-line">/</span><span>Data varies by source</span></div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1760px] px-4 pb-8 pt-6 sm:px-7 sm:pt-8 lg:px-9 lg:pt-9">{children}</main>
      <footer className="mx-4 flex flex-wrap items-center justify-between gap-x-5 gap-y-2 border-t border-line-soft/80 py-4 text-[10px] text-subtle sm:mx-7 lg:mx-9">
        <span>FinSight · Evidence-led market research</span><span>Observations only · Not investment advice</span>
      </footer>
    </div>
  </div>;
}
