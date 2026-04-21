import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { prefs } from '../stores/prefs.svelte';
import Settings from './Settings.svelte';

afterEach(cleanup);

beforeEach(() => {
  // Fresh prefs per test — prefs is a module singleton backed by
  // localStorage, which jsdom resets per test file but not per case.
  prefs.save({
    defaultModel: '',
    defaultWorkingDir: '',
    authToken: '',
    notifyOnComplete: false
  });
});

describe('Settings', () => {
  it('pre-fills fields from current prefs when opened', () => {
    prefs.save({
      defaultModel: 'claude-opus-4-7',
      defaultWorkingDir: '/home/dave',
      authToken: 'existing-token',
      notifyOnComplete: false
    });
    const { getByLabelText } = render(Settings, { props: { open: true } });
    expect(getByLabelText('Default model')).toHaveValue('claude-opus-4-7');
    expect(getByLabelText('Default working dir')).toHaveValue('/home/dave');
    expect(getByLabelText('Auth token')).toHaveValue('existing-token');
  });

  it('Save button writes field values into the prefs store', async () => {
    const { getByLabelText, getByRole } = render(Settings, {
      props: { open: true }
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

    expect(prefs.defaultModel).toBe('claude-sonnet-4-6');
    expect(prefs.defaultWorkingDir).toBe('/tmp/work');
    expect(prefs.authToken).toBe('fresh-token');
    expect(prefs.notifyOnComplete).toBe(false);
  });

  it('Cancel leaves the prefs store untouched', async () => {
    prefs.save({
      defaultModel: 'existing-model',
      defaultWorkingDir: '/existing',
      authToken: 'keep',
      notifyOnComplete: false
    });
    const { getByLabelText, getByRole } = render(Settings, {
      props: { open: true }
    });
    await fireEvent.input(getByLabelText('Default model'), {
      target: { value: 'new-model' }
    });
    await fireEvent.click(getByRole('button', { name: 'Cancel' }));

    expect(prefs.defaultModel).toBe('existing-model');
    expect(prefs.defaultWorkingDir).toBe('/existing');
    expect(prefs.authToken).toBe('keep');
  });
});
