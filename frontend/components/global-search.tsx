"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Icon } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
type SearchCompany = { ticker: string; name: string; sector?: string | null };

export function GlobalCompanySearch() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchCompany[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [directoryNote, setDirectoryNote] = useState("");

  useEffect(() => {
    const onShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, []);

  useEffect(() => {
    const term = query.trim();
    if (!term) {
      setResults([]);
      setError("");
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ search: term, limit: "6", include_quotes: "false" });
        const response = await fetch(`${API}/companies?${params}`, { signal: controller.signal, cache: "no-store" });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail ?? `Company search returned ${response.status}`);
        setResults((data.companies ?? []) as SearchCompany[]);
        setDirectoryNote(data.directory?.status === "stale_limited_fallback" ? data.directory.detail : "");
        setActiveIndex(0);
      } catch (reason) {
        if (!controller.signal.aborted) {
          setResults([]);
          setError(reason instanceof Error ? reason.message : "Company search is unavailable.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 220);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query]);

  function choose(company?: SearchCompany) {
    if (!company) return;
    setOpen(false);
    setQuery("");
    router.push(`/companies/${encodeURIComponent(company.ticker)}`);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    } else if (event.key === "ArrowDown" && results.length) {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((current) => (current + 1) % results.length);
    } else if (event.key === "ArrowUp" && results.length) {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((current) => (current - 1 + results.length) % results.length);
    } else if (event.key === "Enter" && open) {
      event.preventDefault();
      choose(results[activeIndex] ?? results[0]);
    }
  }

  return <div className="relative w-full max-w-[420px]">
    <label className="flex h-11 items-center gap-2.5 rounded-xl border border-line bg-panel-soft/90 px-3.5 text-subtle shadow-inner transition-colors focus-within:border-accent/80 focus-within:bg-panel">
      <Icon name="search" size={17} />
      <span className="sr-only">Search companies by name or ticker</span>
      <input
        ref={inputRef}
        value={query}
        onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
        onFocus={() => setOpen(Boolean(query.trim()))}
        onKeyDown={handleKeyDown}
        role="combobox"
        aria-label="Search companies by name or ticker"
        aria-expanded={open && Boolean(query.trim())}
        aria-controls="global-company-results"
        aria-autocomplete="list"
        aria-activedescendant={open && results.length ? `global-company-${activeIndex}` : undefined}
        placeholder="Find a company or ticker"
        autoComplete="off"
        className="min-w-0 flex-1 bg-transparent text-sm text-text outline-none placeholder:text-subtle"
      />
      {loading ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent/30 border-t-accent" aria-label="Searching" /> : <kbd className="hidden rounded border border-line px-1.5 py-0.5 text-[10px] text-subtle lg:inline">Ctrl K</kbd>}
    </label>
    {open && query.trim() && <>
      <button type="button" aria-label="Close search results" className="fixed inset-0 z-20 cursor-default bg-transparent" onClick={() => setOpen(false)} />
      <div id="global-company-results" role="listbox" aria-label="Company search results" className="absolute left-0 right-0 top-[calc(100%+10px)] z-30 overflow-hidden rounded-2xl border border-line bg-panel shadow-[0_24px_60px_rgba(12,9,23,0.48)]">
        {loading && <p className="px-4 py-3 text-xs text-muted" role="status">Searching the company directory…</p>}
        {error && <p className="px-4 py-3 text-xs text-negative" role="alert">{error}</p>}
        {directoryNote && <p className="border-b border-line-soft bg-warning/10 px-4 py-2 text-[10px] leading-4 text-warning" role="status">{directoryNote}</p>}
        {!loading && !error && results.length === 0 && <p className="px-4 py-3 text-xs text-muted">No companies matched “{query.trim()}”.</p>}
        {results.map((company, index) => <Link
          id={`global-company-${index}`}
          key={company.ticker}
          href={`/companies/${encodeURIComponent(company.ticker)}`}
          role="option"
          aria-selected={index === activeIndex}
          onClick={() => { setOpen(false); setQuery(""); }}
          onMouseEnter={() => setActiveIndex(index)}
          className={`flex min-h-14 items-center justify-between gap-3 border-b border-line-soft px-4 py-3 last:border-0 ${index === activeIndex ? "bg-panel-raised" : "hover:bg-panel-soft"}`}
        >
          <span className="min-w-0"><span className="block truncate text-sm font-medium text-text">{company.name}</span><span className="mt-0.5 block text-[11px] text-subtle">{company.sector ?? "Sector unavailable"}</span></span>
          <span className="rounded-lg border border-accent/30 bg-accent/10 px-2.5 py-1.5 text-xs font-semibold tracking-wide text-accent-strong">{company.ticker}</span>
        </Link>)}
        <div className="flex items-center justify-between border-t border-line-soft bg-panel-soft/60 px-4 py-2 text-[10px] text-subtle"><span>Search by company name or ticker</span><span>↑ ↓ navigate · Enter open</span></div>
      </div>
    </>}
  </div>;
}
