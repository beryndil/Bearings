/** Display-only settings: locale + timezone overrides for the
 * formatters in `$lib/utils/datetime.ts`. Both nullable; `null`
 * means "use the browser default" (i.e. `Intl.DateTimeFormat`'s
 * resolved value when called with `undefined`).
 *
 * Storage is localStorage-only by design. Per-device preference
 * matches the user's mental model — laptop in CT, desktop in UTC,
 * phone abroad — and avoids the migration / DTO / endpoint
 * surface that a server-synced timezone would require. If
 * cross-device sync ever becomes desirable, the server-backed
 * `preferences` store (migration 0026) is where it would land,
 * and the localStorage values can be promoted cleanly.
 *
 * The class mirrors the shape of `prefs.svelte.ts` (which stays
 * localStorage-only for the same auth-scoped reason): `$state` for
 * reactive read access, `set*` methods that write through to
 * localStorage, defensive try/catch so a broken or quota-exhausted
 * localStorage doesn't crash rendering. */

const LOCALE_KEY = 'bearings:display:locale';
const TIMEZONE_KEY = 'bearings:display:timezone';

function readStorage(key: string): string | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    const v = localStorage.getItem(key);
    return v === null || v === '' ? null : v;
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
    // Quota / privacy mode — defaults don't persist but the UI keeps
    // working for this session.
  }
}

class DisplaySettingsStore {
  /** IETF BCP 47 locale tag (e.g. `'en-US'`, `'ja-JP'`) or null for
   * browser default. */
  locale = $state<string | null>(readStorage(LOCALE_KEY));

  /** IANA timezone name (e.g. `'America/New_York'`, `'UTC'`,
   * `'Asia/Tokyo'`) or null for browser default. */
  timezone = $state<string | null>(readStorage(TIMEZONE_KEY));

  setLocale(value: string | null): void {
    const v = value === null || value === '' ? null : value;
    this.locale = v;
    writeStorage(LOCALE_KEY, v);
  }

  setTimezone(value: string | null): void {
    const v = value === null || value === '' ? null : value;
    this.timezone = v;
    writeStorage(TIMEZONE_KEY, v);
  }
}

export const displaySettings = new DisplaySettingsStore();
