/** Unit specs for SettingsLink.
 *
 * Contract surface:
 *  - `href` mode renders an <a target=_blank rel=noopener noreferrer>.
 *  - `onClick` mode renders a <button> that fires the handler.
 *  - `trailing` (no href, no onClick) renders the text as a plain
 *    span — used for non-interactive value displays (the About
 *    section's Version + Build rows).
 */
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SettingsLink from './SettingsLink.svelte';

afterEach(cleanup);

describe('SettingsLink', () => {
  it('href mode renders an external <a> with rel=noopener', () => {
    const { getByTestId } = render(SettingsLink, {
      props: {
        title: 'Repo',
        href: 'https://github.com/Beryndil/Bearings'
      }
    });
    const a = getByTestId('settings-link') as HTMLAnchorElement;
    expect(a.tagName).toBe('A');
    expect(a.target).toBe('_blank');
    expect(a.rel).toContain('noopener');
    expect(a.href).toBe('https://github.com/Beryndil/Bearings');
  });

  it('onClick mode renders a button and fires the handler', async () => {
    const onClick = vi.fn(async () => {});
    const { getByTestId } = render(SettingsLink, {
      props: { title: 'Test', onClick, trailing: 'Run' }
    });
    const btn = getByTestId('settings-link') as HTMLButtonElement;
    expect(btn.tagName).toBe('BUTTON');
    await fireEvent.click(btn);
    await waitFor(() => expect(onClick).toHaveBeenCalledTimes(1));
  });

  it('trailing-only mode renders a plain span (used for value displays)', () => {
    const { queryByTestId, getByText } = render(SettingsLink, {
      props: { title: 'Version', trailing: 'v0.20.5' }
    });
    expect(queryByTestId('settings-link')).toBeNull();
    expect(getByText('v0.20.5')).toBeInTheDocument();
  });
});
