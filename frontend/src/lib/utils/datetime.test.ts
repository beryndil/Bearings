import { beforeEach, describe, expect, it } from 'vitest';

import {
  formatAbsolute,
  formatDate,
  formatDuration,
  formatRelative,
  formatTime,
  parseISO,
} from './datetime';
import { displaySettings } from '$lib/stores/display-settings.svelte';

// Pinned instant: 2026-04-27 14:30:45.123 UTC. Picked because:
//   - distinct hour digit in every supported zone (UTC 14, NY 10, Tokyo 23),
//   - cross-day boundary in Tokyo (next day 04-28 falls out of UTC 04-27),
//   - non-zero seconds + millis exercise the truncation path.
const FIXED_ISO = '2026-04-27T14:30:45.123Z';

describe('parseISO', () => {
  it('parses a valid ISO string', () => {
    const d = parseISO(FIXED_ISO);
    expect(d).not.toBeNull();
    expect(d?.toISOString()).toBe(FIXED_ISO);
  });

  it('returns null for empty / unparseable / non-string input', () => {
    expect(parseISO('')).toBeNull();
    expect(parseISO('not-a-date')).toBeNull();
    expect(parseISO(null)).toBeNull();
    expect(parseISO(undefined)).toBeNull();
  });
});

describe('formatAbsolute', () => {
  beforeEach(() => {
    displaySettings.setLocale(null);
    displaySettings.setTimezone(null);
  });

  // Cross-product of locales × timezones to prove the helper actually
  // localizes. Exact string match is brittle across Intl versions, so
  // we assert distinguishing substrings rather than full equality.
  // en-US defaults to 12-hour clock ("02:30 PM"), en-GB and ja-JP
  // default to 24-hour ("14:30") — same legacy `toLocaleString`
  // behavior, just centralized through `Intl` now.
  const cases: Array<{
    locale: string;
    timeZone: string;
    expectContains: string[];
  }> = [
    // UTC anchor — same day across all locales.
    {
      locale: 'en-US',
      timeZone: 'UTC',
      expectContains: ['Apr', '27', '02:30', 'PM'],
    },
    { locale: 'en-GB', timeZone: 'UTC', expectContains: ['Apr', '27', '14:30'] },
    { locale: 'ja-JP', timeZone: 'UTC', expectContains: ['4', '27', '14:30'] },

    // NY: 10:30 local time on the same day.
    {
      locale: 'en-US',
      timeZone: 'America/New_York',
      expectContains: ['Apr', '27', '10:30', 'AM'],
    },
    {
      locale: 'en-GB',
      timeZone: 'America/New_York',
      expectContains: ['Apr', '27', '10:30'],
    },

    // Tokyo: 23:30 local time on the same day, +0900 (11:30 PM en-US).
    {
      locale: 'en-US',
      timeZone: 'Asia/Tokyo',
      expectContains: ['Apr', '27', '11:30', 'PM'],
    },
    {
      locale: 'ja-JP',
      timeZone: 'Asia/Tokyo',
      expectContains: ['4', '27', '23:30'],
    },
  ];

  for (const { locale, timeZone, expectContains } of cases) {
    it(`renders ${locale} @ ${timeZone}`, () => {
      const out = formatAbsolute(FIXED_ISO, undefined, locale, timeZone);
      for (const piece of expectContains) {
        expect(out).toContain(piece);
      }
    });
  }

  it('returns empty string for unparseable input', () => {
    expect(formatAbsolute('garbage')).toBe('');
    expect(formatAbsolute(null)).toBe('');
    expect(formatAbsolute('')).toBe('');
  });

  it('honors store-set locale and timezone', () => {
    displaySettings.setLocale('ja-JP');
    displaySettings.setTimezone('Asia/Tokyo');
    const out = formatAbsolute(FIXED_ISO);
    expect(out).toContain('23:30'); // Tokyo local, ja-JP 24-hour
    expect(out).toContain('27');
  });

  it('explicit override beats store value', () => {
    displaySettings.setTimezone('Asia/Tokyo');
    const out = formatAbsolute(FIXED_ISO, undefined, 'en-GB', 'UTC');
    expect(out).toContain('14:30'); // UTC, not Tokyo
  });
});

describe('formatDate', () => {
  it('renders date without time', () => {
    const out = formatDate(FIXED_ISO, 'en-US', 'UTC');
    expect(out).toContain('Apr');
    expect(out).toContain('27');
    expect(out).not.toContain(':'); // no time-of-day separator
  });
});

describe('formatTime', () => {
  it('renders time without date components', () => {
    // en-GB for unambiguous 24-hour clock; en-US would say "02:30 PM"
    // which still passes "no date" but is harder to read in test
    // assertions.
    const out = formatTime(FIXED_ISO, 'en-GB', 'UTC');
    expect(out).toContain('14:30');
    expect(out).not.toMatch(/Apr|2026/);
  });

  it('shifts with timezone', () => {
    const ny = formatTime(FIXED_ISO, 'en-GB', 'America/New_York');
    const tokyo = formatTime(FIXED_ISO, 'en-GB', 'Asia/Tokyo');
    expect(ny).toContain('10:30');
    expect(tokyo).toContain('23:30');
  });
});

describe('formatRelative', () => {
  // Anchor `now` so the test doesn't depend on the global clock.
  const NOW = new Date('2026-04-27T14:30:45.123Z');

  it('formats sub-minute deltas in seconds', () => {
    const past = '2026-04-27T14:30:15.123Z'; // 30s ago
    expect(formatRelative(past, NOW, 'en-US')).toMatch(/30 sec|seconds? ago/);
  });

  it('formats sub-hour deltas in minutes', () => {
    const past = '2026-04-27T14:25:45.123Z'; // 5 min ago
    expect(formatRelative(past, NOW, 'en-US')).toMatch(/5 min|minutes? ago/);
  });

  it('formats sub-day deltas in hours', () => {
    const past = '2026-04-27T11:30:45.123Z'; // 3 h ago
    expect(formatRelative(past, NOW, 'en-US')).toMatch(/3 hour|hours? ago/);
  });

  it('formats multi-day deltas in days', () => {
    const past = '2026-04-25T14:30:45.123Z'; // 2 days ago
    expect(formatRelative(past, NOW, 'en-US')).toMatch(/2 day|days? ago/);
  });

  it('handles future timestamps', () => {
    const future = '2026-04-27T14:35:45.123Z'; // 5 min from now
    const out = formatRelative(future, NOW, 'en-US');
    expect(out).toMatch(/in 5/);
  });

  it('returns empty for unparseable input', () => {
    expect(formatRelative(null)).toBe('');
    expect(formatRelative('garbage')).toBe('');
  });

  it('respects locale override', () => {
    const past = '2026-04-27T14:25:45.123Z'; // 5 min ago
    const ja = formatRelative(past, NOW, 'ja-JP');
    expect(ja).toMatch(/分/); // Japanese for "minute"
  });
});

describe('formatDuration', () => {
  it('renders sub-second values in milliseconds', () => {
    expect(formatDuration(0)).toBe('0ms');
    expect(formatDuration(42)).toBe('42ms');
    expect(formatDuration(999)).toBe('999ms');
  });

  it('renders sub-minute values in seconds with one decimal by default', () => {
    expect(formatDuration(1000)).toBe('1.0s');
    expect(formatDuration(1500)).toBe('1.5s');
    expect(formatDuration(59_900)).toBe('59.9s');
  });

  it("renders integer seconds when precision is 'integer'", () => {
    expect(formatDuration(1000, 'integer')).toBe('1s');
    expect(formatDuration(1500, 'integer')).toBe('1s');
    expect(formatDuration(45_900, 'integer')).toBe('45s');
    expect(formatDuration(59_999, 'integer')).toBe('59s');
  });

  it('renders sub-hour values as MmSSs', () => {
    expect(formatDuration(60_000)).toBe('1m00s');
    expect(formatDuration(82_000)).toBe('1m22s');
    expect(formatDuration(3_599_000)).toBe('59m59s');
  });

  it('renders multi-hour values as HhMMm', () => {
    expect(formatDuration(3_600_000)).toBe('1h00m');
    expect(formatDuration(8_100_000)).toBe('2h15m');
  });

  it('returns empty for invalid input', () => {
    expect(formatDuration(NaN)).toBe('');
    expect(formatDuration(-1)).toBe('');
    expect(formatDuration(Infinity)).toBe('');
  });
});
