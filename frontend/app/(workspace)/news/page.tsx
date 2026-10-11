"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EmptyState, PageHeader, Panel, SearchInput, StatusBadge } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const PAGE_SIZE = 30;

type Candidate = { ticker: string; name: string; entity_mentioned?: boolean; security_type?: string; business_sector?: string | null; relevance_score?: number | null };
type Impact = { ticker: string; impact?: string | null; status: string; evidence_status?: string; expected_return?: number | null; model?: string | null };
type Article = {
  id: number;
  title: string;
  url: string;
  source: string;
  published_at: string | null;
  ticker_candidates: Candidate[];
  impact_predictions: Impact[];
  usefulness?: { label?: string; ticker_inference?: string; method?: string } | null;
};

export default function NewsPage() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState("");
  const sentinel = useRef<HTMLDivElement>(null);
  const nextCursor = useRef<string | null>(null);
  const requestInFlight = useRef(false);
  const firstLoadedAt = useRef<string | null>(null);
  const loadPage = useCallback(async (cursor: string | null, append: boolean) => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    if (append) setLoadingMore(true);
    else setLoading(true);
    try {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
      if (cursor) params.set("cursor", cursor);
      if (append && !cursor && firstLoadedAt.current) params.set("before", firstLoadedAt.current);
      const response = await fetch(`${API}/news?${params.toString()}`);
      if (!response.ok) throw new Error(`News API returned ${response.status}`);
      const page: Article[] = await response.json();
      setArticles((previous) => {
        const combined = append ? [...previous, ...page] : [...page, ...previous.filter((old) => !page.some((fresh) => fresh.id === old.id))];
        return [...new Map(combined.map((article) => [article.id, article])).values()];
      });
      // Refreshing the newest page must not rewind the older-page cursor.
      const next = response.headers.get("X-Next-Cursor");
      if (append || cursor === null || next) nextCursor.current = next;
      setHasMore(response.headers.get("X-Has-More") === "true");
      if (!append && page.length && !firstLoadedAt.current) firstLoadedAt.current = page[0].published_at;
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not connect to the FinSight API.");
    } finally {
      requestInFlight.current = false;
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    void loadPage(null, false);
    const timer = window.setInterval(() => void loadPage(null, false), 60_000);
    return () => window.clearInterval(timer);
  }, [loadPage]);

  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasMore || loading || loadingMore) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting) && nextCursor.current) void loadPage(nextCursor.current, true);
    }, { rootMargin: "700px" });
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, loading, loadingMore, loadPage]);

  const filtered = useMemo(() => articles.filter((article) => {
    const stockyPending = article.usefulness?.ticker_inference === "pending";
    const hasStockyMatches = article.ticker_candidates.length > 0;
    const matchesSearch = `${article.title} ${article.source} ${article.ticker_candidates.map((candidate) => `${candidate.ticker} ${candidate.name}`).join(" ")}`
      .toLowerCase().includes(query.toLowerCase());
    return (stockyPending || hasStockyMatches) && matchesSearch;
  }), [articles, query]);

  return <>
    <PageHeader eyebrow="News archive · model-scored" title="News" description="Stories are screened by a pretrained financial-relevance model. Expand one to inspect Stocky matches and FinancialBERT estimates." action={<StatusBadge tone={error ? "red" : "green"}>{error ? "API unavailable" : "Polling"}</StatusBadge>} />
    {error && <div className="mb-4 rounded-lg border border-red-900/50 bg-red-950/20 p-3 text-xs text-red-200">{error}. Start the backend at {API}.</div>}
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <SearchInput placeholder="Search headlines, sources, S&P 500 tickers…" className="w-full sm:max-w-lg" value={query} onChange={setQuery} />
      <span className="text-[11px] text-[#75808c]">{filtered.length} loaded · newest first · older stories load as you scroll</span>
    </div>
    <Panel className="overflow-hidden">
      {loading && !articles.length ? <p className="p-6 text-sm text-[#89939f]">Loading news…</p> : filtered.length ? filtered.map((article) => {
        const linkedCompanies = article.ticker_candidates;
        return <article key={article.id} className="border-b border-[#222a32] px-5 py-5 last:border-0 sm:px-7">
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-[#77838f]">
            <span className="font-medium text-[#aeb8c3]">{article.source}</span><span aria-hidden="true">·</span>
            <time dateTime={article.published_at ?? undefined}>{article.published_at ? new Date(article.published_at).toLocaleString() : "Date unavailable"}</time>
          </div>
          <a href={`${API}/news/${article.id}/open`} target="_blank" rel="noreferrer" className="mt-2 block max-w-5xl text-[16px] font-medium leading-7 text-[#e1e7ed] hover:text-white">{article.title}<span className="ml-2 text-xs text-[#8291a1]">Open source ↗</span></a>
          <details className="group mt-4 rounded-lg border border-[#29323c] bg-[#10151b]">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs text-[#cbd4de]"><span>{article.usefulness?.ticker_inference === "pending" ? "Model enrichment pending · view article" : `Stocky matched ${linkedCompanies.length} S&P 500 tickers · view impact estimates`}</span><span aria-hidden="true" className="text-[#8793a0] transition-transform group-open:rotate-180">⌄</span></summary>
          <div className="border-t border-[#252e38] p-3"><p className="mb-2 text-[10px] text-[#74818e]">{article.usefulness?.ticker_inference === "pending" ? "This archived story is stored; Stocky matching and FinancialBERT impact inference will be filled by the background backfill." : "Select a ticker to open its prediction chart. Directions are FinancialBERT estimates."}</p><div className="flex flex-wrap gap-2">{linkedCompanies.map((company) => {
            const impact = article.impact_predictions.find((item) => item.ticker === company.ticker);
            const direction = impact?.impact;
            return <Link key={company.ticker} href={`/companies/${company.ticker}`} className="inline-flex max-w-full flex-col gap-1 rounded-md border border-[#303b47] bg-[#121922] px-2.5 py-2 text-[11px] hover:border-[#7087ba]">
              <span className="flex flex-wrap items-center gap-x-2"><span className="font-semibold text-[#c5d3f6]">{company.ticker}</span><span className="max-w-[220px] truncate text-[#89939f]">{company.name}</span></span>
              <span className="flex flex-wrap items-center gap-x-2 text-[10px] text-[#7f8b97]">Stocky match {company.relevance_score?.toFixed(3) ?? "—"} · {company.entity_mentioned ? "named in story" : "indirect candidate"}{company.security_type && company.security_type !== "common_or_adr" ? ` · ${company.security_type}` : ""}
                {direction ? <span className={direction === "positive" ? "text-emerald-300" : direction === "negative" ? "text-rose-300" : "text-[#aab4bf]"}>· {impact?.status === "reported_market_move" ? "Reported move" : "FinancialBERT"} {direction}{impact?.expected_return != null ? ` (${(impact.expected_return * 100).toFixed(1)}%)` : ""}</span> : <span>· impact {impact?.status.replaceAll("_", " ") ?? "not computed"}</span>}
              </span>
            </Link>;
          })}{linkedCompanies.length === 0 && <p className="px-1 py-2 text-xs text-[#8b96a3]">No S&amp;P 500 candidates for this article.</p>}</div></div>
          </details>
        </article>;
      }) : <EmptyState title={query ? "No matching stories" : "No stories stored yet"} description={query ? "Try a different headline, source, company, or ticker." : "Automatic ingestion runs while the backend is running. New stories will appear here."} />}
      <div ref={sentinel} className="h-1" />
      {loadingMore && <p className="border-t border-[#222a32] p-4 text-center text-xs text-[#89939f]">Loading older stories…</p>}
      {!hasMore && articles.length > 0 && <p className="border-t border-[#222a32] p-4 text-center text-[11px] text-[#65717d]">End of the stories currently stored in this archive.</p>}
    </Panel>
  </>;
}
