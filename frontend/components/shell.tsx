"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Icon } from "@/components/ui";

const primaryNav = [
  { label: "News", href: "/news", icon: "news" },
  { label: "Predictions", href: "/predictions", icon: "pulse" },
  { label: "Companies", href: "/companies", icon: "building" },
  { label: "Backtesting", href: "/backtesting", icon: "pulse" },
];

const pageNames: Record<string, string> = {
  dashboard: "News",
  news: "News",
  predictions: "Predictions",
  companies: "Companies",
  backtesting: "Backtesting",
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const section = pathname.split("/").filter(Boolean)[0] ?? "dashboard";
  const title = pageNames[section] ?? "Analysis";

  return (
    <div className="min-h-screen bg-[#090c10]">
      {mobileOpen && <button className="fixed inset-0 z-30 bg-black/60 lg:hidden" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
      <aside className={`fixed inset-y-0 left-0 z-40 flex flex-col border-r border-[#222a32] bg-[#0d1116] transition-all duration-200 ${collapsed ? "w-[76px]" : "w-[248px]"} ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>
        <div className={`flex h-[68px] items-center border-b border-[#222a32] ${collapsed ? "justify-center px-2" : "justify-between px-5"}`}>
          <Link href="/news" className="flex items-center gap-3" aria-label="FinSight news">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[#a9bcff] text-xs font-black text-[#111827]">F</span>
            {!collapsed && <span className="text-[15px] font-semibold tracking-tight text-white">FinSight<span className="ml-1 text-[#8c98a6]">/</span></span>}
          </Link>
          {!collapsed && <span className="hidden rounded border border-[#29323c] px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-[#788390] sm:inline">Beta</span>}
        </div>

        <div className="px-3 pt-5">
          {!collapsed && <p className="mb-2 px-3 text-[9px] font-semibold uppercase tracking-[0.16em] text-[#65717d]">Workspace</p>}
          <nav aria-label="Main navigation" className="space-y-1">
            {primaryNav.map((item) => {
              const active = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(`${item.href}/`));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  title={collapsed ? item.label : undefined}
                  onClick={() => setMobileOpen(false)}
                  className={`group flex h-10 items-center gap-3 rounded-md px-3 text-xs transition-colors ${active ? "bg-[#1a222c] font-semibold text-[#dbe4ff]" : "text-[#929ca7] hover:bg-[#151b22] hover:text-[#e4e9ef]"} ${collapsed ? "justify-center px-0" : ""}`}
                >
                  <Icon name={item.icon} size={17} />
                  {!collapsed && <span>{item.label}</span>}
                  {active && !collapsed && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[#a9bcff]" />}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="mt-auto border-t border-[#222a32] px-3 py-4">
          <button onClick={() => setCollapsed(!collapsed)} className="mt-2 hidden h-9 w-full items-center justify-center rounded-md text-[#697581] transition-colors hover:bg-[#151b22] hover:text-white lg:flex" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
            <span className={`transition-transform ${collapsed ? "rotate-180" : ""}`}><Icon name="chevron" size={16} /></span>
          </button>
          <div className={`mt-3 flex items-center gap-3 rounded-md border border-[#232b34] bg-[#11171e] p-2.5 ${collapsed ? "justify-center" : ""}`}>
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#293444] text-[10px] font-semibold text-[#c1d0ef]">FS</span>
            {!collapsed && <div className="min-w-0"><p className="truncate text-[11px] font-semibold text-[#d5dce4]">Market research</p><p className="mt-0.5 text-[10px] text-[#74808c]">S&P 500 · Model v2</p></div>}
          </div>
        </div>
      </aside>

      <div className={`min-h-screen transition-[margin] duration-200 ${collapsed ? "lg:ml-[76px]" : "lg:ml-[248px]"}`}>
        <header className="sticky top-0 z-20 flex h-[68px] items-center justify-between gap-4 border-b border-[#222a32] bg-[#090c10]/95 px-4 backdrop-blur-sm sm:px-7">
          <div className="flex min-w-0 items-center gap-3">
            <button onClick={() => setMobileOpen(true)} aria-label="Open navigation" className="rounded-md p-2 text-[#929ca7] hover:bg-[#171d24] lg:hidden"><Icon name="menu" /></button>
            <div className="hidden items-center gap-2 text-xs text-[#707b87] sm:flex">
              <span>FinSight</span><Icon name="chevron" size={13} /><span className="font-medium text-[#cbd3dc]">{title}</span>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-[#29323c] bg-[#11171e] px-3 py-1.5 text-[10px] text-[#9ba8b6]"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />U.S. equities · S&P 500</div>
        </header>
        <main className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-7 sm:py-8">{children}</main>
        <footer className="mx-4 flex flex-wrap items-center justify-between gap-2 border-t border-[#202830] py-4 text-[10px] text-[#64707c] sm:mx-7">
          <span>FinSight · News-driven price research</span><span>Experimental forecasts · Not investment advice</span>
        </footer>
      </div>
    </div>
  );
}
