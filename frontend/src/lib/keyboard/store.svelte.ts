/**
 * Keybindings runtime store — focus + modal context tracking and the
 * registered handler map. Two pieces live together because the
 * dispatcher reads both on every event:
 *
 * - ``activeContexts`` — the current focus / modal state, used to
 *   gate bare-letter chords per ``docs/behavior/keyboard-shortcuts.md``
 *   §"Contexts".
 * - ``handlers`` — the action-id → handler map; the dispatcher invokes
 *   ``handlers[binding.id]?.()`` after a chord matches.
 *
 * Components do NOT subscribe to this store reactively — the
 * dispatcher reads it imperatively in its keydown listener. Mutation
 * goes through the helpers below so the focus-tracking logic stays in
 * one place.
 */

/**
 * Composer-focused: a textarea / contenteditable / input owns the
 * keystroke. Bare-letter chords skip when ``true``.
 */
let composerFocused = $state(false);
/**
 * Modal-open: any of the modals (cheat sheet, new-session dialog,
 * template picker, etc.) is the foreground. Sidebar nav + bare-letter
 * chords skip when ``true``; ``global: true`` bindings still fire.
 */
let modalOpen = $state(false);

const handlers = new Map<string, () => void>();

/**
 * Reactive snapshot of the active context flags. Components reading
 * this do NOT subscribe via ``$effect`` — only the dispatcher reads
 * it, and it does so synchronously on each keystroke.
 */
export const keybindingsState = {
  get composerFocused(): boolean {
    return composerFocused;
  },
  get modalOpen(): boolean {
    return modalOpen;
  },
};

export function setComposerFocused(value: boolean): void {
  composerFocused = value;
}

export function setModalOpen(value: boolean): void {
  modalOpen = value;
}

/**
 * Bind an action handler. Returns a cleanup function to unbind on
 * component teardown. Re-binding an existing id replaces the previous
 * handler — the most-recently-mounted consumer wins, mirroring the
 * focus-trap convention modal libraries use.
 */
export function bindHandler(actionId: string, handler: () => void): () => void {
  const previous = handlers.get(actionId);
  handlers.set(actionId, handler);
  return () => {
    // Only undo if we are still the registered handler — a fresh
    // re-bind from a different consumer should not be clobbered.
    if (handlers.get(actionId) === handler) {
      if (previous !== undefined) {
        handlers.set(actionId, previous);
      } else {
        handlers.delete(actionId);
      }
    }
  };
}

/** Look up a registered handler. Returns ``undefined`` when unbound. */
export function getHandler(actionId: string): (() => void) | undefined {
  return handlers.get(actionId);
}

/** Test seam — drop every registered handler + reset focus state. */
export function _resetForTests(): void {
  handlers.clear();
  composerFocused = false;
  modalOpen = false;
}
