"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui";
import { addWatchlistCompany, readWatchlist, removeWatchlistCompany, WATCHLIST_STORAGE_KEY, writeWatchlist, type SavedCompany } from "@/lib/watchlist";

type WatchlistState = {
  items: SavedCompany[];
  status: "loading" | "ready" | "error";
  error: string;
  errorKind: "invalid_data" | "storage" | "write" | "capacity" | "validation" | null;
};

const changeEvent = "finsight:watchlist-change";

export function useWatchlist() {
  const [state, setState] = useState<WatchlistState>({ items: [], status: "loading", error: "", errorKind: null });
  const itemsRef = useRef<SavedCompany[]>([]);

  const hydrate = useCallback(() => {
    try {
      const result = readWatchlist(window.localStorage);
      itemsRef.current = result.items;
      setState({ items: result.items, status: result.error ? "error" : "ready", error: result.error ?? "", errorKind: result.errorKind });
    } catch {
      setState({ items: [], status: "error", error: "Browser storage is unavailable.", errorKind: "storage" });
    }
  }, []);

  useEffect(() => {
    try { hydrate(); }
    catch { setState({ items: [], status: "error", error: "Browser storage is unavailable.", errorKind: "storage" }); }
    const onStorage = (event: StorageEvent) => {
      if (event.key === WATCHLIST_STORAGE_KEY || event.key === null) hydrate();
    };
    const onLocalChange = () => hydrate();
    window.addEventListener("storage", onStorage);
    window.addEventListener(changeEvent, onLocalChange);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(changeEvent, onLocalChange);
    };
  }, [hydrate]);

  const commit = useCallback((next: SavedCompany[]) => {
    if (state.status !== "ready") return false;
    const error = writeWatchlist(window.localStorage, next);
    if (error) {
      setState((previous) => ({ ...previous, status: "error", error, errorKind: "write" }));
      return false;
    }
    itemsRef.current = next;
    setState({ items: next, status: "ready", error: "", errorKind: null });
    window.dispatchEvent(new Event(changeEvent));
    return true;
  }, [state.status]);

  const add = useCallback((company: SavedCompany) => {
    const update = addWatchlistCompany(itemsRef.current, company);
    const updateError = update.error;
    if (updateError) {
      setState((previous) => ({ ...previous, error: updateError, errorKind: updateError.includes("full") ? "capacity" : "validation" }));
      return false;
    }
    return commit(update.items);
  }, [commit]);

  const remove = useCallback((ticker: string) => commit(removeWatchlistCompany(itemsRef.current, ticker)), [commit]);

  const clearInvalidData = useCallback(() => {
    if (state.errorKind !== "invalid_data") return false;
    try {
      window.localStorage.removeItem(WATCHLIST_STORAGE_KEY);
      itemsRef.current = [];
      setState({ items: [], status: "ready", error: "", errorKind: null });
      window.dispatchEvent(new Event(changeEvent));
      return true;
    } catch {
      setState((previous) => ({ ...previous, status: "error", error: "Could not clear browser storage.", errorKind: "storage" }));
      return false;
    }
  }, [state.errorKind]);

  return { ...state, add, remove, clearInvalidData, retryStorage: hydrate, isSaved: (ticker: string) => state.items.some((item) => item.ticker === ticker) };
}

export function WatchlistButton({ company, className = "" }: { company: SavedCompany; className?: string }) {
  const watchlist = useWatchlist();
  const saved = watchlist.isSaved(company.ticker);
  const handleClick = () => saved ? watchlist.remove(company.ticker) : watchlist.add(company);
  return (
    <div className="flex flex-col items-start gap-1">
      <Button type="button" variant={saved ? "ghost" : "secondary"} className={`min-h-11 ${className}`} disabled={watchlist.status === "loading" || watchlist.status === "error"} onClick={handleClick} aria-pressed={saved}>
        {saved ? "Remove from watchlist" : "Add to watchlist"}
      </Button>
      {watchlist.error && <span className="max-w-52 text-[10px] leading-4 text-warning" role="status">{watchlist.error}</span>}
      {watchlist.status === "error" && watchlist.errorKind !== "invalid_data" && <button type="button" onClick={watchlist.retryStorage} className="text-[10px] text-[var(--accent-strong)] underline underline-offset-2">Retry browser storage</button>}
      {watchlist.status === "error" && watchlist.errorKind === "invalid_data" && <a href="/watchlist" className="text-[10px] text-[var(--accent-strong)] underline underline-offset-2">Review saved data</a>}
    </div>
  );
}
