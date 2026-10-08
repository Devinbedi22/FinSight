"use client";

import { useState } from "react";
import { DrawdownChart, EquityCurveChart, RegimeDistributionChart } from "@/components/charts";
import { DemoNotice } from "@/components/cards";
import { Button, EmptyState, FilterSelect, PageHeader, Panel, PanelHeading, StatCard, StatusBadge } from "@/components/ui";

const horizons = ["30m", "1h", "4h", "1d", "3d", "5d"];

export default function BacktestingPage() {
  const [horizon, setHorizon] = useState("1d");
  return (
    <>
      <PageHeader eyebrow="Strategy research" title="Backtesting" description="Replay historical event decisions chronologically and compare against a sentiment-only baseline." action={<StatusBadge tone="amber">No run results</StatusBadge>} />
      <DemoNotice>Charts below are explicitly illustrative UI previews, not computed backtest results. No metrics or performance numbers are shown.</DemoNotice>
      <div className="grid gap-5 xl:grid-cols-[300px_minmax(0,1fr)]">
        <Panel className="h-fit">
          <PanelHeading title="Strategy configuration" detail="UI controls only · no run is submitted" />
          <div className="space-y-5 p-4">
            <label className="block"><span className="mb-2 block text-[11px] font-medium text-[#aeb8c2]">Company universe</span><FilterSelect label="Select companies" options={["Watchlist", "Large-cap universe", "All covered"]} /></label>
            <div><span className="mb-2 block text-[11px] font-medium text-[#aeb8c2]">Prediction horizon</span><div className="grid grid-cols-3 gap-1.5">{horizons.map((item) => <button onClick={() => setHorizon(item)} key={item} aria-pressed={horizon === item} className={`rounded-md border px-2 py-2 text-[11px] font-medium transition-colors ${horizon === item ? "border-[#748bc8] bg-[#222d42] text-[#dbe4ff]" : "border-[#29323c] bg-[#11171d] text-[#8b96a2] hover:text-white"}`}>{item}</button>)}</div></div>
            <label className="block"><span className="mb-2 block text-[11px] font-medium text-[#aeb8c2]">Date range</span><div className="grid grid-cols-2 gap-2"><input aria-label="Start date" type="date" className="min-w-0 rounded-md border border-[#29323c] bg-[#0c1116] px-2 py-2 text-[10px] text-[#aab4be]" /><input aria-label="End date" type="date" className="min-w-0 rounded-md border border-[#29323c] bg-[#0c1116] px-2 py-2 text-[10px] text-[#aab4be]" /></div></label>
            <FilterSelect label="Baseline" options={["Sentiment-only", "Buy and hold"]} />
            <div className="border-t border-[#252d36] pt-4"><p className="text-[10px] leading-5 text-[#7c8793]">Replay mode enforces chronological processing and excludes future information. Transaction timing and assumptions will be specified when the engine is implemented.</p></div>
            <Button className="w-full" disabled title="Backtesting service is not implemented"><span aria-hidden>▶</span> Run backtest · {horizon}</Button>
            <p className="text-center text-[10px] text-[#71808c]">Backend execution is not connected.</p>
          </div>
        </Panel>
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{["CAGR", "Cumulative return", "Max drawdown", "Win rate", "Sharpe ratio", "Abstention rate"].map((metric) => <StatCard key={metric} label={metric} value="—" note="No backtest has been run" />)}</div>
          <Panel><PanelHeading title="Backtest results" detail="No persisted runs" /><EmptyState title="Run a backtest to see results." description="Configure a strategy and date range. Results will include the strategy, a sentiment-only baseline, and risk metrics." /></Panel>
        </div>
      </div>
      <div className="mt-5 grid gap-5 xl:grid-cols-2"><EquityCurveChart /><DrawdownChart /></div>
      <div className="mt-5"><RegimeDistributionChart /></div>
    </>
  );
}
