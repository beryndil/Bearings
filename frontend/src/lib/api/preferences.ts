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
  /** ISO-8601 timestamp of the last successful avatar upload, or
   * `null` when no avatar is set. The cache-busted URL is in
   * `avatar_url`; this raw timestamp is exposed for components that
   * need to reason about freshness directly (e.g. tests). */
  avatar_uploaded_at: string | null;
  /** Cache-busted URL for the avatar PNG, or `null` when no avatar
   * is set. The backend composes `/api/preferences/avatar?v=<ts>`
   * from `avatar_uploaded_at` so the frontend doesn't have to mirror
   * the contract. NULL means "render initials fallback." */
  avatar_url: string | null;
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

/** Upload a new avatar image. The backend re-encodes whatever PNG /
 * JPEG / WebP we send into a 512×512 PNG, so the caller doesn't need
 * to pre-process anything. Returns the updated preferences row whose
 * `avatar_url` reflects the new cache-busted path. */
export function uploadAvatar(file: File, fetchImpl: typeof fetch = fetch): Promise<Preferences> {
  const form = new FormData();
  form.append('file', file);
  return jsonFetch<Preferences>(fetchImpl, '/api/preferences/avatar', {
    method: 'POST',
    body: form,
  });
}

/** Clear the avatar. Idempotent on the server side — calling it twice
 * is the same as calling it once; the row's `avatar_url` is `null`
 * either way. */
export function deleteAvatar(fetchImpl: typeof fetch = fetch): Promise<Preferences> {
  return jsonFetch<Preferences>(fetchImpl, '/api/preferences/avatar', {
    method: 'DELETE',
  });
}
