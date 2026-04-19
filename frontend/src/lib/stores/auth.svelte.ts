import * as api from '$lib/api';

const TOKEN_KEY = 'twrminal:token';

export type AuthStatus =
  | 'checking' // fetching /api/health
  | 'open' // server reports auth disabled — nothing required
  | 'ok' // required and stored token currently works
  | 'required' // required and no token stored
  | 'invalid' // required but stored token was rejected (401/4401)
  | 'error'; // /api/health itself failed

function readToken(): string | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeToken(value: string | null): void {
  if (typeof localStorage === 'undefined') return;
  try {
    if (value === null) localStorage.removeItem(TOKEN_KEY);
    else localStorage.setItem(TOKEN_KEY, value);
  } catch {
    // Quota/private-mode — token won't persist across reloads; UI still
    // works for this session.
  }
}

class AuthStore {
  status = $state<AuthStatus>('checking');
  errorMessage = $state<string | null>(null);

  hasToken = $derived(readToken() !== null);
  blocking = $derived(this.status === 'required' || this.status === 'invalid');

  constructor() {
    api.onAuthFailure(() => this.markInvalid());
  }

  async check(): Promise<void> {
    this.status = 'checking';
    this.errorMessage = null;
    try {
      const health = await api.fetchHealth();
      if (health.auth !== 'required') {
        this.status = 'open';
        return;
      }
      // Server requires auth. If we have a token, assume it works until
      // an API call proves otherwise — markInvalid() flips us to
      // `invalid` if a 401 / 4401 comes back.
      this.status = readToken() ? 'ok' : 'required';
    } catch (e) {
      this.status = 'error';
      this.errorMessage = e instanceof Error ? e.message : String(e);
    }
  }

  /** Called when a 401 or WS 4401 was observed — the stored token was
   * rejected. Re-opens the gate so the user can supply a new one. */
  markInvalid(): void {
    if (this.status === 'open') return; // server doesn't require auth
    writeToken(null);
    this.status = 'invalid';
  }

  saveToken(value: string): void {
    const trimmed = value.trim();
    if (!trimmed) return;
    writeToken(trimmed);
    this.status = 'ok';
  }

  clearToken(): void {
    writeToken(null);
    this.status = 'required';
  }
}

export const auth = new AuthStore();
