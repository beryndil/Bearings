/**
 * Vitest stub for `$app/stores`. Mirrors the surface SvelteKit
 * synthesizes at build time so component tests can import `page`
 * without bringing in the real SvelteKit runtime.
 *
 * The `page` store carries URL + route info; tests that need a
 * specific URL can do:
 *
 *     import { setStubPage } from 'src/test-stubs/app/stores';
 *     setStubPage({ url: new URL('http://localhost/?session=abc') });
 *
 * Default value is a benign localhost root URL with empty params /
 * route, which is sufficient for components that only read the page
 * store defensively.
 */
import { writable, type Readable } from 'svelte/store';

type StubPage = {
  url: URL;
  params: Record<string, string>;
  route: { id: string | null };
  status: number;
  error: Error | null;
  data: Record<string, unknown>;
  form: Record<string, unknown> | null;
  state: Record<string, unknown>;
};

const initial: StubPage = {
  url: new URL('http://localhost/'),
  params: {},
  route: { id: null },
  status: 200,
  error: null,
  data: {},
  form: null,
  state: {}
};

const _page = writable<StubPage>(initial);

export const page: Readable<StubPage> = {
  subscribe: _page.subscribe
};

export const navigating = writable<null>(null);
export const updated = writable(false);

export function setStubPage(patch: Partial<StubPage>): void {
  _page.update((curr) => ({ ...curr, ...patch }));
}

export function resetStubPage(): void {
  _page.set(initial);
}
