/**
 * Menu placement math. Pure functions — unit tested, no DOM access.
 *
 * Phase 1 ships cursor-anchored placement with viewport clamping. The
 * full flip-above / flip-left / submenu-flip logic and its exhaustive
 * tests land in Phase 2, per the plan. Existing call sites remain
 * source-compatible when Phase 2 lands; new fields get defaulted.
 */

/** Minimum breathing room from the viewport edge. Matches the 4px
 * clamp called out in the plan's §6.1 rules. */
export const VIEWPORT_MARGIN_PX = 4;

export type Placement = {
  left: number;
  top: number;
};

export type PlaceInput = {
  /** Desired anchor — usually the right-click `clientX`/`clientY`. */
  x: number;
  y: number;
  menuWidth: number;
  menuHeight: number;
  viewportWidth: number;
  viewportHeight: number;
};

/**
 * Place the menu's top-left at (x, y), clamped so no edge leaves the
 * viewport. If the menu is wider/taller than the viewport minus
 * margins, the margin wins — left/top pin to `VIEWPORT_MARGIN_PX`
 * and the overflow is accepted (the renderer's scroll handles it).
 */
export function placeAtCursor(input: PlaceInput): Placement {
  const {
    x,
    y,
    menuWidth,
    menuHeight,
    viewportWidth,
    viewportHeight
  } = input;
  const maxLeft = Math.max(
    VIEWPORT_MARGIN_PX,
    viewportWidth - menuWidth - VIEWPORT_MARGIN_PX
  );
  const maxTop = Math.max(
    VIEWPORT_MARGIN_PX,
    viewportHeight - menuHeight - VIEWPORT_MARGIN_PX
  );
  const left = Math.min(Math.max(x, VIEWPORT_MARGIN_PX), maxLeft);
  const top = Math.min(Math.max(y, VIEWPORT_MARGIN_PX), maxTop);
  return { left, top };
}
