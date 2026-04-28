<script lang="ts">
  /**
   * Standardized Loading / Success / Error / Empty wrapper for any
   * data-fetching view (§9 Error UX in the Beryndil standards).
   *
   * Why a single component: every view that loads data must explicitly
   * branch on those four states, and ad-hoc `{#if loading} … {:else
   * if error}` blocks let views drift — some surface a retry button,
   * most don't; some say "Loading…", most use a different sentinel.
   * DataView centralizes the shape so a missed branch is a missing
   * prop, not a missing snippet block.
   *
   * Caller contract (the four states, mutually exclusive in this
   * priority order):
   *   1. `error` truthy → render the error branch (with retry).
   *   2. `loading` true and we have no usable data yet → loading.
   *   3. `isEmpty` true → empty.
   *   4. otherwise → success (default `children` snippet).
   *
   * "No usable data yet" is the caller's call: if a soft-refresh is
   * in flight on top of an existing list, pass `loading=false` (or
   * keep `loading=true` but flip `isEmpty=false`) so the user
   * doesn't see the skeleton flicker between updates. The pattern
   * we apply at migration sites is `loading={store.loading &&
   * store.list.length === 0}`.
   *
   * Snippets (Svelte 5 — passed as props, not `<svelte:slot>`):
   *   - default (`children`) — success body.
   *   - `loadingSnippet` — override the default skeleton pulse.
   *   - `errorSnippet` — override the default error+retry block.
   *     Receives `(message, onRetry?)` so callers can format their
   *     own copy while keeping the retry wiring.
   *   - `emptySnippet` — override the default empty message.
   *
   * The default skeleton is a 3-bar `animate-pulse` block that
   * matches the project's existing pulse usage (see TokenMeter,
   * Conversation streaming caret) and respects
   * `prefers-reduced-motion` via Tailwind's animate-pulse, which is
   * already gated by user preference at the browser level.
   */
  import type { Snippet } from 'svelte';

  type Props = {
    /** Data fetch in flight and we have nothing to show yet. */
    loading: boolean;
    /** Last fetch failed with this message. Truthy => error branch. */
    error: string | null;
    /** Fetch succeeded but yielded zero items. */
    isEmpty: boolean;
    /** Optional retry handler — drives the default error branch's
     * Retry button. If omitted, the button is hidden so callers
     * with no retry surface don't show a dead control. */
    onRetry?: () => void;
    /** Optional label for the empty branch's default copy.
     * Replace the whole branch via the `empty` snippet for
     * anything more complex. */
    emptyLabel?: string;
    /** Optional aria-label for the loading skeleton's container. */
    loadingLabel?: string;
    /** Optional CSS class applied to the wrapper div so callers
     * can scope sizing/padding without wrapping DataView in
     * another div at every call site. */
    class?: string;

    children?: Snippet;
    loadingSnippet?: Snippet;
    errorSnippet?: Snippet<[string, (() => void) | undefined]>;
    emptySnippet?: Snippet;
  };

  let {
    loading,
    error,
    isEmpty,
    onRetry,
    emptyLabel = 'Nothing to show.',
    loadingLabel = 'Loading…',
    class: klass = '',
    children,
    loadingSnippet,
    errorSnippet,
    emptySnippet,
  }: Props = $props();
</script>

<div class={klass} data-testid="dataview-root">
  {#if error}
    {#if errorSnippet}
      {@render errorSnippet(error, onRetry)}
    {:else}
      <div
        role="alert"
        class="flex flex-col items-start gap-2 px-4 py-6"
        data-testid="dataview-error"
      >
        <p class="text-sm text-rose-400">
          <span class="font-medium">Couldn't load:</span>
          {error}
        </p>
        {#if onRetry}
          <button
            type="button"
            class="rounded border border-rose-700/60 bg-rose-900/20 px-3 py-1
              text-xs font-medium text-rose-200 hover:bg-rose-900/40
              focus:outline-none focus:ring-2 focus:ring-rose-500"
            onclick={onRetry}
            data-testid="dataview-retry"
          >
            Retry
          </button>
        {/if}
      </div>
    {/if}
  {:else if loading}
    {#if loadingSnippet}
      {@render loadingSnippet()}
    {:else}
      <div
        role="status"
        aria-label={loadingLabel}
        aria-busy="true"
        class="flex flex-col gap-2 px-4 py-6"
        data-testid="dataview-loading"
      >
        <div class="h-3 w-3/5 animate-pulse rounded bg-slate-800/80"></div>
        <div class="h-3 w-4/5 animate-pulse rounded bg-slate-800/80"></div>
        <div class="h-3 w-2/5 animate-pulse rounded bg-slate-800/80"></div>
        <span class="sr-only">{loadingLabel}</span>
      </div>
    {/if}
  {:else if isEmpty}
    {#if emptySnippet}
      {@render emptySnippet()}
    {:else}
      <p class="px-4 py-6 text-sm text-slate-500" data-testid="dataview-empty">
        {emptyLabel}
      </p>
    {/if}
  {:else}
    {@render children?.()}
  {/if}
</div>
