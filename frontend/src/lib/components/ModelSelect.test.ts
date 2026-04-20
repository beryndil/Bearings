import { afterEach, describe, expect, test } from 'vitest';
import { cleanup, fireEvent, render } from '@testing-library/svelte';

import { KNOWN_MODELS } from '$lib/models';
import ModelSelect from './ModelSelect.svelte';

afterEach(() => cleanup());

describe('ModelSelect', () => {
  test('renders all known models plus Custom in the dropdown', () => {
    const { getByRole } = render(ModelSelect, { value: '' });
    const select = getByRole('combobox', { name: 'Model' }) as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toEqual(['', ...KNOWN_MODELS, '__custom__']);
  });

  test('known value surfaces as the selected option, no custom input', () => {
    const { getByRole, queryByLabelText } = render(ModelSelect, {
      value: 'claude-opus-4-7'
    });
    const select = getByRole('combobox', { name: 'Model' }) as HTMLSelectElement;
    expect(select.value).toBe('claude-opus-4-7');
    expect(queryByLabelText('Custom model id')).toBeNull();
  });

  test('unknown value lands in Custom mode with the input visible', () => {
    const { getByRole, getByLabelText } = render(ModelSelect, {
      value: 'claude-sonnet-5-0-preview-20280101'
    });
    const select = getByRole('combobox', { name: 'Model' }) as HTMLSelectElement;
    expect(select.value).toBe('__custom__');
    const custom = getByLabelText('Custom model id') as HTMLInputElement;
    expect(custom.value).toBe('claude-sonnet-5-0-preview-20280101');
  });

  test('picking Custom from the dropdown clears value and reveals input', async () => {
    const { getByRole, getByLabelText } = render(ModelSelect, {
      value: 'claude-opus-4-7'
    });
    const select = getByRole('combobox', { name: 'Model' }) as HTMLSelectElement;
    await fireEvent.change(select, { target: { value: '__custom__' } });
    const custom = getByLabelText('Custom model id') as HTMLInputElement;
    expect(custom.value).toBe('');
  });
});
