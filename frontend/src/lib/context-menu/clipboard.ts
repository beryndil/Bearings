/**
 * Isolated clipboard helper for context-menu actions.
 *
 * The spec's Gotcha §"Copy actions must always work" calls out copy as
 * the one thing that must never silently fail — a failed copy is the
 * worst UX bug possible because it breaks user trust. This helper is
 * deliberately decoupled from the rest of the app's state so a copy
 * action can succeed even if the backend, store, or agent is wedged.
 *
 * Strategy:
 *   1. Prefer the async Clipboard API — the modern path.
 *   2. Fall back to a synthetic <textarea> + `execCommand('copy')` for
 *      older browsers, permission-denied states, and insecure origins.
 *   3. If both paths throw, rethrow so the caller can surface a toast.
 *      Silent failures are explicitly forbidden.
 */

export async function writeClipboard(text: string): Promise<void> {
  // Path 1: async Clipboard API. Available on https and localhost.
  try {
    if (
      typeof navigator !== 'undefined' &&
      navigator.clipboard &&
      typeof navigator.clipboard.writeText === 'function'
    ) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    // Fall through to the execCommand path. Do not swallow the
    // final failure below — the caller needs to know.
  }

  // Path 2: execCommand fallback. Deprecated but universally present.
  if (typeof document === 'undefined') {
    throw new Error('clipboard unavailable: no document');
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.position = 'fixed';
  ta.style.top = '-1000px';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try {
    const ok = document.execCommand('copy');
    if (!ok) throw new Error('execCommand("copy") returned false');
  } finally {
    ta.remove();
  }
}
