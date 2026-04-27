/**
 * Vitest stub for `$app/navigation`. SvelteKit's real module is
 * synthesized at build time and isn't available in plain vitest. The
 * production code imports `goto` to drive deep-linked navigation; in
 * tests we expose a spy-friendly mock so component tests can assert
 * `goto` was called with the expected URL.
 *
 * Aliased in vitest.config.ts. Tests that want call-history can do:
 *
 *     import { goto } from '$app/navigation';
 *     import { vi } from 'vitest';
 *     const gotoSpy = vi.mocked(goto);
 *     gotoSpy.mockClear();
 *     // ... interact ...
 *     expect(gotoSpy).toHaveBeenCalledWith('/sessions/abc');
 */
import { vi } from 'vitest';

export const goto = vi.fn(async (_url: string | URL, _opts?: unknown) => {
  // No-op resolver. Tests can override with mockImplementation if they
  // need the goto promise to do something specific.
});

export const invalidate = vi.fn(async (_dep?: string) => {});
export const invalidateAll = vi.fn(async () => {});
export const preloadCode = vi.fn(async (..._urls: string[]) => {});
export const preloadData = vi.fn(async (_url: string) => undefined);
export const beforeNavigate = vi.fn();
export const afterNavigate = vi.fn();
export const onNavigate = vi.fn();
export const disableScrollHandling = vi.fn();
export const pushState = vi.fn();
export const replaceState = vi.fn();
