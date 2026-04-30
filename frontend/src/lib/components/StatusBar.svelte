<script lang="ts">
  /**
   * Bottom status strip — Phase 2a of the v1.0.0 dashboard redesign.
   *
   * Surfaces the always-on app-state signals the mockup put at the
   * bottom of the chrome:
   *
   *   Bearings v0.24.0   ~/projects/bearings   ●  Recovery: Enabled
   *                                            ●  Auto-save: On    Connected
   *
   * Lives at the bottom of the `(app)` group's flex-column shell so
   * it spans the full viewport (sidebar + main + inspector). Renders
   * unconditionally — when no session is selected, the working-dir
   * slot is suppressed but version + recovery + auto-save + connection
   * stay put. Signals previously rendered in `ConversationHeader.svelte`
   * (working_dir + connection badge) move here; the header is now
   * session-content focused (title, model, cost, tags, description),
   * the footer is chrome-state focused.
   *
   * Recovery and auto-save are static-text indicators today: both
   * features are unconditionally on (recovery is built into the WS
   * reconnect loop in `ws_sessions.svelte.ts`; auto-save is the WS
   * persistence path on every message). When/if either becomes
   * configurable, the relevant store flag plugs in here. Disk usage
   * ("2.1 GB" in the mockup) is deferred — would require a new server
   * endpoint, out of scope for Phase 2a.
   */
  import { onMount } from 'svelte';
  import { agent } from '$lib/agent.svelte';
  import { sessions } from '$lib/stores/sessions.svelte';
  import { connectionLabel } from '$lib/utils/conversation-ui';
  import { fetchVersion } from '$lib/api/version';

  let appVersion = $state<string | null>(null);

  onMount(async () => {
    try {
      const info = await fetchVersion();
      appVersion = info.version;
    } catch {
      // /api/version is best-effort here. A failure leaves the version
      // slot rendering plain "Bearings" — the rest of the bar is
      // unaffected, so a transient backend hiccup doesn't blank out
      // the connection state or working-dir display.
      appVersion = null;
    }
  });

  /** Compress `/home/<user>/...` paths to `~/...` for display. The full
   * absolute path stays available via the `title` attribute on hover. */
  function homeShorten(path: string | undefined | null): string {
    if (!path) return '';
    const home = '/home/';
    if (path.startsWith(home)) {
      const rest = path.slice(home.length);
      const slash = rest.indexOf('/');
      if (slash !== -1) return '~' + rest.slice(slash);
    }
    return path;
  }
</script>

<footer
  class="flex shrink-0 items-center justify-between gap-3 border-t
    border-slate-800 bg-slate-950 px-4 py-1.5 text-[11px] text-slate-500"
  data-testid="status-bar"
  aria-label="Application status"
>
  <div class="flex min-w-0 items-center gap-3">
    <span class="font-medium text-emerald-400" data-testid="status-bar-version">
      {#if appVersion}Bearings v{appVersion}{:else}Bearings{/if}
    </span>
    {#if sessions.selected}
      <span aria-hidden="true">·</span>
      <span
        class="truncate font-mono text-slate-400"
        title={sessions.selected.working_dir}
        data-testid="status-bar-working-dir"
      >
        {homeShorten(sessions.selected.working_dir)}
      </span>
    {/if}
  </div>
  <div class="flex shrink-0 items-center gap-3">
    <span class="inline-flex items-center gap-1.5">
      <span class="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true"></span>
      Recovery: Enabled
    </span>
    <span class="inline-flex items-center gap-1.5">
      <span class="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true"></span>
      Auto-save: On
    </span>
    <span
      class="rounded px-2 py-0.5 text-[10px] uppercase tracking-wider
        {agent.state === 'open'
        ? 'bg-emerald-900 text-emerald-300'
        : agent.state === 'connecting'
          ? 'bg-amber-900 text-amber-300'
          : 'bg-slate-800 text-slate-400'}"
      data-testid="status-bar-connection"
    >
      {connectionLabel(agent.state, agent.reconnectDelayMs, agent.lastCloseCode)}
    </span>
  </div>
</footer>
