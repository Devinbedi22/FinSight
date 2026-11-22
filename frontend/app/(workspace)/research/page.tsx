"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { EmptyState, PageHeader, Panel, StatusBadge } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const suggestions = [
  "Give me an overview of Apple.",
  "How has NVIDIA performed over the last year?",
  "Compare Apple and Microsoft over six months.",
  "What do Tesla's RSI and moving averages indicate?",
  "Compare Microsoft's latest available revenue and P/E.",
  "Summarize recent NVIDIA news and sentiment.",
];

type Evidence = {
  id: string;
  source: string;
  claim: string;
  observed_at?: string | null;
  reporting_period?: string | null;
  url?: string | null;
  value?: unknown;
  unit?: string | null;
  methodology?: string | null;
  freshness?: string | null;
};
type Finding = { text: string; citations: string[] };
type ResearchAnswer = {
  mode: string;
  llm_status: string;
  narrative?: string;
  narrative_citations?: string[];
  resolved_question?: string;
  intent: string;
  companies: Array<{ ticker: string; name?: string; sector?: string }>;
  findings: Finding[];
  evidence: Evidence[];
  limitations: string[];
  generated_at: string;
};
type Exchange = { question: string; answer?: ResearchAnswer; error?: string };
type ProviderStatus = { configured: boolean; provider: string; status: string };
type Directory = { status: string; detail: string };

export default function ResearchAssistantPage() {
  const [question, setQuestion] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null);
  const [directory, setDirectory] = useState<Directory | null>(null);
  const providerMessage = !providerStatus
    ? "Checking optional research provider…"
    : providerStatus.configured
      ? `Provider: ${providerStatus.provider}. Evidence and citations are still validated by FinSight.`
      : providerStatus.status === "not_configured"
        ? "No LLM provider is configured; verified findings use FinSight's deterministic research pipeline."
        : "LLM provider configuration is incomplete or unsupported; deterministic findings remain available.";

  useEffect(() => {
    let active = true;
    fetch(`${API}/research/status`)
      .then((response) => response.ok ? response.json() as Promise<ProviderStatus> : null)
      .then((status) => { if (active && status) setProviderStatus(status); })
      .catch(() => { if (active) setProviderStatus({ configured: false, provider: "none", status: "unavailable" }); });
    fetch(`${API}/universe/sp500`, { cache: "no-store" })
      .then((response) => response.ok ? response.json() : null)
      .then((result) => { if (active && result?.directory) setDirectory(result.directory as Directory); })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  async function ask(value: string) {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    setQuestion("");
    setError("");
    setLoading(true);
    try {
      const response = await fetch(`${API}/research/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: trimmed,
          history: exchanges.filter((item) => item.answer).slice(-6).map((item) => ({
            question: item.answer?.resolved_question ?? item.question,
            companies: item.answer?.companies.map((company) => company.ticker) ?? [],
            finding_citations: item.answer?.findings.flatMap((finding) => finding.citations) ?? [],
          })),
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `Research request failed (${response.status}).`);
      setExchanges((previous) => [...previous, { question: trimmed, answer: payload as ResearchAnswer }]);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Research service is unavailable.";
      setExchanges((previous) => [...previous, { question: trimmed, error: message }]);
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask(question);
  }

  return (
    <div>
      <PageHeader eyebrow="Evidence-led research" title="Research assistant" description="Ask about supported S&P 500 companies. Each response is assembled from FinSight's existing market, SEC, technical, and persisted-news data." />

      {directory?.status === "stale_limited_fallback" && <div role="status" className="mb-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs leading-5 text-warning">{directory.detail} Research can still use the locally supported tickers; provider-dependent evidence may be unavailable.</div>}

      <div className="mb-5 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 text-xs leading-5 text-[var(--muted)]">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone={providerStatus?.configured ? "green" : "blue"}>{providerStatus?.configured ? "Optional LLM enabled" : "Deterministic mode"}</StatusBadge>
          <span>{providerMessage}</span>
          {exchanges.length > 0 && <button type="button" onClick={() => { setExchanges([]); setError(""); }} className="ml-auto min-h-9 rounded-md border border-[var(--line)] px-3 text-[11px] text-[var(--muted)] hover:bg-[var(--panel-raised)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-strong)]">Clear session</button>}
        </div>
        <p className="mt-2 text-[var(--muted)]">This page summarizes sourced observations and interpretations. It does not provide personalized recommendations or validated forecasts. Conversation context stays in this page session.</p>
      </div>

      <Panel className="overflow-hidden">
        <div className="max-h-[62vh] min-h-72 space-y-5 overflow-y-auto p-4 sm:p-6" aria-live="polite" aria-label="Research conversation">
          {exchanges.length === 0 ? (
            <EmptyState title="What would you like to research?" description="Ask about a supported company, price history, technical indicators, reported fundamentals, or news stored in FinSight." />
          ) : exchanges.map((exchange, index) => (
            <section key={`${index}-${exchange.question}`} className="space-y-3" aria-label={`Research exchange ${index + 1}`}>
              <div className="ml-auto max-w-3xl rounded-xl border border-[var(--line)] bg-[var(--panel-raised)] p-4 text-sm leading-6 text-[var(--text)]">{exchange.question}</div>
              {exchange.answer ? <AnswerCard answer={exchange.answer} /> : (
                <div className="max-w-3xl rounded-xl border border-[var(--line-soft)] bg-[var(--panel-soft)] p-4 text-sm text-warning" role="alert"><p>{exchange.error}</p><button type="button" disabled={loading} onClick={() => void ask(exchange.question)} className="mt-3 min-h-11 rounded-lg border border-[var(--line)] px-4 py-2 text-xs font-semibold text-[var(--accent-strong)] hover:bg-[var(--panel-raised)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-strong)] disabled:opacity-50">Retry</button></div>
              )}
            </section>
          ))}
          {loading && <p role="status" className="flex items-center gap-3 px-2 py-4 text-sm text-[var(--muted)]"><span className="h-4 w-4 animate-pulse rounded-full bg-accent" />Retrieving relevant evidence…</p>}
        </div>

        {exchanges.length === 0 && <div className="border-t border-[var(--line-soft)] px-4 py-4 sm:px-6"><p className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-[var(--muted)]">Try a question</p><div className="flex flex-wrap gap-2">{suggestions.map((item) => <button key={item} type="button" disabled={loading} onClick={() => void ask(item)} className="min-h-11 rounded-lg border border-[var(--line)] px-3 py-2 text-left text-xs text-[var(--muted)] hover:border-[var(--accent-strong)] hover:bg-[var(--panel-raised)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-strong)] disabled:opacity-50">{item}</button>)}</div></div>}

        <form onSubmit={onSubmit} className="flex flex-col gap-3 border-t border-[var(--line-soft)] bg-[var(--panel-soft)] p-4 sm:flex-row sm:items-end sm:px-6">
          <label className="min-w-0 flex-1 text-xs font-medium text-[var(--muted)]">Your research question
            <textarea value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={500} rows={2} placeholder="Ask about a supported company…" className="mt-2 block min-h-20 w-full resize-y rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] px-3 py-2.5 text-sm leading-5 text-[var(--text)] placeholder:text-[var(--subtle)] focus:border-[var(--accent-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/30" />
          </label>
          <button type="submit" disabled={loading || !question.trim()} className="min-h-11 rounded-lg bg-accent px-5 py-2 text-sm font-semibold text-[#241f32] hover:bg-accent-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-strong)] disabled:cursor-not-allowed disabled:opacity-50">{loading ? "Researching…" : "Ask"}</button>
        </form>
        {error && <p className="px-4 pb-4 text-xs text-negative" role="status">The last request did not complete. You can edit the question and try again.</p>}
      </Panel>
    </div>
  );
}

function AnswerCard({ answer }: { answer: ResearchAnswer }) {
  const deterministicStatuses = new Set(["not_configured", "configuration_incomplete", "unsupported_provider", "provider_timeout", "provider_rate_limited", "provider_unavailable", "invalid_response", "invalid_citations", "unsupported_numbers", "context_too_large", "no_evidence_fallback"]);
  const statusLabel = answer.llm_status === "generated" ? "LLM · evidence citations validated" : deterministicStatuses.has(answer.llm_status) ? "Deterministic findings" : answer.llm_status;
  const providerFallback = answer.llm_status !== "generated" && !["not_configured", "no_evidence_fallback"].includes(answer.llm_status);
  return <div className="max-w-4xl space-y-4 rounded-xl border border-[var(--line-soft)] bg-[var(--panel)] p-4 sm:p-5">
    <div className="flex flex-wrap items-center gap-2"><StatusBadge tone={answer.llm_status === "generated" ? "green" : "blue"}>{statusLabel}</StatusBadge><StatusBadge tone="muted">{answer.intent}</StatusBadge>{answer.companies.map((company) => <Link key={company.ticker} href={`/companies/${company.ticker}`} className="rounded-md border border-[var(--line)] px-2 py-1 text-[11px] text-[var(--accent-strong)] hover:border-[var(--accent-strong)]">{company.ticker}</Link>)}<span className="text-[10px] text-[var(--subtle)]">Generated {new Date(answer.generated_at).toLocaleString()}</span></div>
    {providerFallback && <p role="status" className="rounded-md border border-warning/30 bg-warning/10 p-3 text-xs leading-5 text-warning">The optional language-model explanation was unavailable or failed validation. FinSight is showing its deterministic evidence summary.</p>}
    {answer.narrative && <div className="rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] p-4"><p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[var(--accent-strong)]">LLM interpretation</p><p className="whitespace-pre-wrap text-sm leading-6 text-[var(--text)]">{answer.narrative}</p>{answer.narrative_citations?.length ? <div className="mt-3 flex flex-wrap gap-2" aria-label="Interpretation citations">{answer.narrative_citations.map((id) => <a key={id} href={`#${id}`} className="min-h-9 rounded-md border border-[var(--line)] px-2.5 py-1.5 text-xs text-[var(--accent-strong)] underline decoration-dotted underline-offset-2">[{id}]</a>)}</div> : null}</div>}
    <div className="space-y-3"><p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--muted)]">Verified findings</p>{answer.findings.map((finding, index) => <p key={index} className="text-sm leading-6 text-[var(--text)]">{finding.text} {finding.citations.map((id) => <a key={id} href={`#${id}`} className="ml-1 text-xs font-semibold text-[var(--accent-strong)] underline decoration-dotted underline-offset-2">[{id}]</a>)}</p>)}</div>
    {answer.evidence.length > 0 && <details className="rounded-lg border border-[var(--line-soft)] bg-[var(--panel-soft)] p-3" open><summary className="cursor-pointer text-xs font-semibold text-[var(--muted)]">Sources and supporting evidence ({answer.evidence.length})</summary><ul className="mt-3 space-y-3">{answer.evidence.map((item) => <li id={item.id} key={item.id} className="scroll-mt-24 border-t border-[var(--panel-raised)] pt-3 text-xs leading-5 text-[var(--muted)]"><p className="font-semibold text-[var(--text)]">{item.id}: {item.claim}</p><p className="mt-1">Source: {item.url ? <a href={item.url} target="_blank" rel="noreferrer" className="text-[var(--accent-strong)] underline">{item.source}</a> : item.source}{item.observed_at && ` · observed/filed ${item.observed_at}`}{item.reporting_period && ` · period ${item.reporting_period}`}{item.freshness && ` · status ${item.freshness}`}</p>{item.value !== undefined && item.value !== null && <EvidenceValue value={item.value} unit={item.unit} />}{item.methodology && <p className="mt-1 break-words text-[var(--subtle)]">Method: {item.methodology}</p>}</li>)}</ul></details>}
    {answer.limitations.length > 0 && <div className="rounded-lg border border-warning/30 bg-warning/10 p-3"><p className="text-[10px] font-semibold uppercase tracking-wide text-warning">Limitations</p><ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-5 text-[var(--warning)]">{answer.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div>}
    <p className="text-[10px] text-[var(--subtle)]">These observations are descriptive and are not investment advice or validated predictions.</p>
  </div>;
}

function EvidenceValue({ value, unit }: { value: unknown; unit?: string | null }) {
  if (value === null || value === undefined) return null;
  if (typeof value !== "object") return <p className="mt-1 break-words">Value: {String(value)}{unit ? ` ${unit}` : ""}</p>;
  const record = value as Record<string, unknown>;
  const indicators = record.indicators && typeof record.indicators === "object" ? record.indicators as Record<string, unknown> : null;
  if (indicators) {
    const regime = record.regime && typeof record.regime === "object" ? record.regime as Record<string, unknown> : {};
    return <div className="mt-2 space-y-2"><p>Market regime: {String(regime.label ?? "unavailable")}{regime.criteria ? ` · ${String(regime.criteria)}` : ""}</p><dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">{Object.entries(indicators).map(([name, raw]) => { const metric = raw && typeof raw === "object" ? raw as Record<string, unknown> : {}; return <div key={name} className="min-w-0 rounded-md border border-[var(--panel-raised)] bg-[var(--panel)] px-2.5 py-2"><dt className="text-[10px] font-medium text-[var(--muted)]">{name.replaceAll("_", " ")}</dt><dd className="mt-1 break-words tabular-nums text-[var(--text)]">{metric.value == null ? "Unavailable" : `${String(metric.value)} ${String(metric.unit ?? "")}`}</dd>{typeof metric.methodology === "string" && <dd className="mt-1 break-words text-[10px] leading-4 text-[var(--subtle)]">{metric.methodology}</dd>}</div>; })}</dl></div>;
  }
  return <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 break-words">{Object.entries(record).map(([key, item]) => <div key={key} className="min-w-0"><dt className="inline text-[var(--muted)]">{key.replaceAll("_", " ")}: </dt><dd className="inline text-[var(--text)]">{item == null ? "unavailable" : String(item)}</dd></div>)}</dl>;
}
