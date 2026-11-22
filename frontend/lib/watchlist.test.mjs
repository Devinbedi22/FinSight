import test from "node:test";
import assert from "node:assert/strict";
import { addWatchlistCompany, readWatchlist, removeWatchlistCompany, WATCHLIST_STORAGE_KEY, writeWatchlist } from "./watchlist-store.mjs";

function memoryStorage() {
  const values = new Map();
  return {
    getItem(key) { return values.get(key) ?? null; },
    setItem(key, value) { values.set(key, String(value)); },
    removeItem(key) { values.delete(key); },
  };
}

const apple = { ticker: "AAPL", name: "Apple Inc.", sector: "Information Technology" };
const microsoft = { ticker: "MSFT", name: "Microsoft Corporation", sector: "Information Technology" };

test("watchlist add, remove, and browser-local persistence round trip", () => {
  const storage = memoryStorage();
  const first = addWatchlistCompany([], apple);
  const second = addWatchlistCompany(first.items, microsoft);
  assert.deepEqual(second.items.map((company) => company.ticker), ["AAPL", "MSFT"]);
  assert.equal(writeWatchlist(storage, second.items), null);
  assert.deepEqual(readWatchlist(storage), { items: second.items, error: null, errorKind: null });
  const removed = removeWatchlistCompany(second.items, "AAPL");
  assert.deepEqual(removed.map((company) => company.ticker), ["MSFT"]);
  assert.equal(writeWatchlist(storage, removed), null);
  assert.deepEqual(readWatchlist(storage).items, [microsoft]);
  assert.equal(WATCHLIST_STORAGE_KEY, "finsight.watchlist.v1");
});

test("duplicate additions are idempotent and invalid tickers are rejected", () => {
  const current = [apple];
  assert.deepEqual(addWatchlistCompany(current, apple), { items: current, error: null });
  assert.match(addWatchlistCompany(current, { ...apple, ticker: "AAPL/ADMIN" }).error, /invalid/);
});

test("corrupt local data is preserved until explicit user action", () => {
  const storage = memoryStorage();
  storage.setItem(WATCHLIST_STORAGE_KEY, "not-json");
  const result = readWatchlist(storage);
  assert.deepEqual(result.items, []);
  assert.ok(result.error);
  assert.equal(result.errorKind, "invalid_data");
  assert.equal(storage.getItem(WATCHLIST_STORAGE_KEY), "not-json");
});

test("unavailable browser storage is reported without attempting a destructive reset", () => {
  const blockedStorage = { getItem() { throw new DOMException("blocked", "SecurityError"); } };
  const result = readWatchlist(blockedStorage);
  assert.deepEqual(result.items, []);
  assert.equal(result.errorKind, "storage");
  assert.match(result.error, /unavailable/);
});
