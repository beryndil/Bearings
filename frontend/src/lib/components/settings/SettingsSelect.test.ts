/** Unit specs for SettingsSelect.
 *
 * Contract surface:
 *  - Renders one <option> per entry in `options`.
 *  - Selecting fires `onChange(next)` immediately (no debounce).
 *  - Surfaces saving / saved / error from the row indicator.
 */
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SettingsSelect from './SettingsSelect.svelte';

afterEach(cleanup);

describe('SettingsSelect', () => {
  it('renders one option per entry and reflects current value', () => {
    const { getByLabelText } = render(SettingsSelect, {
      props: {
        title: 'Theme',
        value: 'b',
        options: [
          { value: 'a', label: 'A' },
          { value: 'b', label: 'B' },
          { value: 'c', label: 'C' },
        ],
      },
    });
    const sel = getByLabelText('Theme') as HTMLSelectElement;
    expect(sel.value).toBe('b');
    expect(sel.options.length).toBe(3);
  });

  it('change fires onChange immediately (no debounce)', async () => {
    const onChange = vi.fn(async () => {});
    const { getByLabelText } = render(SettingsSelect, {
      props: {
        title: 'Theme',
        value: 'a',
        options: [
          { value: 'a', label: 'A' },
          { value: 'b', label: 'B' },
        ],
        onChange,
      },
    });
    const sel = getByLabelText('Theme') as HTMLSelectElement;
    await fireEvent.change(sel, { target: { value: 'b' } });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('b'));
  });
});
