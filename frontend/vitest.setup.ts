import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';

// Node 22+ ships a native `localStorage` global that is non-functional
// unless `--localstorage-file` was given a valid path. Under vitest +
// jsdom that native binding shadows jsdom's Storage, so setItem /
// getItem throw TypeError. Replace both the Node-global and the
// window property with a Map-backed shim.
class MemoryStorage {
  private store = new Map<string, string>();
  get length(): number {
    return this.store.size;
  }
  clear(): void {
    this.store.clear();
  }
  getItem(key: string): string | null {
    return this.store.has(key) ? (this.store.get(key) as string) : null;
  }
  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

const storage = new MemoryStorage();
Object.defineProperty(globalThis, 'localStorage', {
  value: storage,
  writable: true,
  configurable: true
});
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'localStorage', {
    value: storage,
    writable: true,
    configurable: true
  });
}

afterEach(() => {
  storage.clear();
});
