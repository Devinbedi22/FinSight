import type { SavedCompany, WatchlistReadResult, WatchlistUpdateResult } from "./watchlist";

export const WATCHLIST_STORAGE_KEY: string;
export function readWatchlist(storage: Pick<Storage, "getItem">): WatchlistReadResult;
export function writeWatchlist(storage: Pick<Storage, "setItem">, items: SavedCompany[]): string | null;
export function addWatchlistCompany(items: SavedCompany[], company: SavedCompany): WatchlistUpdateResult;
export function removeWatchlistCompany(items: SavedCompany[], ticker: string): SavedCompany[];
