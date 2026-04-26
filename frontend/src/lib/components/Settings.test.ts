import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { prefs } from '../stores/prefs.svelte';
import { preferences } from '../stores/preferences.svelte';
import Settings from './Settings.svelte';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/** Replace the in-memory preferences row directly. The store normally
 * hydrates via `init()` against `/api/preferences`; tests bypass that
 * and write the row so the modal pre-fills from a known shape. */
function seedPreferences(over: Record<string, unknown>): void {
  const row = (preferences as unknown as { row: Record<string, unknown> }).row;
  row.display_name = null;
  row.theme = null;
  row.default_model = null;
  row.default_working_dir = null;
  row.notify_on_complete = false;
  row.updated_at = '2026-04-25T00:00:00+00:00';
  Object.assign(row, over);
}

/** Stub `fetch` for the PATCH the dialog fires on autosave. Returns
 * the spy so tests can assert the body that landed on the server. */
function stubPatchOk(response: Record<string, unknown>): ReturnType<typeof vi.fn> {
  const stub = vi.fn(async () => ({
    ok: true,
    status: 200,
    async json() {
      return response;
    },
    async text() {
      return JSON.stringify(response);
    }
  }));
  vi.stubGlobal('fetch', stub);
  return stub;
}

beforeEach(() => {
  // Reset both stores to a known shape per test.
  prefs.save({ authToken: '' });
  seedPreferences({});
});

describe('Settings', () => {
  it('opens onto the Profile section by default', () => {
    seedPreferences({ display_name: 'Dave' });
    const { getByLabelText, getByTestId } = render(Settings, {
      props: { open: true }
    });
    // Profile section is the lowest-weight entry in the registry, so
    // it's the active pane on open.
    expect(getByTestId('settings-section-profile')).toBeInTheDocument();
    expect(getByLabelText('Display name')).toHaveValue('Dave');
  });

  it('autosaves Display name after the debounce window', async () => {
    const stub = stubPatchOk({
      display_name: 'Dave',
      theme: null,
      default_model: null,
      default_working_dir: null,
      notify_on_complete: false,
      updated_at: '2026-04-25T00:00:01+00:00'
    });
    const { getByLabelText } = render(Settings, { props: { open: true } });

    await fireEvent.input(getByLabelText('Display name'), {
      target: { value: 'Dave' }
    });

    // 400ms debounce in SettingsTextField — `waitFor` polls until
    // the spy has fired or the default 1s timeout trips.
    await waitFor(() => expect(stub).toHaveBeenCalledTimes(1));
    const [, init] = stub.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe('PATCH');
    const body = JSON.parse(init.body as string);
    expect(body.display_name).toBe('Dave');
    await waitFor(() => expect(preferences.displayName).toBe('Dave'));
  });

  it('blank Display name lands on the wire as null', async () => {
    seedPreferences({ display_name: 'Dave' });
    const stub = stubPatchOk({
      display_name: null,
      theme: null,
      default_model: null,
      default_working_dir: null,
      notify_on_complete: false,
      updated_at: '2026-04-25T00:00:02+00:00'
    });
    const { getByLabelText } = render(Settings, { props: { open: true } });

    await fireEvent.input(getByLabelText('Display name'), {
      target: { value: '   ' }
    });

    await waitFor(() => expect(stub).toHaveBeenCalledTimes(1));
    const [, init] = stub.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.display_name).toBeNull();
  });

  it('navigating to Defaults shows the model + working dir fields seeded from the store', async () => {
    seedPreferences({
      default_model: 'claude-opus-4-7',
      default_working_dir: '/home/dave'
    });
    const { getByLabelText, getByTestId } = render(Settings, {
      props: { open: true }
    });

    await fireEvent.click(getByTestId('settings-rail-defaults'));

    expect(getByTestId('settings-section-defaults')).toBeInTheDocument();
    expect(getByLabelText('Default model')).toHaveValue('claude-opus-4-7');
    expect(getByLabelText('Default working directory')).toHaveValue('/home/dave');
  });

  it('Authentication section writes the token to localStorage and not /api/preferences', async () => {
    const stub = stubPatchOk({});
    const { getByLabelText, getByTestId } = render(Settings, {
      props: { open: true }
    });

    await fireEvent.click(getByTestId('settings-rail-auth'));

    await fireEvent.input(getByLabelText('Auth token'), {
      target: { value: 'fresh-token' }
    });

    // Wait past the debounce so the assertion isn't racing the timer.
    await waitFor(() => expect(prefs.authToken).toBe('fresh-token'));
    expect(stub).not.toHaveBeenCalled();
  });
});
