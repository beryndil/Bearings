/**
 * Inspector store — the single source of truth for *which* tab the
 * inspector is showing and *which* session it is reading.
 *
 * Per arch §1.2 + §2.2 the inspector is one canonical store, one file.
 * The two pieces of state live together because every consumer that
 * cares about one cares about the other: the tab strip switches which
 * subsection renders, the subsection renders against the active
 * session row. Splitting them across two stores would force every
 * subsection component to import from two places without a net win.
 *
 * Components subscribe by reading the proxy fields directly:
 *
 * ```svelte
 * import { inspectorStore } from "$lib/stores/inspector.svelte";
 * $: tab = inspectorStore.activeTabId;
 * ```
 *
 * All mutation flows through the imperative helpers below; components
 * never write into the proxy directly. That keeps the dependency graph
 * one-way (components → helpers → store) and matches the
 * tags/sessions/conversation store conventions already established in
 * items 2.2 + 2.3.
 */
import { DEFAULT_INSPECTOR_TAB, KNOWN_INSPECTOR_TABS, type InspectorTabId } from "../config";

interface InspectorState {
  /**
   * Currently-rendered subsection. Always one of
   * :data:`KNOWN_INSPECTOR_TABS`; a caller passing an unknown id is
   * silently ignored (defense-in-depth — a future migration that drops
   * a tab id leaves stale local-storage values harmless).
   */
  activeTabId: InspectorTabId;
  /**
   * Session id the inspector is reading. Mirrors the conversation
   * pane's selection — both are driven from the sidebar's row click in
   * ``+layout.svelte``. ``null`` means "no session selected" (boot
   * state, or every row deselected after a tag-filter change emptied
   * the list).
   */
  activeSessionId: string | null;
}

const state: InspectorState = $state({
  activeTabId: DEFAULT_INSPECTOR_TAB,
  activeSessionId: null,
});

/**
 * Reactive proxy. Read fields off this object inside ``$derived`` /
 * template expressions; mutation is goes through :func:`setInspectorTab`
 * / :func:`setActiveSession` rather than direct field writes so the
 * lone "valid id" check stays in one place.
 */
export const inspectorStore = state;

/**
 * Switch the active subsection. Unknown ids are ignored; the existing
 * tab id stays in place. The check is structural, not throw-on-error:
 * a stale id from a removed feature flag should be a no-op rather than
 * a crash, and a typo at a call site is caught by the
 * :type:`InspectorTabId` parameter type at compile time anyway.
 */
export function setInspectorTab(id: InspectorTabId): void {
  if (!KNOWN_INSPECTOR_TABS.includes(id)) {
    return;
  }
  state.activeTabId = id;
}

/**
 * Set (or clear) the inspector's active session. ``null`` clears it —
 * the inspector renders its empty state until the next selection.
 */
export function setActiveSession(sessionId: string | null): void {
  state.activeSessionId = sessionId;
}

/** Test seam — restores the boot state without re-importing the module. */
export function _resetForTests(): void {
  state.activeTabId = DEFAULT_INSPECTOR_TAB;
  state.activeSessionId = null;
}
