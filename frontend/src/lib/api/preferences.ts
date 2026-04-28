/** Wire shape for `/api/preferences` GET + PATCH. Mirrors the
 * `PreferencesOut` Pydantic DTO on the backend. The record is a
 * singleton (id=1) so there's no list / create endpoint — every field
 * is nullable on the wire because the seed row lands at migration
 * time with NULL display_name / theme / model / workdir. The frontend
 * treats NULL as "unset" and falls back to its built-in defaults. */
export type Preferences = {
  display_name: string | null;
  theme: string | null;
  default_model: string | null;
  default_working_dir: string | null;
  notify_on_complete: boolean;
  updated_at: string;
};

/** Partial-update body for PATCH. Every field is optional; omit a
 * field to leave it untouched, set explicit `null` to clear it
 * (nullable string columns only — `notify_on_complete` collapses
 * `null` to `false` server-side). `display_name` is capped at 64
 * characters and whitespace-only submissions are coalesced to NULL by
 * the backend Pydantic validator, so the client doesn't have to
 * normalise before sending. */
export type PreferencesPatch = Partial<{
  display_name: string | null;
  theme: string | null;
  default_model: string | null;
  default_working_dir: string | null;
  notify_on_complete: boolean | null;
}>;

import { jsonFetch } from './core';

export function fetchPreferences(fetchImpl: typeof fetch = fetch): Promise<Preferences> {
  return jsonFetch<Preferences>(fetchImpl, '/api/preferences');
}

export function patchPreferences(
  body: PreferencesPatch,
  fetchImpl: typeof fetch = fetch
): Promise<Preferences> {
  return jsonFetch<Preferences>(fetchImpl, '/api/preferences', {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}
