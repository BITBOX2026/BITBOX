import { beforeEach, describe, expect, it } from "vitest";
import { loadRecentDestinations } from "./DestinationSearch";

const RECENT_KEY = "bitbox.recentDestinations";

class MemoryStorage implements Storage {
  private store = new Map<string, string>();
  get length(): number {
    return this.store.size;
  }
  clear(): void {
    this.store.clear();
  }
  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null;
  }
  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }
}

beforeEach(() => {
  (globalThis as unknown as { localStorage: Storage }).localStorage = new MemoryStorage();
});

describe("loadRecentDestinations", () => {
  it("returns an empty array when nothing is stored", () => {
    expect(loadRecentDestinations()).toEqual([]);
  });

  it("returns an empty array when storage contains invalid JSON", () => {
    localStorage.setItem(RECENT_KEY, "{not-json");
    expect(loadRecentDestinations()).toEqual([]);
  });

  it("returns an empty array when the stored value is not an array", () => {
    localStorage.setItem(RECENT_KEY, JSON.stringify({ name: "강남역" }));
    expect(loadRecentDestinations()).toEqual([]);
  });

  it("normalizes legacy plain-string entries into RouteDestination objects", () => {
    localStorage.setItem(RECENT_KEY, JSON.stringify(["강남역", "  ", "서울역"]));
    expect(loadRecentDestinations()).toEqual([{ name: "강남역" }, { name: "서울역" }]);
  });

  it("parses coordinate fields and drops non-finite values", () => {
    localStorage.setItem(
      RECENT_KEY,
      JSON.stringify([
        { name: "잠실역", address: "송파구", x: "127.1", y: "37.5" },
        { name: "이상한곳", x: "NaN", y: null },
      ]),
    );
    expect(loadRecentDestinations()).toEqual([
      { name: "잠실역", address: "송파구", x: 127.1, y: 37.5 },
      { name: "이상한곳", address: null, x: null, y: null },
    ]);
  });

  it("silently drops malformed entries without a usable name", () => {
    localStorage.setItem(RECENT_KEY, JSON.stringify([{ address: "이름없음" }, 42, null]));
    expect(loadRecentDestinations()).toEqual([]);
  });

  it("caps the result at 3 entries", () => {
    localStorage.setItem(RECENT_KEY, JSON.stringify(["a", "b", "c", "d", "e"]));
    expect(loadRecentDestinations()).toHaveLength(3);
  });
});
