"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PricePredictionChart, type ForecastPoint } from "@/components/charts";
import { EmptyState, PageHeader, Panel, PanelHeading, StatCard, StatusBadge } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
type NewsUsed = { id: number; title: string; url: string; published_at: string; relevance_score: number | null; explicit_company_mention: boolean };
type Analysis = {
  ticker: string;
  company: string;
  sector: string;
  history: ForecastPoint[];
  latest_price?: number | null;
  daily_change?: number | null;
  prediction: { expected_return: number; forecast_price: number; as_of: string; horizon_days: number } | null;
  news_used: NewsUsed[];
  status: string;
  model?: string;
  model_artifact?: string;
};

export default function CompanyDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const [ticker, setTicker] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void params.then(({ ticker: raw }) => {
      const symbol = raw.toUpperCase();
      setTicker(symbol);
      return fetch(`${API}/companies/${symbol}/prediction`, { cache: "no-store" });
    }).then(async (response) => {
      if (!response.ok) throw new Error((await response.json()).detail ?? `Prediction API returned ${response.status}`);
      return response.json();
    }).then((data) => { if (active) setAnalysis(data); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Company forecast unavailable."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [params]);

  const prediction = analysis?.prediction;
  return <>
    <div className="mb-5 text-[11px] text-[#75808c]"><Link href="/companies" className="hover:text-white">S&P 500</Link><span className="px-2">/</span>{ticker}</div>
    <PageHeader eyebrow={analysis?.sector ?? "S&P 500 company"} title={analysis?.company ?? ticker} description="Company-specific news retrieval, actual daily prices, and a 30-day FinancialBERT Model v2 return forecast." action={<StatusBadge tone={error ? "red" : loading ? "muted" : prediction ? "blue" : "amber"}>{error ? "Unavailable" : loading ? "Loading" : prediction ? "Forecast ready" : "No forecast"}</StatusBadge>} />
    {error && <div className="mb-4 rounded-lg border border-red-900/50 bg-red-950/20 p-3 text-xs text-red-200">{error}</div>}
    {loading ? <Panel><p className="p-6 text-sm text-[#89939f]">Retrieving price history, relevant news, and model forecast…</p></Panel> : analysis && <>
      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <StatCard label="Latest observed close" value={analysis.latest_price == null ? "Unavailable" : `$${analysis.latest_price.toFixed(2)}`} note={analysis.history.at(-1)?.date ?? "No price date"} />
        <StatCard label="30-day expected return" value={prediction ? `${prediction.expected_return >= 0 ? "+" : ""}${(prediction.expected_return * 100).toFixed(2)}%` : "Unavailable"} note={prediction ? "Raw regression output from the loaded checkpoint" : analysis.status.replaceAll("_", " ")} />
        <StatCard label="Forecast price" value={prediction ? `$${prediction.forecast_price.toFixed(2)}` : "Unavailable"} note={prediction ? `Model estimate for ${prediction.horizon_days} days from ${prediction.as_of}` : "Requires price history and relevant stored news"} />
      </div>
      <PricePredictionChart history={analysis.history} forecast={prediction ? { date: new Date(new Date(prediction.as_of).getTime() + prediction.horizon_days * 86_400_000).toISOString().slice(0, 10), price: prediction.forecast_price, expectedReturn: prediction.expected_return } : null} />
      <Panel className="mt-5">
        <PanelHeading title="News used by the forecast" detail={`${analysis.news_used.length} company-linked article${analysis.news_used.length === 1 ? "" : "s"} selected by the retrieval/reranking stage`} />
        {analysis.news_used.length ? <div className="divide-y divide-[#222a32]">{analysis.news_used.map((item) => <a key={item.id} href={item.url} target="_blank" rel="noreferrer" className="block px-5 py-4 hover:bg-[#131920]"><div className="flex flex-wrap items-center gap-2 text-[10px] text-[#75808c]"><time>{new Date(item.published_at).toLocaleString()}</time><span>·</span><span>{item.explicit_company_mention ? "Company named" : `Stocky relevance ${item.relevance_score?.toFixed(3) ?? "n/a"}`}</span></div><p className="mt-2 text-sm leading-6 text-[#dce2e8]">{item.title}</p></a>)}</div> : <EmptyState title="No company-linked news" description="The model needs stored headlines retrieved for this S&P 500 company before it can make a forecast." />}
      </Panel>
      <p className="mt-3 text-[10px] leading-5 text-[#65717d]">Experimental point forecast, not investment advice. The chart shows observed adjusted daily closes and one model-generated 30-day point—not a calibrated price path or confidence interval. Company-linked stored news descriptions are reranked with Cohere when configured; otherwise issuer mentions and Stocky match scores provide the local ranking.</p>
    </>}
  </>;
}
