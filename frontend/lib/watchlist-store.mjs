export const WATCHLIST_STORAGE_KEY = "finsight.watchlist.v1";

function isSavedCompany(value) {
  if (!value || typeof value !== "object") return false;
  const company = value;
  return typeof company.ticker === "string" && /^[A-Z0-9.-]{1,16}$/.test(company.ticker)
    && typeof company.name === "string" && typeof company.sector === "string";
}

export function readWatchlist(storage) {
  let raw;
  try {
    raw = storage.getItem(WATCHLIST_STORAGE_KEY);
  } catch {
    return { items: [], error: "Browser storage is unavailable.", errorKind: "storage" };
  }
  if (raw === null) return { items: [], error: null, errorKind: null };
  let parsed;
  try { parsed = JSON.parse(raw); }
  catch { return { items: [], error: "Saved watchlist data is corrupted. It has been left untouched.", errorKind: "invalid_data" }; }
  if (!Array.isArray(parsed) || parsed.length > 500 || !parsed.every(isSavedCompany)) {
    return { items: [], error: "Saved watchlist data is invalid. It has been left untouched.", errorKind: "invalid_data" };
  }
  const unique = new Map();
  for (const company of parsed) unique.set(company.ticker, company);
  return { items: [...unique.values()], error: null, errorKind: null };
}

export function writeWatchlist(storage, items) {
  try {
    storage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(items));
    return null;
  } catch {
    return "Could not save this change in browser storage. Check the browser's storage settings and available space.";
  }
}

export function addWatchlistCompany(items, company) {
  if (!isSavedCompany(company)) return { items, error: "Company ticker or directory details are invalid." };
  if (items.some((item) => item.ticker === company.ticker)) return { items, error: null };
  if (items.length >= 500) return { items, error: "The local watchlist is full (500 companies)." };
  return { items: [...items, company], error: null };
}

export function removeWatchlistCompany(items, ticker) {
  return items.filter((item) => item.ticker !== ticker);
}
