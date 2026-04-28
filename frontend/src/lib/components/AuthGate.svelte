<script lang="ts">
  import { auth } from '$lib/stores/auth.svelte';

  let entry = $state('');
  let submitting = $state(false);
  let input: HTMLInputElement | undefined = $state();

  $effect(() => {
    if (auth.blocking && input) input.focus();
  });

  async function onSubmit() {
    submitting = true;
    auth.saveToken(entry);
    entry = '';
    submitting = false;
  }
</script>

{#if auth.blocking}
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4">
    <form
      class="flex w-full max-w-sm flex-col gap-4 rounded-lg border border-slate-800 bg-slate-900 p-6 shadow-2xl"
      onsubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <header>
        <h2 class="text-lg font-medium">Auth required</h2>
        <p class="mt-1 text-xs text-slate-400">
          {#if auth.status === 'invalid'}
            The stored token was rejected. Enter a new one.
          {:else}
            This server requires an auth token to proceed.
          {/if}
        </p>
      </header>
      <label class="flex flex-col gap-1 text-xs">
        <span class="text-slate-400">Token</span>
        <input
          type="password"
          class="rounded border border-slate-800 bg-slate-950 px-2 py-2 font-mono text-sm
            focus:border-slate-600 focus:outline-none"
          autocomplete="off"
          bind:value={entry}
          bind:this={input}
        />
      </label>
      <button
        type="submit"
        class="rounded bg-emerald-600 px-3 py-2 text-sm hover:bg-emerald-500
          disabled:cursor-not-allowed disabled:opacity-50"
        disabled={submitting || !entry.trim()}
      >
        Save & continue
      </button>
      <p class="text-[10px] text-slate-600">
        Stored in <code>localStorage</code> under <code>bearings:token</code>.
      </p>
    </form>
  </div>
{/if}
