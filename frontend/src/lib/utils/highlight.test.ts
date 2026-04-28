import { describe, expect, it } from 'vitest';

import { highlightText } from './highlight';

describe('highlightText', () => {
  it('returns escaped text unchanged when the query is empty', () => {
    expect(highlightText('hello <world>', '')).toBe('hello &lt;world&gt;');
  });

  it('wraps a case-insensitive match in <mark>', () => {
    expect(highlightText('Find the Fish', 'fish')).toBe('Find the <mark>Fish</mark>');
  });

  it('wraps every occurrence', () => {
    expect(highlightText('ab ab AB', 'ab')).toBe('<mark>ab</mark> <mark>ab</mark> <mark>AB</mark>');
  });

  it('escapes HTML in the source before inserting marks', () => {
    const out = highlightText('<script>alert("x")</script>', 'alert');
    expect(out).not.toContain('<script>');
    expect(out).toContain('<mark>alert</mark>');
    expect(out).toContain('&lt;script&gt;');
  });

  it('treats regex metacharacters in the query as literals', () => {
    expect(highlightText('match a.b.c here', 'a.b.c')).toBe('match <mark>a.b.c</mark> here');
    // Without escaping this would match anything-anything-anything.
    expect(highlightText('match abc here', 'a.b.c')).toBe('match abc here');
  });

  it('returns escaped source when there is no match', () => {
    expect(highlightText('nothing to see', 'xyz')).toBe('nothing to see');
  });
});
