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

/** Stub `fetch` for the PATCH the modal fires on Save. Returns the
 * spy so tests can assert the body that landed on the server. */
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
  it('pre-fills fields from current preferences when opened', () => {
    seedPreferences({
      display_name: 'Dave',
      default_model: 'claude-opus-4-7',
      default_working_dir: '/home/dave'
    });
    prefs.save({ authToken: 'existing-token' });
    const { getByLabelText } = render(Settings, { props: { open: true } });
    expect(getByLabelText('Display name')).toHaveValue('Dave');
    expect(getByLabelText('Default model')).toHaveValue('claude-opus-4-7');
    expect(getByLabelText('Default working dir')).toHaveValue('/home/dave');
    expect(getByLabelText('Auth token')).toHaveValue('existing-token');
  });

  it('Save fires PATCH with edited preference values and writes the auth token', async () => {
    const stub = stubPatchOk({
      display_name: 'Dave',
      theme: null,
      default_model: 'claude-sonnet-4-6',
      default_working_dir: '/tmp/work',
      notify_on_complete: false,
      updated_at: '2026-04-25T00:00:01+00:00'
    });
    const { getByLabelText, getByRole } = render(Settings, {
      props: { open: true }
    });
    await fireEvent.input(getByLabelText('Display name'), {
      target: { value: 'Dave' }
    });
    await fireEvent.input(getByLabelText('Default model'), {
      target: { value: 'claude-sonnet-4-6' }
    });
    await fireEvent.input(getByLabelText('Default working dir'), {
      target: { value: '/tmp/work' }
    });
    await fireEvent.input(getByLabelText('Auth token'), {
      target: { value: 'fresh-token' }
    });
    await fireEvent.click(getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(stub).toHaveBeenCalledTimes(1));
    const [, init] = stub.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe('PATCH');
    const body = JSON.parse(init.body as string);
    expect(body.display_name).toBe('Dave');
    expect(body.default_model).toBe('claude-sonnet-4-6');
    expect(body.default_working_dir).toBe('/tmp/work');
    expect(body.notify_on_complete).toBe(false);

    // Auth token persisted via the local prefs store. `onSave` runs
    // its `prefs.save` after `await preferences.update`; wait for the
    // microtask drain so the assertion sees the post-await state.
    await waitFor(() => expect(prefs.authToken).toBe('fresh-token'));
    // Server-backed fields landed via the response.
    expect(preferences.displayName).toBe('Dave');
    expect(preferences.defaultModel).toBe('claude-sonnet-4-6');
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
    const { getByLabelText, getByRole } = render(Settings, {
      props: { open: true }
    });
    await fireEvent.input(getByLabelText('Display name'), {
      target: { value: '   ' }
    });
    await fireEvent.click(getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(stub).toHaveBeenCalledTimes(1));
    const [, init] = stub.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.display_name).toBeNull();
  });

  it('Cancel does not fire a PATCH', async () => {
    const stub = stubPatchOk({});
    const { getByLabelText, getByRole } = render(Settings, {
      props: { open: true }
    });
    await fireEvent.input(getByLabelText('Default model'), {
      target: { value: 'edited' }
    });
    await fireEvent.click(getByRole('button', { name: 'Cancel' }));
    expect(stub).not.toHaveBeenCalled();
  });
});
