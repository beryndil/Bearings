import { describe, expect, it } from 'vitest';

import { parseBudget } from './budget';

describe('parseBudget', () => {
  it('returns null for null / undefined / empty / whitespace', () => {
    expect(parseBudget(null)).toBeNull();
    expect(parseBudget(undefined)).toBeNull();
    expect(parseBudget('')).toBeNull();
  });

  it('parses positive finite numbers', () => {
    expect(parseBudget(1)).toBe(1);
    expect(parseBudget(0.25)).toBe(0.25);
    expect(parseBudget('1.25')).toBe(1.25);
    expect(parseBudget('  2.00  ')).toBe(2);
  });

  it('returns null for zero and negatives', () => {
    expect(parseBudget(0)).toBeNull();
    expect(parseBudget('0')).toBeNull();
    expect(parseBudget(-1)).toBeNull();
    expect(parseBudget('-3.5')).toBeNull();
  });

  it('returns null for non-finite and non-numeric strings', () => {
    expect(parseBudget(Number.NaN)).toBeNull();
    expect(parseBudget(Number.POSITIVE_INFINITY)).toBeNull();
    expect(parseBudget('abc')).toBeNull();
    expect(parseBudget('1.2.3')).toBeNull();
  });
});
