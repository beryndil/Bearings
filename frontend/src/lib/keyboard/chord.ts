/**
 * Chord matching + serialization helpers for the keybindings layer.
 *
 * Behavior anchors:
 *
 * - ``docs/behavior/keyboard-shortcuts.md`` §"Conflict resolution"
 *   §"Non-US keyboard layouts" — letter chords compare against the
 *   physical key code (``event.code``); named keys compare against
 *   the produced character (``event.key``).
 * - §"Modifier-equivalence on Mac" — ``Cmd`` and ``Ctrl`` are treated
 *   as equivalent; the matcher accepts either when a binding requires
 *   ``ctrl``.
 *
 * The chord spec is the immutable description; chord *keys* (the
 * dotted strings in :func:`chordKey`) are the dispatch lookup key —
 * one event normalizes to exactly one chord key.
 */

/**
 * The matchable part of a chord — modifier flags + the physical code
 * or produced key. Used for normalization (computing a chord *key*
 * string the registry indexes by). The full :type:`ChordSpec`
 * extends this with the cheat-sheet display capsules.
 */
export interface ChordMatch {
  /** Match against ``event.code`` (e.g. ``"KeyC"``, ``"Digit1"``). */
  readonly code?: string;
  /** Match against ``event.key`` (e.g. ``"Escape"``, ``"?"``). */
  readonly key?: string;
  /** Required Shift modifier. Default ``false``. */
  readonly shift?: boolean;
  /** Required Ctrl/Cmd modifier. Default ``false``. */
  readonly ctrl?: boolean;
  /** Required Alt modifier. Default ``false``. */
  readonly alt?: boolean;
}

/**
 * Description of a single chord. ``code`` and ``key`` are mutually
 * exclusive entry points: a chord matches by physical position OR by
 * produced character, not both. The matcher prefers ``code`` when set.
 */
export interface ChordSpec extends ChordMatch {
  /** Cheat-sheet display capsules (e.g. ``["Shift", "C"]``). */
  readonly display: readonly string[];
}

/**
 * Normalize a chord into a stable string key. Ordering of modifier
 * tokens is deterministic so duplicate-detection at registration time
 * is exact: two chord specs that match the same key event compute to
 * the same key.
 *
 * Examples:
 *
 * - ``{code: "KeyC"}`` → ``"code:KeyC"``
 * - ``{code: "KeyC", shift: true}`` → ``"shift+code:KeyC"``
 * - ``{key: "?"}`` → ``"key:?"``
 * - ``{code: "KeyP", ctrl: true, shift: true}`` → ``"ctrl+shift+code:KeyP"``
 */
export function chordKey(spec: ChordMatch): string {
  const parts: string[] = [];
  if (spec.ctrl) parts.push("ctrl");
  if (spec.shift) parts.push("shift");
  if (spec.alt) parts.push("alt");
  if (spec.code !== undefined) {
    parts.push(`code:${spec.code}`);
  } else if (spec.key !== undefined) {
    parts.push(`key:${spec.key}`);
  } else {
    parts.push("invalid");
  }
  return parts.join("+");
}

/**
 * Translate a keyboard event into the canonical chord key. The
 * dispatcher computes this once per event and looks up the registered
 * spec by string equality.
 *
 * Match order:
 *
 * 1. If ``event.code`` is in the registered code-keyed bindings,
 *    that wins (letter / digit chords).
 * 2. Otherwise, fall back to ``event.key`` (named chords).
 *
 * The dispatcher computes both keys and probes them in turn.
 */
export function eventToCodeKey(event: KeyboardEvent): string {
  return chordKey({
    code: event.code,
    shift: event.shiftKey,
    ctrl: event.ctrlKey || event.metaKey,
    alt: event.altKey,
  });
}

/** Same as :func:`eventToCodeKey` but using ``event.key`` for named chords. */
export function eventToNamedKey(event: KeyboardEvent): string {
  return chordKey({
    key: event.key,
    shift: event.shiftKey,
    ctrl: event.ctrlKey || event.metaKey,
    alt: event.altKey,
  });
}

/**
 * Render a chord spec as a flat string (for ARIA / debug). The cheat
 * sheet renders ``display`` capsules as ``<kbd>``; this fallback shows
 * up in test assertions and screen-reader announcements.
 */
export function chordDisplayString(spec: ChordSpec): string {
  return spec.display.join("+");
}
