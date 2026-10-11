"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Panel, PanelHeading, StatusBadge } from "@/components/ui";

const axisStyle = { fill: "#7d8995", fontSize: 10 };
const gridColor = "#252d36";

export type ForecastPoint = { date: string; close: number };

export function PricePredictionChart({
  history,
  forecast,
  currency = "USD",
}: {
  history: ForecastPoint[];
  forecast: { date: string; price: number; expectedReturn: number } | null;
  currency?: string;
}) {
  const data: { date: string; actual: number | null; forecast: number | null }[] =
    history.map((point) => ({ date: point.date, actual: point.close, forecast: null }));
  if (forecast && history.length) {
    data[data.length - 1].forecast = history[history.length - 1].close;
    data.push({ date: forecast.date, actual: null, forecast: forecast.price });
  }
  const money = new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 });
  return <Panel>
    <PanelHeading title="Price history & 30-day forecast" detail="Observed adjusted closes and FinancialBERT Model v2 point forecast" action={<StatusBadge tone={forecast ? "blue" : "muted"}>{forecast ? "Model forecast" : "No forecast"}</StatusBadge>} />
    {history.length ? <div className="h-[340px] p-4 sm:h-[420px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 12, right: 16, bottom: 4, left: 4 }}>
          <CartesianGrid vertical={false} stroke={gridColor} />
          <XAxis dataKey="date" tickLine={false} axisLine={false} tick={axisStyle} minTickGap={38} />
          <YAxis tickLine={false} axisLine={false} tick={axisStyle} width={66} domain={["auto", "auto"]} tickFormatter={(value: number) => money.format(value)} />
          <Tooltip formatter={(value, name) => [money.format(Number(value)), name === "actual" ? "Observed close" : "Predicted close"]} labelStyle={{ color: "#dce2e8" }} contentStyle={{ background: "#141a21", border: "1px solid #303a45", borderRadius: 8, fontSize: 11 }} />
          <Line type="monotone" dataKey="actual" name="Observed close" stroke="#91aaff" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
          <Line type="linear" dataKey="forecast" name="Predicted close" stroke="#39c9a0" strokeWidth={2} strokeDasharray="6 5" connectNulls dot={{ r: 4, fill: "#39c9a0", strokeWidth: 0 }} activeDot={{ r: 5 }} />
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-2 text-[10px] text-[#89939f]">
        <span className="flex items-center gap-2"><i className="h-0.5 w-4 bg-[#91aaff]" />Observed close</span>
        {forecast && <><span className="flex items-center gap-2"><i className="h-0.5 w-4 border-t border-dashed border-[#39c9a0]" />30-day forecast</span><span className="tabular-nums">Model return: {forecast.expectedReturn >= 0 ? "+" : ""}{(forecast.expectedReturn * 100).toFixed(2)}%</span></>}
      </div>
    </div> : <p className="p-6 text-sm text-[#89939f]">No price history is available for this company.</p>}
  </Panel>;
}
