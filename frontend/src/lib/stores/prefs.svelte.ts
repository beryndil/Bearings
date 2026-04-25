/** Client-only preferences. Auth token deliberately stays here —
 * the server can't authorize itself on its own stored token, so the
 * bearer that gates `/api/preferences` itself has to live in
 * localStorage. Every other preference moved to the server-backed
 * `preferences` store (migration 0026, commit `2871877`). */

const TOKEN_KEY = 'bearings:token';

function readStorage(key: string): string | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null): void {
  if (typeof localStorage === 'undefined') return;
  try {
    if (value === null || value === '') localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Quota/privacy-mode: defaults don't persist, but the UI keeps
    // working for this session.
  }
}

class PrefsStore {
  authToken = $state(readStorage(TOKEN_KEY) ?? '');

  save(values: { authToken: string }): void {
    this.authToken = values.authToken.trim();
    writeStorage(TOKEN_KEY, this.authToken || null);
  }
}

export const prefs = new PrefsStore();
