/**
 * Vitest setup file — runs before every test file.
 *
 * - Loads `@testing-library/jest-dom` so component tests can use
 *   matchers like `toBeInTheDocument()`, `toHaveClass()` etc.
 * - Installs an in-memory `localStorage` polyfill — jsdom does not
 *   wire one up by default in our vitest config, and the theme
 *   provider (item 2.9) needs synchronous reads + writes for the
 *   no-flash boot path. The polyfill is reset between tests via the
 *   per-file `beforeEach(window.localStorage.clear())`.
 */
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach } from "vitest";

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
    const keys = Array.from(this.store.keys());
    return keys[index] ?? null;
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }
}

// Install on every test that needs it. ``Object.defineProperty`` is the
// only way to override jsdom's read-only ``window.localStorage`` slot.
function installMemoryStorage(): void {
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    writable: false,
    value: new MemoryStorage(),
  });
}

beforeEach(() => {
  installMemoryStorage();
});

afterEach(() => {
  // Reset between tests so a leaked write from one test doesn't bleed
  // into the next. Using a fresh polyfill is simpler than calling
  // ``clear()`` on the existing one — fresh covers ``Storage.prototype``
  // mocks that some tests install per-test.
  installMemoryStorage();
});
