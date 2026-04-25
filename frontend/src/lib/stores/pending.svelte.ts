/**
 * Pending-operations store — Phase 16 of docs/context-menu-plan.md.
 *
 * The floating `PendingOpsCard`, the sidebar header `PendingOpsBadge`,
 * and the `pending_operation` context-menu actions all read from this
 * single store. The store owns:
 *   - the absolute project directory the badge is currently watching
 *     (mirrors `agent.workingDir` for the active session — empty
 *     string means "no project, hide everything"),
 *   - the live operation list refreshed on resolve / dismiss / open,
 *   - a polling tick so a fresh `bearings pending add` from the CLI
 *     surfaces in the UI without a manual refresh,
 *   - the open/closed flag for the floating card overlay.
 *
 * Polling rather than WS: pending ops mutate from CLI commands the
 * server doesn't host (the user typing `bearings pending resolve foo`
 * in another terminal). A WS subscription would need a filesystem
 * watcher in the server process, which is non-trivial cross-platform
 * and adds little vs a 30-second poll for an inherently low-traffic
 * surface. Polling pauses while the document is hidden so a
 * background tab doesn't keep hammering the API.
 */

import * as api from '$lib/api/pending';
import type { PendingOperation } from '$lib/api/pending';

const POLL_INTERVAL_MS = 30_000;

class PendingStore {
  /** Most recent ops snapshot. Newest-first is the API's default. */
  ops = $state<PendingOperation[]>([]);

  /** Directory this snapshot belongs to. Resets to `''` when no
   * session is active so the badge doesn't keep showing a stale
   * count for a project the user moved away from. */
  directory = $state('');

  /** True while a refresh fetch is in flight. The badge greys itself
   * during the first load so a flash of "0" doesn't briefly contradict
   * what the server eventually reports. */
  loading = $state(false);

  /** Last error message from the server, surfaced in the card. */
  error = $state<string | null>(null);

  /** Card open/closed flag. Toggled by the badge click, the
   * Ctrl+Shift+O shortcut, and the Esc-cascade in the keyboard
   * registry. */
  cardOpen = $state(false);

  private pollTimer: ReturnType<typeof setInterval> | null = null;

  /** Live count for the badge — hides the badge entirely when 0. */
  get count(): number {
    return this.ops.length;
  }

  /** Point the store at a project directory. Re-fetches immediately
   * and (re)installs the poll timer. Passing `''` (or `null`) tears
   * the timer down — used when no session is selected. */
  async setDirectory(directory: string | null): Promise<void> {
    const next = directory ?? '';
    if (next === this.directory) return;
    this.directory = next;
    this.ops = [];
    this.error = null;
    if (!next) {
      this.stopPolling();
      return;
    }
    await this.refresh();
    this.startPolling();
  }

  async refresh(): Promise<void> {
    if (!this.directory) return;
    this.loading = true;
    try {
      const next = await api.listPending(this.directory);
      this.ops = next;
      this.error = null;
    } catch (err) {
      this.error = err instanceof Error ? err.message : String(err);
    } finally {
      this.loading = false;
    }
  }

  async resolve(directory: string, name: string): Promise<void> {
    try {
      await api.resolvePending(directory, name);
      this.ops = this.ops.filter((op) => op.name !== name);
    } catch (err) {
      this.error = err instanceof Error ? err.message : String(err);
    }
  }

  /** UX-distinct alias of `resolve` — same primitive, different verb
   * for the abandon-this-op path. See actions/pending_operation.ts
   * for the rationale on why two action IDs share one server call. */
  async dismiss(directory: string, name: string): Promise<void> {
    try {
      await api.deletePending(directory, name);
      this.ops = this.ops.filter((op) => op.name !== name);
    } catch (err) {
      this.error = err instanceof Error ? err.message : String(err);
    }
  }

  toggleCard(): void {
    this.cardOpen = !this.cardOpen;
    // Refresh on every open so the count the user clicked through to
    // is the live one rather than the most-recent poll snapshot.
    if (this.cardOpen) void this.refresh();
  }

  closeCard(): boolean {
    if (!this.cardOpen) return false;
    this.cardOpen = false;
    return true;
  }

  private startPolling(): void {
    this.stopPolling();
    if (typeof window === 'undefined') return;
    this.pollTimer = setInterval(() => {
      // Skip while the tab is hidden — pending ops aren't time-critical
      // and an idle tab shouldn't keep hitting the API.
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
        return;
      }
      void this.refresh();
    }, POLL_INTERVAL_MS);
  }

  private stopPolling(): void {
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }
}

export const pending = new PendingStore();
