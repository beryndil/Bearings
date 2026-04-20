import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';

import FolderPicker from './FolderPicker.svelte';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const HOME_LIST = {
  path: '/home/dave',
  parent: '/home',
  entries: [
    { name: 'Projects', path: '/home/dave/Projects' },
    { name: 'docs', path: '/home/dave/docs' }
  ]
};

const PROJECTS_LIST = {
  path: '/home/dave/Projects',
  parent: '/home/dave',
  entries: [
    { name: 'Twrminal', path: '/home/dave/Projects/Twrminal' }
  ]
};

function mockFetch(map: Record<string, unknown>) {
  return vi.fn(async (url: string) => {
    for (const [needle, body] of Object.entries(map)) {
      if (url.includes(needle))
        return new Response(JSON.stringify(body), { status: 200 });
    }
    // Default: treat as "list $HOME" when no path param is given.
    if (!url.includes('path=')) {
      return new Response(JSON.stringify(HOME_LIST), { status: 200 });
    }
    return new Response('not found', { status: 404 });
  });
}

describe('FolderPicker', () => {
  beforeEach(() => {
    // jsdom lacks a default global fetch — install a stub each test.
    // `listDir` uses the global `fetch` via its default fetchImpl.
  });

  it('renders a text field bound to value', () => {
    const { getByLabelText } = render(FolderPicker, { value: '/home/dave' });
    const input = getByLabelText('Folder path') as HTMLInputElement;
    expect(input.value).toBe('/home/dave');
  });

  it('Browse button opens the picker and fetches the current value', async () => {
    const fetchSpy = mockFetch({
      'path=%2Fhome%2Fdave': HOME_LIST
    });
    vi.stubGlobal('fetch', fetchSpy);
    const { getByText, findByText } = render(FolderPicker, {
      value: '/home/dave'
    });
    await fireEvent.click(getByText('Browse'));
    // Waits for the fetch to resolve and the first entry to render.
    await findByText('Projects');
    expect(fetchSpy).toHaveBeenCalled();
  });

  it('descending into a subdirectory refetches and updates breadcrumb', async () => {
    const fetchSpy = mockFetch({
      'path=%2Fhome%2Fdave%2FProjects': PROJECTS_LIST,
      'path=%2Fhome%2Fdave': HOME_LIST
    });
    vi.stubGlobal('fetch', fetchSpy);
    const { getByText, findByText } = render(FolderPicker, {
      value: '/home/dave'
    });
    await fireEvent.click(getByText('Browse'));
    await findByText('Projects');
    await fireEvent.click(getByText('Projects'));
    await findByText('Twrminal');
    // Breadcrumb now includes the descended segment.
    expect(getByText('Projects')).toBeDefined();
  });

  it('"Use this folder" writes currentPath back to value and closes', async () => {
    const fetchSpy = mockFetch({
      'path=%2Fhome%2Fdave%2FProjects': PROJECTS_LIST
    });
    vi.stubGlobal('fetch', fetchSpy);
    const { getByText, getByLabelText, findByText, queryByText } = render(
      FolderPicker,
      { value: '/home/dave/Projects' }
    );
    await fireEvent.click(getByText('Browse'));
    await findByText('Twrminal');
    await fireEvent.click(getByText('Use this folder'));
    await waitFor(() => expect(queryByText('Use this folder')).toBeNull());
    const input = getByLabelText('Folder path') as HTMLInputElement;
    expect(input.value).toBe('/home/dave/Projects');
  });

  it('surfaces fetch errors inline without clobbering the input', async () => {
    const fetchSpy = vi.fn(
      async () => new Response('not found', { status: 404 })
    );
    vi.stubGlobal('fetch', fetchSpy);
    const { getByText, findByText, getByLabelText } = render(FolderPicker, {
      value: '/nope'
    });
    await fireEvent.click(getByText('Browse'));
    await findByText(/not found|404/);
    const input = getByLabelText('Folder path') as HTMLInputElement;
    expect(input.value).toBe('/nope');
  });
});
