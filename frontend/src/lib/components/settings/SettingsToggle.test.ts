/** Unit specs for SettingsToggle.
 *
 * Contract surface:
 *  - Renders a switch widget with the given title; aria-checked
 *    matches `checked` prop.
 *  - Fires `onChange(next)` when the user activates the control.
 *  - Surfaces `Saving…` / `Saved` / `Error` states from the row's
 *    indicator while the async hook resolves.
 *  - Rolls back the local flip if `onChange` throws (the 'permission
 *    denied' carve-out for Notifications relies on this).
 */
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SettingsToggle from './SettingsToggle.svelte';

afterEach(cleanup);

describe('SettingsToggle', () => {
  it('renders the title and reflects checked state via aria-checked', () => {
    const { getByRole } = render(SettingsToggle, {
      props: { title: 'Notify on complete', checked: true }
    });
    const sw = getByRole('switch');
    expect(sw).toHaveAttribute('aria-checked', 'true');
    expect(sw).toHaveAttribute('aria-label', 'Notify on complete');
  });

  it('clicking the switch fires onChange with the next value', async () => {
    const onChange = vi.fn(async () => {});
    const { getByRole } = render(SettingsToggle, {
      props: { title: 'Toggle', checked: false, onChange }
    });
    await fireEvent.click(getByRole('switch'));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(true));
  });

  it('surfaces Saved after a successful onChange', async () => {
    const onChange = vi.fn(async () => {});
    const { getByRole, findByText } = render(SettingsToggle, {
      props: { title: 'Toggle', checked: false, onChange }
    });
    await fireEvent.click(getByRole('switch'));
    await findByText('Saved');
  });

  it('rolls back the flip and surfaces Error when onChange throws', async () => {
    const onChange = vi.fn(async () => {
      throw new Error('denied');
    });
    const { getByRole, findByText } = render(SettingsToggle, {
      props: { title: 'Toggle', checked: false, onChange }
    });
    const sw = getByRole('switch');
    await fireEvent.click(sw);
    await findByText('Error');
    // Rolled back — aria-checked is still false.
    expect(sw).toHaveAttribute('aria-checked', 'false');
  });

  it('disabled toggle does not fire onChange', async () => {
    const onChange = vi.fn(async () => {});
    const { getByRole } = render(SettingsToggle, {
      props: { title: 'Toggle', checked: false, disabled: true, onChange }
    });
    await fireEvent.click(getByRole('switch'));
    expect(onChange).not.toHaveBeenCalled();
  });
});
