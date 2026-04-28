import { describe, expect, it } from 'vitest';

import {
  INITIAL_LONG_PRESS_STATE,
  LONG_PRESS_MOVE_THRESHOLD_PX,
  reduceLongPress,
  type LongPressEvent,
  type LongPressState,
} from './touch';

/** Feed a sequence of events through the reducer and return the final
 * state + the list of effects produced. Mirrors the pattern used in
 * `keyboard.test.ts` so the FSM stays readable under test. */
function run(
  events: LongPressEvent[],
  opts?: { thresholdPx?: number }
): { state: LongPressState; effects: unknown[] } {
  let state = INITIAL_LONG_PRESS_STATE;
  const effects: unknown[] = [];
  for (const ev of events) {
    const result = reduceLongPress(state, ev, opts);
    state = result.state;
    if (result.effect) effects.push(result.effect);
  }
  return { state, effects };
}

describe('reduceLongPress — arming', () => {
  it('schedules the timer on pointerdown and moves to armed', () => {
    const { state, effects } = run([{ type: 'down', x: 10, y: 10 }]);
    expect(state.phase).toBe('armed');
    expect(state.startX).toBe(10);
    expect(state.startY).toBe(10);
    expect(effects).toEqual([{ type: 'schedule' }]);
  });

  it('ignores move / up / timer events while idle', () => {
    const { state, effects } = run([
      { type: 'move', x: 5, y: 5 },
      { type: 'up' },
      { type: 'cancel' },
      { type: 'timer' },
    ]);
    expect(state.phase).toBe('idle');
    expect(effects).toEqual([]);
  });
});

describe('reduceLongPress — movement threshold', () => {
  it('stays armed when movement is within slop', () => {
    const { state, effects } = run([
      { type: 'down', x: 0, y: 0 },
      { type: 'move', x: LONG_PRESS_MOVE_THRESHOLD_PX, y: 0 },
    ]);
    expect(state.phase).toBe('armed');
    // Only the schedule from `down` — no cancel yet.
    expect(effects).toEqual([{ type: 'schedule' }]);
  });

  it('cancels the timer when movement exceeds slop', () => {
    const { state, effects } = run([
      { type: 'down', x: 0, y: 0 },
      { type: 'move', x: LONG_PRESS_MOVE_THRESHOLD_PX + 1, y: 0 },
    ]);
    expect(state.phase).toBe('idle');
    expect(effects).toEqual([{ type: 'schedule' }, { type: 'cancel-timer' }]);
  });

  it('measures diagonal movement via hypot', () => {
    // 5px in each direction = ~7.07px magnitude, under the 8px slop.
    const kept = run([
      { type: 'down', x: 0, y: 0 },
      { type: 'move', x: 5, y: 5 },
    ]);
    expect(kept.state.phase).toBe('armed');
    // 6px in each direction = ~8.49px, over the slop.
    const dropped = run([
      { type: 'down', x: 0, y: 0 },
      { type: 'move', x: 6, y: 6 },
    ]);
    expect(dropped.state.phase).toBe('idle');
  });

  it('honours a custom threshold via opts', () => {
    const { state } = run(
      [
        { type: 'down', x: 0, y: 0 },
        { type: 'move', x: 3, y: 0 },
      ],
      { thresholdPx: 2 }
    );
    expect(state.phase).toBe('idle');
  });
});

describe('reduceLongPress — cancellation paths', () => {
  it('cancels on pointerup before timer fires', () => {
    const { state, effects } = run([{ type: 'down', x: 0, y: 0 }, { type: 'up' }]);
    expect(state.phase).toBe('idle');
    expect(effects).toEqual([{ type: 'schedule' }, { type: 'cancel-timer' }]);
  });

  it('cancels on pointercancel before timer fires', () => {
    const { state, effects } = run([{ type: 'down', x: 0, y: 0 }, { type: 'cancel' }]);
    expect(state.phase).toBe('idle');
    expect(effects).toEqual([{ type: 'schedule' }, { type: 'cancel-timer' }]);
  });

  it('treats a second down as a fresh start', () => {
    const { state, effects } = run([
      { type: 'down', x: 0, y: 0 },
      { type: 'down', x: 50, y: 50 },
    ]);
    expect(state.phase).toBe('armed');
    expect(state.startX).toBe(50);
    expect(state.startY).toBe(50);
    expect(effects).toEqual([{ type: 'schedule' }, { type: 'schedule' }]);
  });
});

describe('reduceLongPress — firing', () => {
  it('fires at the original press coordinates after timer expiry', () => {
    const { state, effects } = run([
      { type: 'down', x: 42, y: 99 },
      { type: 'move', x: 43, y: 99 }, // tiny jitter still within slop
      { type: 'timer' },
    ]);
    expect(state.phase).toBe('fired');
    expect(effects).toEqual([{ type: 'schedule' }, { type: 'fire', x: 42, y: 99 }]);
  });

  it('does not fire if the timer arrives after a cancel', () => {
    const { state, effects } = run([
      { type: 'down', x: 0, y: 0 },
      { type: 'cancel' },
      { type: 'timer' },
    ]);
    expect(state.phase).toBe('idle');
    // No `fire` effect — the timer event is a no-op against idle.
    expect(effects).toEqual([{ type: 'schedule' }, { type: 'cancel-timer' }]);
  });

  it('up after fired returns to idle without a second cancel', () => {
    const { state, effects } = run([
      { type: 'down', x: 0, y: 0 },
      { type: 'timer' },
      { type: 'up' },
    ]);
    expect(state.phase).toBe('idle');
    // The `up` after `fired` must NOT push a cancel-timer — the timer
    // has already fired and the caller has dropped its handle.
    expect(effects).toEqual([{ type: 'schedule' }, { type: 'fire', x: 0, y: 0 }]);
  });
});
