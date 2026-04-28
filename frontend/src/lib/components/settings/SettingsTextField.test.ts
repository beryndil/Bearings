/** Unit specs for SettingsTextField.
 *
 * Contract surface:
 *  - Two-way binds value via input event.
 *  - Fires `onChange(next)` 400ms after the last keystroke (debounced).
 *  - Synchronous `validate(value)` blocks the save and renders the
 *    error message inline in red.
 *  - Char counter appears once value length crosses 80% of `maxlength`.
 *  - `password` flips input type to 'password' and adds
 *    `autocomplete="off"`.
 *  - Surfaces saving / saved / error from the row indicator.
 */
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SettingsTextField from './SettingsTextField.svelte';

afterEach(cleanup);

describe('SettingsTextField', () => {
  it('debounces onChange by 400ms after the last keystroke', async () => {
    const onChange = vi.fn(async () => {});
    const { getByLabelText } = render(SettingsTextField, {
      props: { title: 'Display name', value: '', onChange },
    });
    const input = getByLabelText('Display name');
    await fireEvent.input(input, { target: { value: 'D' } });
    await fireEvent.input(input, { target: { value: 'Da' } });
    await fireEvent.input(input, { target: { value: 'Dav' } });
    await fireEvent.input(input, { target: { value: 'Dave' } });
    // After the debounce, exactly one PATCH lands with the final value.
    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1));
    expect(onChange).toHaveBeenCalledWith('Dave');
  });

  it('blocks the save when validate returns a non-null message', async () => {
    const onChange = vi.fn(async () => {});
    const { getByLabelText, findByRole } = render(SettingsTextField, {
      props: {
        title: 'Field',
        value: '',
        onChange,
        validate: (v: string) => (v.includes(' ') ? 'no spaces allowed' : null),
      },
    });
    await fireEvent.input(getByLabelText('Field'), {
      target: { value: 'a b' },
    });
    const alert = await findByRole('alert');
    expect(alert).toHaveTextContent('no spaces allowed');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('shows the char counter past 80% of maxlength', async () => {
    const { getByLabelText, queryByText } = render(SettingsTextField, {
      props: { title: 'Field', value: '', maxlength: 10 },
    });
    const input = getByLabelText('Field');

    // 7 chars = 70% — no counter.
    await fireEvent.input(input, { target: { value: 'abcdefg' } });
    expect(queryByText(/^\d+\/10$/)).toBeNull();

    // 9 chars = 90% — counter appears.
    await fireEvent.input(input, { target: { value: 'abcdefghi' } });
    await waitFor(() => expect(queryByText('9/10')).not.toBeNull());
  });

  it('password mode masks the input and disables autocomplete', () => {
    const { getByLabelText } = render(SettingsTextField, {
      props: { title: 'Token', value: 'secret', password: true },
    });
    const input = getByLabelText('Token') as HTMLInputElement;
    expect(input.type).toBe('password');
    expect(input.getAttribute('autocomplete')).toBe('off');
  });
});
