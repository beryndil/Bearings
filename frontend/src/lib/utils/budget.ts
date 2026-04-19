/**
 * Normalise user input for the "max budget USD" field. The
 * `<input type="number">` binding can hand us a number, empty
 * string, or null depending on the browser + Svelte 5 behavior —
 * this helper collapses all three into a single shape:
 *
 *   - null / undefined / empty / whitespace → null (no cap)
 *   - non-finite (NaN / Infinity) → null (invalid)
 *   - zero or negative → null (no cap)
 *   - finite positive → the number
 */
export function parseBudget(raw: unknown): number | null {
  if (raw === null || raw === undefined || raw === '') return null;
  const n = typeof raw === 'number' ? raw : Number(String(raw).trim());
  return Number.isFinite(n) && n > 0 ? n : null;
}
