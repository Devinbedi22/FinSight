export type SavedCompany = { ticker: string; name: string; sector: string };
export type WatchlistReadResult = { items: SavedCompany[]; error: string | null; errorKind: "invalid_data" | "storage" | null };
export type WatchlistUpdateResult = { items: SavedCompany[]; error: string | null };

export {
  addWatchlistCompany,
  readWatchlist,
  removeWatchlistCompany,
  WATCHLIST_STORAGE_KEY,
  writeWatchlist,
} from "./watchlist-store.mjs";
