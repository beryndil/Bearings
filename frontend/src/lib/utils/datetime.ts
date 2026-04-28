/**
 * Centralized date / time / duration formatting (§32 of
 * `~/.claude/coding-standards.md`).
 *
 * Wire format invariant: every backend timestamp is ISO 8601 with a
 * trailing `Z` (UTC). The backend is UTC-disciplined per
 * `db/_common.py` and `bearings_dir/schema.py`. This module is the
 * only display path — every user-visible date/time/duration in the
 * frontend should route through one of these helpers.
 *
 * The helpers read `locale` and `timezone` from the
 * `displaySettings` store at call time. `null` on either side falls
 * back to the browser default. Callers can override with explicit
 * args when locale or timezone matters for a specific surface (e.g.
 * tests pinning a fixed locale + zone).
 *
 * Output is always a localized human-readable string. Anything that
 * needs a machine-stable representation (filenames, log lines,
 * backend payloads) MUST keep using `new Date().toISOString()` —
 * those are not display surfaces and intentionally bypass this
 * module.
 */

import { displaySettings } from '$lib/stores/display-settings.svelte';

/** Resolve the locale to use for formatting. Explicit arg → store
 * override → browser default. */
function resolveLocale(explicit?: string | null): string | undefined {
  if (explicit) return explicit;
  return displaySettings.locale ?? undefined;
}

/** Resolve the timezone to use for formatting. Explicit arg → store
 * override → browser default. `Intl.DateTimeFormat` accepts
 * `undefined` to mean "use the runtime default," which matches what
 * `new Date().toLocaleString()` did before this module existed. */
function resolveTimeZone(explicit?: string | null): string | undefined {
  if (explicit) return explicit;
  return displaySettings.timezone ?? undefined;
}

/** Parse an ISO 8601 string into a `Date`. Returns `null` for empty,
 * unparseable, or non-string input. Use this rather than the bare
 * `new Date(iso)` constructor when the input might be malformed —
 * `new Date('garbage')` returns an Invalid Date object that lies
 * about being a Date and corrupts downstream formatters. */
export function parseISO(iso: string | null | undefined): Date | null {
  if (typeof iso !== 'string' || iso === '') return null;
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return null;
  return new Date(ms);
}

/** Format an absolute timestamp (date + time). Default options
 * mirror the legacy `new Date().toLocaleString()` shape — full
 * date with hours and minutes — so existing surfaces look the same
 * after migration unless the caller asks for something narrower. */
export function formatAbsolute(
  iso: string | null | undefined,
  opts: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  },
  localeOverride?: string | null,
  timeZoneOverride?: string | null
): string {
  const d = parseISO(iso);
  if (d === null) return '';
  const fmt = new Intl.DateTimeFormat(resolveLocale(localeOverride), {
    ...opts,
    timeZone: resolveTimeZone(timeZoneOverride),
  });
  return fmt.format(d);
}

/** Format a date-only string (no time-of-day). */
export function formatDate(
  iso: string | null | undefined,
  localeOverride?: string | null,
  timeZoneOverride?: string | null
): string {
  return formatAbsolute(
    iso,
    { year: 'numeric', month: 'short', day: '2-digit' },
    localeOverride,
    timeZoneOverride
  );
}

/** Format a time-only string (no date). */
export function formatTime(
  iso: string | null | undefined,
  localeOverride?: string | null,
  timeZoneOverride?: string | null
): string {
  return formatAbsolute(
    iso,
    { hour: '2-digit', minute: '2-digit' },
    localeOverride,
    timeZoneOverride
  );
}

/** Format a relative time ("5 minutes ago", "in 3 hours") using
 * `Intl.RelativeTimeFormat`. Picks the largest unit that doesn't
 * round to zero, capped at days; week / month / year are
 * deliberately skipped because pending-ops and reorg audits don't
 * sit around that long, and falling back to absolute formatting at
 * that horizon reads more naturally to operators.
 *
 * `now` is injectable so tests don't need to fake the global clock. */
export function formatRelative(
  iso: string | null | undefined,
  now: Date = new Date(),
  localeOverride?: string | null
): string {
  const d = parseISO(iso);
  if (d === null) return '';
  const diffMs = d.getTime() - now.getTime();
  const absSec = Math.abs(diffMs) / 1000;
  const rtf = new Intl.RelativeTimeFormat(resolveLocale(localeOverride), {
    numeric: 'auto',
  });

  // Round each candidate unit toward zero so "59s ago" stays in
  // seconds. The signed value preserves past/future direction for
  // RTF.
  const secs = Math.trunc(diffMs / 1000);
  if (absSec < 60) return rtf.format(secs, 'second');
  const mins = Math.trunc(diffMs / 60_000);
  if (absSec < 3600) return rtf.format(mins, 'minute');
  const hours = Math.trunc(diffMs / 3_600_000);
  if (absSec < 86_400) return rtf.format(hours, 'hour');
  const days = Math.trunc(diffMs / 86_400_000);
  return rtf.format(days, 'day');
}

/** Format a duration in milliseconds as a compact human label.
 * Sub-second → "850ms"; under a minute → "12s" or "12.3s" depending
 * on `precision`; under an hour → "5m07s"; over an hour → "2h15m".
 *
 * `precision` controls the sub-minute fractional digits:
 *   - `'tenths'` (default): "1.2s" — useful for finished calls where
 *     sub-second resolution distinguishes a fast tool from a slow one
 *     (Inspector's existing behavior).
 *   - `'integer'`: "1s" — useful for live-ticking elapsed displays
 *     where the tenths digit is always `.0` mid-tick and reads as
 *     false precision (MessageTurn's existing behavior).
 * Minute-and-up rendering is the same regardless of `precision`. */
export function formatDuration(ms: number, precision: 'tenths' | 'integer' = 'tenths'): string {
  if (!Number.isFinite(ms) || ms < 0) return '';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const totalSec = Math.floor(ms / 1000);
  if (totalSec < 60) {
    if (precision === 'integer') return `${totalSec}s`;
    return `${(ms / 1000).toFixed(1)}s`;
  }
  if (totalSec < 3600) {
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m}m${s.toString().padStart(2, '0')}s`;
  }
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  return `${h}h${m.toString().padStart(2, '0')}m`;
}
