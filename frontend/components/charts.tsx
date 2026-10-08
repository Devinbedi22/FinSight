"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { demoDrawdown, demoEquity, demoMarketLine, demoRegimes, demoTrend } from "@/lib/demo-data";
import { Panel, PanelHeading, StatusBadge } from "@/components/ui";

const axisStyle = { fill: "#7d8995", fontSize: 10 };
const gridColor = "#252d36";

function DemoLabel() {
  return <StatusBadge tone="amber">Illustrative demo</StatusBadge>;
}

export function ChartContainer({
  title,
  detail,
  children,
  className = "",
}: {
  title: string;
  detail?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return <Panel className={className}><PanelHeading title={title} detail={detail} action={<DemoLabel />} /><div className="p-4">{children}</div></Panel>;
}

export function SentimentTrendChart() {
  return (
    <ChartContainer title="News sentiment" detail="Illustrative volume by sentiment · not model output">
      <div className="h-[235px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={demoTrend} barGap={3} barCategoryGap="35%">
            <CartesianGrid vertical={false} stroke={gridColor} />
            <XAxis dataKey="day" tickLine={false} axisLine={false} tick={axisStyle} />
            <YAxis tickLine={false} axisLine={false} tick={axisStyle} width={24} />
            <Tooltip contentStyle={{ background: "#141a21", border: "1px solid #303a45", borderRadius: 8, fontSize: 11 }} />
            <Bar dataKey="positive" stackId="sentiment" fill="#42b883" radius={[0, 0, 0, 0]} />
            <Bar dataKey="neutral" stackId="sentiment" fill="#596572" />
            <Bar dataKey="negative" stackId="sentiment" fill="#df6872" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-3 flex justify-center gap-5 text-[10px] text-[#89939f]">
        {[["#42b883", "Positive"], ["#596572", "Neutral"], ["#df6872", "Negative"]].map(([color, label]) => <span key={label} className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-sm" style={{ backgroundColor: color }} />{label}</span>)}
      </div>
    </ChartContainer>
  );
}

export function MarketReactionChart() {
  return (
    <ChartContainer title="Market overview" detail="Synthetic index path for UI preview · no live prices">
      <div className="h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={demoMarketLine} margin={{ top: 10, right: 4, bottom: 0, left: -20 }}>
            <defs><linearGradient id="demoArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#8ba9ff" stopOpacity={0.18} /><stop offset="95%" stopColor="#8ba9ff" stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid vertical={false} stroke={gridColor} />
            <XAxis dataKey="time" tickLine={false} axisLine={false} tick={axisStyle} minTickGap={20} />
            <YAxis tickLine={false} axisLine={false} tick={axisStyle} />
            <Tooltip contentStyle={{ background: "#141a21", border: "1px solid #303a45", borderRadius: 8, fontSize: 11 }} />
            <Area type="monotone" dataKey="value" stroke="#9bb2ff" strokeWidth={2} fill="url(#demoArea)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </ChartContainer>
  );
}

export function EquityCurveChart() {
  return (
    <ChartContainer title="Equity curve" detail="Illustrative series only · no backtest has been run">
      <div className="h-[250px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={demoEquity} margin={{ top: 10, right: 10, bottom: 0, left: -15 }}>
            <CartesianGrid vertical={false} stroke={gridColor} />
            <XAxis dataKey="date" tickLine={false} axisLine={false} tick={axisStyle} />
            <YAxis tickLine={false} axisLine={false} tick={axisStyle} />
            <Tooltip contentStyle={{ background: "#141a21", border: "1px solid #303a45", borderRadius: 8, fontSize: 11 }} />
            <Line type="monotone" dataKey="strategy" name="Strategy (demo)" stroke="#9bb2ff" dot={false} strokeWidth={2} />
            <Line type="monotone" dataKey="baseline" name="Baseline (demo)" stroke="#78838f" dot={false} strokeWidth={1.5} strokeDasharray="4 4" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartContainer>
  );
}

export function DrawdownChart() {
  return (
    <ChartContainer title="Drawdown" detail="Illustrative series only · no backtest has been run">
      <div className="h-[210px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={demoDrawdown} margin={{ top: 10, right: 8, bottom: 0, left: -15 }}>
            <CartesianGrid vertical={false} stroke={gridColor} />
            <XAxis dataKey="date" tickLine={false} axisLine={false} tick={axisStyle} />
            <YAxis tickLine={false} axisLine={false} tick={axisStyle} />
            <Tooltip contentStyle={{ background: "#141a21", border: "1px solid #303a45", borderRadius: 8, fontSize: 11 }} />
            <Area type="monotone" dataKey="drawdown" stroke="#df6872" fill="#df6872" fillOpacity={0.13} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </ChartContainer>
  );
}

export function RegimeDistributionChart() {
  const colors = ["#7187b5", "#65717e", "#bd9652"];
  return (
    <ChartContainer title="Regime performance" detail="No regime classifications available">
      <div className="flex min-h-[210px] items-center justify-center gap-7">
        <div className="relative h-[160px] w-[160px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart><Pie data={demoRegimes} dataKey="count" innerRadius={52} outerRadius={72} paddingAngle={3}>{demoRegimes.map((entry, index) => <Cell key={entry.name} fill={colors[index]} />)}</Pie></PieChart>
          </ResponsiveContainer>
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"><span className="text-lg font-semibold">—</span><span className="text-[9px] text-[#89939f]">regimes</span></div>
        </div>
        <ul className="space-y-3">{demoRegimes.map((item, index) => <li key={item.name} className="flex items-center gap-2 text-[10px] text-[#98a2ad]"><i className="h-2 w-2 rounded-full" style={{ background: colors[index] }} />{item.name}<span className="ml-auto text-[#75808c]">—</span></li>)}</ul>
      </div>
    </ChartContainer>
  );
}
