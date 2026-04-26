/** Specs for the settings section registry.
 *
 * Contract surface:
 *  - SETTINGS_SECTIONS is sorted ascending by `weight` so the rail
 *    renders in the intended order.
 *  - Every entry carries a stable id, label, and component.
 *  - Six core sections ship in v1: profile, appearance, defaults,
 *    notifications, auth, about.
 */
import { describe, expect, it } from 'vitest';

import { SETTINGS_SECTIONS } from './sections';

describe('SETTINGS_SECTIONS', () => {
  it('is sorted ascending by weight', () => {
    const weights = SETTINGS_SECTIONS.map((s) => s.weight);
    const sorted = [...weights].sort((a, b) => a - b);
    expect(weights).toEqual(sorted);
  });

  it('every entry has id, label, and component', () => {
    for (const s of SETTINGS_SECTIONS) {
      expect(typeof s.id).toBe('string');
      expect(s.id).toMatch(/^[a-z][a-z0-9-]*$/);
      expect(typeof s.label).toBe('string');
      expect(s.label.length).toBeGreaterThan(0);
      expect(s.component).toBeDefined();
    }
  });

  it('ships the six core v1 sections', () => {
    const ids = SETTINGS_SECTIONS.map((s) => s.id).sort();
    expect(ids).toEqual([
      'about',
      'appearance',
      'auth',
      'defaults',
      'notifications',
      'profile'
    ]);
  });

  it('ids are unique', () => {
    const ids = SETTINGS_SECTIONS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
