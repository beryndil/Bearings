import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import CheatSheet from './CheatSheet.svelte';

afterEach(cleanup);

describe('CheatSheet', () => {
  it('renders nothing when open=false', () => {
    const { queryByRole } = render(CheatSheet, { props: { open: false } });
    expect(queryByRole('heading', { name: 'Shortcuts' })).toBeNull();
  });

  it('renders the shortcut list when open=true', () => {
    const { getByRole, getByText } = render(CheatSheet, { props: { open: true } });
    expect(getByRole('heading', { name: 'Shortcuts' })).toBeInTheDocument();
    expect(getByText('Focus the sidebar search')).toBeInTheDocument();
    expect(getByText('Send the prompt')).toBeInTheDocument();
  });

  it('exposes a close button when open', async () => {
    const { getByRole } = render(CheatSheet, { props: { open: true } });
    const close = getByRole('button', { name: 'Close cheat sheet' });
    // Click doesn't error (the bind update happens on the parent side;
    // we're only exercising the event dispatch).
    await fireEvent.click(close);
  });
});
