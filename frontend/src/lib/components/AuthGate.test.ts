import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { auth } from '../stores/auth.svelte';
import AuthGate from './AuthGate.svelte';

afterEach(cleanup);

beforeEach(() => {
  // Reset the auth store singleton between cases. clearToken() puts
  // us in `required`; tests that want a different status bump it
  // explicitly.
  auth.clearToken();
});

describe('AuthGate', () => {
  it('renders nothing when the server reports auth disabled', () => {
    auth.status = 'open';
    const { queryByRole } = render(AuthGate);
    expect(queryByRole('heading', { name: 'Auth required' })).toBeNull();
  });

  it('shows the gate when status is `required`', () => {
    auth.status = 'required';
    const { getByRole, getByText } = render(AuthGate);
    expect(getByRole('heading', { name: 'Auth required' })).toBeInTheDocument();
    expect(getByText(/This server requires an auth token/i)).toBeInTheDocument();
  });

  it('shows a "rejected" hint when status is `invalid`', () => {
    auth.status = 'invalid';
    const { getByText } = render(AuthGate);
    expect(getByText(/stored token was rejected/i)).toBeInTheDocument();
  });

  it('submitting a token flips the store to `ok`', async () => {
    auth.status = 'required';
    const { getByLabelText, getByRole } = render(AuthGate);
    await fireEvent.input(getByLabelText('Token'), {
      target: { value: 'secret-sauce' }
    });
    await fireEvent.click(getByRole('button', { name: /Save/i }));
    expect(auth.status).toBe('ok');
    // jsdom exposes localStorage on `window`; Node 22+ also ships a
    // native bare `localStorage` global that conflicts, so go through
    // `window` to reach the one the app actually wrote to.
    expect(window.localStorage.getItem('twrminal:token')).toBe('secret-sauce');
  });

  it('ignores empty / whitespace-only token submissions', async () => {
    auth.status = 'required';
    const { getByLabelText, getByRole } = render(AuthGate);
    await fireEvent.input(getByLabelText('Token'), {
      target: { value: '   ' }
    });
    await fireEvent.click(getByRole('button', { name: /Save/i }));
    // Gate stays up — saveToken short-circuits on empty input.
    expect(auth.status).toBe('required');
  });
});
