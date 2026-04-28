import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import TokenMeter from './TokenMeter.svelte';

afterEach(cleanup);

describe('TokenMeter', () => {
  it('renders an em-dash placeholder while totals are null', () => {
    const { getByLabelText } = render(TokenMeter, {
      props: { totals: null },
    });
    expect(getByLabelText('Loading token totals').textContent).toBe('—');
  });

  it('renders the three-figure summary for populated totals', () => {
    const { getByLabelText } = render(TokenMeter, {
      props: {
        totals: {
          input_tokens: 12_300,
          output_tokens: 4_560,
          cache_read_tokens: 80_000,
          cache_creation_tokens: 20_000,
        },
      },
    });
    // Input/output use k suffix; cache is the sum (80k + 20k = 100k).
    const text = getByLabelText('Token usage summary').textContent ?? '';
    expect(text).toContain('12.3k in');
    expect(text).toContain('4.6k out');
    // 100k rounds with one decimal under 100, zero at 100+: expect 100k.
    expect(text).toContain('100k cache');
  });

  it('uses M suffix past a million', () => {
    const { getByLabelText } = render(TokenMeter, {
      props: {
        totals: {
          input_tokens: 1_200_000,
          output_tokens: 0,
          cache_read_tokens: 0,
          cache_creation_tokens: 0,
        },
      },
    });
    const text = getByLabelText('Token usage summary').textContent ?? '';
    expect(text).toContain('1.2M in');
  });

  it('renders plain 0 for a brand-new session', () => {
    const { getByLabelText } = render(TokenMeter, {
      props: {
        totals: {
          input_tokens: 0,
          output_tokens: 0,
          cache_read_tokens: 0,
          cache_creation_tokens: 0,
        },
      },
    });
    const text = getByLabelText('Token usage summary').textContent ?? '';
    // All three slots read "0" with no k/M suffix.
    expect(text).toContain('0 in');
    expect(text).toContain('0 out');
    expect(text).toContain('0 cache');
  });

  it('compact mode drops the labels so three numbers fit on a card', () => {
    const { getByLabelText } = render(TokenMeter, {
      props: {
        totals: {
          input_tokens: 1_000,
          output_tokens: 2_000,
          cache_read_tokens: 500,
          cache_creation_tokens: 500,
        },
        compact: true,
      },
    });
    const text = getByLabelText('Token usage summary').textContent ?? '';
    expect(text).not.toContain('in');
    expect(text).not.toContain('out');
    expect(text).toContain('/');
  });
});
