/**
 * Version-watcher store (gap-cycle-01-018, N-14).
 *
 * Polls ``GET /api/diag/server`` every
 * :data:`STATUS_BAR_VERSION_POLL_INTERVAL_MS` and exposes the result as
 * a reactive ``$state`` object so the status bar re-renders when the
 * server version changes (e.g. after a hot-reload restart).
 *
 * Additionally polls ``GET /api/version`` for the bundle mtime (N-14).
 * When the server's bundle mtime is newer than the mtime captured at
 * page load, the watcher auto-reloads on:
 * - ``visibilitychange`` to ``"visible"`` (user switches back to tab).
 * - A debounced idle check after each mtime poll.
 *
 * The initial fetch fires immediately on first import so the status bar
 * shows a real version string as early as possible. On fetch failure the
 * current value is left unchanged; on the very first failure the version
 * stays at the loading placeholder.
 *
 * Behavior anchor: ``docs/behavior/chat.md`` §"App chrome" "Status strip".
 */
import { getJson } from "../api/client";
import {
  API_DIAG_SERVER_ENDPOINT,
  API_VERSION_ENDPOINT,
  STATUS_BAR_VERSION_POLL_INTERVAL_MS,
  STATUS_BAR_STRINGS,
} from "../config";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Subset of ``ServerDiagOut`` that the version watcher reads. */
interface DiagServerOut {
  version: string;
}

interface BundleVersionOut {
  bundle_mtime: number;
}

// ---------------------------------------------------------------------------
// Bundle mtime tracking (N-14)
// ---------------------------------------------------------------------------

/** Unix float seconds at page load (captured once on module init). */
const _PAGE_LOAD_MTIME: number = Date.now() / 1000;

let _serverBundleMtime: number | null = null;
let _reloadPending = false;

/** Debounce handle for the idle-reload check. */
let _reloadDebounce: ReturnType<typeof setTimeout> | null = null;

/**
 * Trigger a page reload if the server bundle is newer than the mtime
 * captured at page load. Debounced so rapid poll ticks don't stack up.
 */
function _maybeReload(): void {
  if (_reloadDebounce !== null) return; // already scheduled
  _reloadDebounce = setTimeout(() => {
    _reloadDebounce = null;
    if (
      !_reloadPending &&
      _serverBundleMtime !== null &&
      _serverBundleMtime > _PAGE_LOAD_MTIME
    ) {
      _reloadPending = true;
      window.location.reload();
    }
  }, 500);
}

/** Fetch the server bundle mtime and schedule a reload when newer. */
async function checkBundleMtime(): Promise<void> {
  try {
    const out = await getJson<BundleVersionOut>(API_VERSION_ENDPOINT);
    _serverBundleMtime = out.bundle_mtime;
    _maybeReload();
  } catch {
    // Silently ignore — no reload on network error.
  }
}

// Reload on tab-visible if a newer bundle was already detected.
if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      void checkBundleMtime();
    }
  });
}

// ---------------------------------------------------------------------------
// Reactive state
// ---------------------------------------------------------------------------

interface VersionWatcherStore {
  /** Current Bearings server version string, or the loading placeholder. */
  version: string;
}

const _store: VersionWatcherStore = $state({ version: STATUS_BAR_STRINGS.versionLoading });

/** Read-only reactive view of the version watcher state. */
export const versionWatcherStore: VersionWatcherStore = _store;

// ---------------------------------------------------------------------------
// Polling
// ---------------------------------------------------------------------------

/**
 * Fetch the server version once and update the store. Errors are
 * swallowed — a failed refresh leaves the displayed version unchanged
 * rather than crashing the status bar.
 */
async function refreshVersion(): Promise<void> {
  try {
    const diag = await getJson<DiagServerOut>(API_DIAG_SERVER_ENDPOINT);
    _store.version = diag.version;
  } catch {
    // Silently retain the current value on network / server error.
  }
  // Also check bundle mtime on each version poll tick.
  void checkBundleMtime();
}

// Kick off the first fetch immediately.
void refreshVersion();

// Schedule subsequent polls on the configured interval.
let _pollInterval: ReturnType<typeof setInterval> | null = setInterval(
  () => void refreshVersion(),
  STATUS_BAR_VERSION_POLL_INTERVAL_MS,
);

// ---------------------------------------------------------------------------
// Test helpers (not part of the public API)
// ---------------------------------------------------------------------------

/**
 * Override the displayed version for unit tests. Call before rendering
 * the component under test.
 *
 * @internal
 */
export function _setVersionForTests(version: string): void {
  _store.version = version;
}

/**
 * Reset the version to the loading placeholder and cancel any in-flight
 * interval timer so fake-timer tests start from a clean state.
 *
 * **Must be called in ``afterEach``** when fake timers are active —
 * otherwise the setInterval callback queued by this module fires during
 * the next test's fake-clock advance and pollutes that test's fetch mocks.
 *
 * @internal
 */
export function _resetVersionWatcherForTests(): void {
  _store.version = STATUS_BAR_STRINGS.versionLoading;
  _serverBundleMtime = null;
  _reloadPending = false;
  if (_reloadDebounce !== null) {
    clearTimeout(_reloadDebounce);
    _reloadDebounce = null;
  }
  if (_pollInterval !== null) {
    clearInterval(_pollInterval);
    _pollInterval = null;
  }
}

/**
 * Re-arm the poll interval after :func:`_resetVersionWatcherForTests`
 * has torn it down (used by tests that exercise the tick behaviour).
 *
 * @internal
 */
export function _startVersionPollForTests(): void {
  if (_pollInterval !== null) clearInterval(_pollInterval);
  _pollInterval = setInterval(() => void refreshVersion(), STATUS_BAR_VERSION_POLL_INTERVAL_MS);
}
