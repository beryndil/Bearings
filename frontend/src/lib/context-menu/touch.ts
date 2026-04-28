/**
 * Long-press detector for touch / coarse-pointer context menus — Phase
 * 11 of `docs/context-menu-plan.md`. The FSM is a pure reducer so the
 * tricky state transitions (movement threshold, pointer cancel, timer
 * expiry) can be unit-tested without a real touchscreen or `jsdom`
 * pointer simulation.
 *
 * Contract per spec §6.4:
 *   - 500ms press with <=8px movement fires the synthetic "open menu"
 *     event.
 *   - Any movement past the threshold cancels the timer — a drag
 *     must not open a menu.
 *   - Pointer-up before 500ms is a regular tap; the browser still sees
 *     it and the element's click handler fires normally.
 *   - Pointer-cancel (gesture interrupted, e.g. a modal opens, the
 *     browser scrolls, etc.) cancels.
 *
 * The Svelte action `longpress` below wires the reducer to DOM events
 * and handles the `setTimeout`/`clearTimeout` plumbing. Callers pass
 * `onLongPress(x, y)` to receive the synthetic event.
 */

/** How long the user must hold before the menu opens. Matches
 * Android's `longClickable` default and feels deliberate without being
 * slow. */
export const LONG_PRESS_DURATION_MS = 500;

/** Pixel slop tolerated before we classify the gesture as a drag and
 * cancel. 8px matches the `touchslop` convention on Android — big
 * enough to absorb finger jitter, small enough that a genuine swipe
 * cancels fast. */
export const LONG_PRESS_MOVE_THRESHOLD_PX = 8;

export type LongPressPhase = 'idle' | 'armed' | 'fired';

export type LongPressState = {
  phase: LongPressPhase;
  startX: number;
  startY: number;
};

export type LongPressEvent =
  | { type: 'down'; x: number; y: number }
  | { type: 'move'; x: number; y: number }
  | { type: 'up' }
  | { type: 'cancel' }
  | { type: 'timer' };

export type LongPressEffect =
  | { type: 'schedule' }
  | { type: 'cancel-timer' }
  | { type: 'fire'; x: number; y: number }
  | null;

export type LongPressOptions = {
  /** Defaults to `LONG_PRESS_MOVE_THRESHOLD_PX`. Tests override for
   * deterministic thresholds. */
  thresholdPx?: number;
};

export const INITIAL_LONG_PRESS_STATE: LongPressState = {
  phase: 'idle',
  startX: 0,
  startY: 0,
};

/** Pure transition function. Returns the next state and an optional
 * effect for the caller to apply (start/stop the timer, fire the
 * synthetic event). */
export function reduceLongPress(
  state: LongPressState,
  event: LongPressEvent,
  opts: LongPressOptions = {}
): { state: LongPressState; effect: LongPressEffect } {
  const threshold = opts.thresholdPx ?? LONG_PRESS_MOVE_THRESHOLD_PX;
  switch (event.type) {
    case 'down': {
      // `down` during `armed` is impossible on well-behaved devices
      // (you don't get two consecutive downs without an up / cancel),
      // but if it happens we treat the new down as a fresh start —
      // safer than leaving a stale timer pending.
      return {
        state: { phase: 'armed', startX: event.x, startY: event.y },
        effect: { type: 'schedule' },
      };
    }
    case 'move': {
      if (state.phase !== 'armed') return { state, effect: null };
      const dx = event.x - state.startX;
      const dy = event.y - state.startY;
      if (Math.hypot(dx, dy) <= threshold) {
        return { state, effect: null };
      }
      return {
        state: INITIAL_LONG_PRESS_STATE,
        effect: { type: 'cancel-timer' },
      };
    }
    case 'up':
    case 'cancel': {
      if (state.phase === 'idle') return { state, effect: null };
      // `up` after `fired` is a no-op — the menu is already open, the
      // reducer returns to idle but doesn't need to cancel the timer
      // (it already fired).
      const effect: LongPressEffect = state.phase === 'armed' ? { type: 'cancel-timer' } : null;
      return { state: INITIAL_LONG_PRESS_STATE, effect };
    }
    case 'timer': {
      if (state.phase !== 'armed') return { state, effect: null };
      return {
        state: { ...state, phase: 'fired' },
        effect: { type: 'fire', x: state.startX, y: state.startY },
      };
    }
  }
}

/** True when the current environment reports a coarse pointer (touch
 * screen, TV remote, etc). Returns false in SSR / test environments
 * without `matchMedia`. Callers use this to decide whether to bind the
 * long-press listener at all — on a desktop with a mouse, the native
 * `contextmenu` event is the authoritative open path. */
export function isCoarsePointer(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  try {
    return window.matchMedia('(pointer: coarse)').matches;
  } catch {
    return false;
  }
}

export type LongPressBinding = {
  /** Called when the long-press timer expires with the starting
   * pointer coordinates (NOT the latest — spec says "open at press
   * location"). Caller is responsible for opening the menu. */
  onLongPress: (x: number, y: number) => void;
  /** Caller can short-circuit the whole detector when false —
   * reactive updates re-check on `update`. Useful to disable
   * long-press while another modal is open. */
  enabled?: boolean;
};

/** Svelte action that wires the FSM to pointer events. Only coarse
 * pointers arm the detector — on a desktop mouse this is a cheap
 * no-op that just attaches a pointerdown listener that never fires
 * `schedule`. */
export function longpress(
  node: HTMLElement,
  binding: LongPressBinding
): { update: (next: LongPressBinding) => void; destroy: () => void } {
  let current: LongPressBinding = binding;
  let state: LongPressState = INITIAL_LONG_PRESS_STATE;
  let timer: ReturnType<typeof setTimeout> | null = null;

  function apply(effect: LongPressEffect, x = 0, y = 0): void {
    if (!effect) return;
    if (effect.type === 'schedule') {
      if (timer !== null) clearTimeout(timer);
      timer = setTimeout(() => {
        timer = null;
        const result = reduceLongPress(state, { type: 'timer' });
        state = result.state;
        apply(result.effect);
      }, LONG_PRESS_DURATION_MS);
      return;
    }
    if (effect.type === 'cancel-timer') {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
      return;
    }
    if (effect.type === 'fire') {
      current.onLongPress(effect.x || x, effect.y || y);
    }
  }

  function dispatch(event: LongPressEvent): void {
    if (current.enabled === false) return;
    const result = reduceLongPress(state, event);
    state = result.state;
    apply(result.effect);
  }

  function onDown(e: PointerEvent): void {
    // Only primary-button touches arm the detector — a stylus eraser
    // or a secondary mouse button should never trigger long-press.
    if (e.pointerType !== 'touch' && e.pointerType !== 'pen') return;
    if (!isCoarsePointer()) return;
    dispatch({ type: 'down', x: e.clientX, y: e.clientY });
  }

  function onMove(e: PointerEvent): void {
    dispatch({ type: 'move', x: e.clientX, y: e.clientY });
  }

  function onUp(): void {
    dispatch({ type: 'up' });
  }

  function onCancel(): void {
    dispatch({ type: 'cancel' });
  }

  node.addEventListener('pointerdown', onDown);
  node.addEventListener('pointermove', onMove);
  node.addEventListener('pointerup', onUp);
  node.addEventListener('pointercancel', onCancel);
  // Losing pointer capture mid-gesture (e.g. the browser starts a
  // native scroll) counts as a cancel — dispatch rather than leaving
  // the FSM armed with a timer that will fire on an untracked gesture.
  node.addEventListener('pointerleave', onCancel);

  return {
    update(next: LongPressBinding): void {
      current = next;
    },
    destroy(): void {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
      node.removeEventListener('pointerdown', onDown);
      node.removeEventListener('pointermove', onMove);
      node.removeEventListener('pointerup', onUp);
      node.removeEventListener('pointercancel', onCancel);
      node.removeEventListener('pointerleave', onCancel);
    },
  };
}
