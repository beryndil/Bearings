<script lang="ts">
  /**
   * Sticky top banner that surfaces "the backend is unreachable"
   * directly to the user (§8 Offline Resilience). The WS reconnect
   * loop in `ws_sessions.svelte.ts` already handles recovery with
   * exponential backoff — this component is the missing UI affordance
   * that tells the user *why* the sidebar stopped updating.
   *
   * Surface contract:
   *   - Hidden while `sessionsWs.state === 'open'`.
   *   - Hidden during the brief `connecting`/`closed`/`error` window
   *     before the threshold elapses, to avoid flashing the banner
   *     on every routine reconnect cycle.
   *   - Visible once `sessionsWs.state ∈ {'closed','error'}` has
   *     persisted for `THRESHOLD_MS` (5 s) without recovery.
   *   - On `'open'` the banner clears immediately.
   *   - Auth failures (`lastCloseCode === 4401`) are NOT shown here:
   *     the AuthGate modal owns that surface, and a stale token
   *     is a different problem from a dead backend.
   *
   * Why 5 s: the broker reconnects with exponential backoff starting
   * at 1 s. The first 2-3 retries usually win on a transient blip —
   * showing the banner sooner produces a flicker on every routine
   * reconnect (laptop sleep wake, wifi roam, server SIGHUP). 5 s is
   * long enough to skip those and short enough to surface a genuine
   * outage before the user notices the sidebar is frozen.
   *
   * Mounting: `+layout.svelte` — once at the app shell, fixed-top.
   */
  import { sessionsWs } from '$lib/stores/ws_sessions.svelte';

  /** How long a non-`open` state must persist before the banner
   * shows. Public via prop so tests can shrink the window without
   * monkey-patching the timer. */
  type Props = { thresholdMs?: number };
  let { thresholdMs = 5_000 }: Props = $props();

  const CODE_UNAUTHORIZED = 4401;

  let visible = $state(false);
  // Plain `let` (not `$state`) — these are imperative scheduling
  // bookkeeping, never read inside reactive scopes. Keeping them out
  // of `$state` prevents an inadvertent dependency loop where toggling
  // the timer reference triggers the same effect that scheduled it.
  let timer: ReturnType<typeof setTimeout> | null = null;
  let armed = false;

  function clearTimer(): void {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    armed = false;
  }

  // State machine — react to changes in `sessionsWs.state`. Outcomes:
  //   * 'open' → hide banner, disarm any pending timer.
  //   * auth-failed close (4401) → hide; AuthGate owns that surface.
  //   * 'idle' (pre-connect) → hide.
  //   * 'connecting' | 'closed' | 'error' → arm the threshold timer
  //     if not already armed. Crucially we do NOT reset the timer
  //     on each transition within the non-open band, because the
  //     reconnect loop cycles 'connecting' → 'closed' → 'connecting'
  //     and resetting on each step would push the banner past its
  //     threshold forever.
  //
  // No cleanup function is returned from this effect on purpose:
  // a per-rerun cleanup would clear the timer on every state
  // transition, defeating the "don't reset between non-open states"
  // invariant. Unmount cleanup is handled by the dedicated effect
  // below, which has no reactive sources and so only runs once.
  $effect(() => {
    const state = sessionsWs.state;
    const code = sessionsWs.lastCloseCode;

    const isOnline = state === 'open';
    const isAuthFail = state === 'closed' && code === CODE_UNAUTHORIZED;
    const isPreConnect = state === 'idle';

    if (isOnline || isAuthFail || isPreConnect) {
      clearTimer();
      visible = false;
      return;
    }
    if (visible || armed) return;
    armed = true;
    timer = setTimeout(() => {
      timer = null;
      armed = false;
      visible = true;
    }, thresholdMs);
  });

  // Unmount-only cleanup. The empty `$effect` body (no reactive
  // reads) means this effect runs exactly once on mount; its
  // returned cleanup runs only on component teardown, so a route
  // change mid-arm doesn't leak the pending setTimeout.
  $effect(() => {
    return () => clearTimer();
  });
</script>

{#if visible}
  <div
    role="status"
    aria-live="polite"
    class="fixed inset-x-0 top-0 z-50 flex items-center justify-center gap-3
      border-b border-amber-700/60 bg-amber-900/90 px-4 py-2 text-sm
      text-amber-50 shadow-lg backdrop-blur"
    data-testid="backend-status-banner"
  >
    <span aria-hidden="true" class="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-300"
    ></span>
    <span class="font-medium">Backend unreachable.</span>
    <span class="text-amber-200/80"> Trying to reconnect — recent updates may be missing. </span>
  </div>
{/if}
