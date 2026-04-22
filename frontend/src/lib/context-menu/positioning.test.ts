import { describe, expect, it } from 'vitest';

import { VIEWPORT_MARGIN_PX, placeAtCursor } from './positioning';

// Phase 1 coverage: cursor-anchored clamping. Phase 2 grows this suite
// to exhaustive flip / submenu-flip cases per plan §6.1.

describe('placeAtCursor', () => {
  const viewport = { viewportWidth: 1000, viewportHeight: 800 };
  const smallMenu = { menuWidth: 200, menuHeight: 100 };

  it('places at the cursor when fully inside the viewport', () => {
    expect(
      placeAtCursor({ x: 100, y: 100, ...smallMenu, ...viewport })
    ).toEqual({ left: 100, top: 100 });
  });

  it('clamps to the right-edge margin when x+width overflows', () => {
    const p = placeAtCursor({ x: 950, y: 100, ...smallMenu, ...viewport });
    // 1000 - 200 - 4 = 796
    expect(p.left).toBe(796);
    expect(p.top).toBe(100);
  });

  it('clamps to the bottom-edge margin when y+height overflows', () => {
    const p = placeAtCursor({ x: 100, y: 780, ...smallMenu, ...viewport });
    // 800 - 100 - 4 = 696
    expect(p.top).toBe(696);
    expect(p.left).toBe(100);
  });

  it('clamps to the minimum margin when cursor is outside top-left', () => {
    const p = placeAtCursor({ x: -50, y: -50, ...smallMenu, ...viewport });
    expect(p.left).toBe(VIEWPORT_MARGIN_PX);
    expect(p.top).toBe(VIEWPORT_MARGIN_PX);
  });

  it('pins to the margin when the menu is wider than the viewport', () => {
    const p = placeAtCursor({
      x: 500,
      y: 500,
      menuWidth: 2000,
      menuHeight: 100,
      viewportWidth: 1000,
      viewportHeight: 800
    });
    // Oversize menu: left pins to margin, renderer handles overflow.
    expect(p.left).toBe(VIEWPORT_MARGIN_PX);
  });

  it('pins to the margin when the menu is taller than the viewport', () => {
    const p = placeAtCursor({
      x: 100,
      y: 100,
      menuWidth: 200,
      menuHeight: 2000,
      viewportWidth: 1000,
      viewportHeight: 800
    });
    expect(p.top).toBe(VIEWPORT_MARGIN_PX);
  });

  it('clamps both axes when the cursor is past both edges', () => {
    const p = placeAtCursor({
      x: 10_000,
      y: 10_000,
      ...smallMenu,
      ...viewport
    });
    expect(p.left).toBe(1000 - 200 - VIEWPORT_MARGIN_PX);
    expect(p.top).toBe(800 - 100 - VIEWPORT_MARGIN_PX);
  });
});
