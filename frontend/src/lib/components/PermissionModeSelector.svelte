<script lang="ts">
  import { agent, type PermissionMode } from '$lib/agent.svelte';

  /** Four modes the backend recognises. Order is chosen so risk grows
   *  left→right: Ask (safest, default) → Plan (read-only) → Auto-edit
   *  (waives prompts for Edit/Write) → Bypass (waives ALL prompts). */
  type Option = { value: PermissionMode; label: string; hint: string };

  const OPTIONS: Option[] = [
    {
      value: 'default',
      label: 'Ask',
      hint: 'Prompt before every tool call (safest).'
    },
    {
      value: 'plan',
      label: 'Plan',
      hint: 'Read-only planning — edits and writes are blocked.'
    },
    {
      value: 'acceptEdits',
      label: 'Auto-edit',
      hint: 'Allow Edit/Write without prompting. Other tools still prompt.'
    },
    {
      value: 'bypassPermissions',
      label: 'Bypass',
      hint: 'Allow every tool call without prompting. Use with care.'
    }
  ];

  /** Tone per mode. Deliberately escalates: slate → sky → amber → rose
   *  so the selector visibly warns as you pick riskier modes. The rose
   *  tone on Bypass is the main safety affordance — it has to be
   *  unmissable at a glance. */
  function toneClass(mode: PermissionMode): string {
    switch (mode) {
      case 'default':
        return 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700';
      case 'plan':
        return 'bg-sky-900 text-sky-200 border-sky-800 hover:bg-sky-800';
      case 'acceptEdits':
        return 'bg-amber-900 text-amber-200 border-amber-800 hover:bg-amber-800';
      case 'bypassPermissions':
        return 'bg-rose-900 text-rose-200 border-rose-800 hover:bg-rose-800';
    }
  }

  const current = $derived(
    OPTIONS.find((o) => o.value === agent.permissionMode) ?? OPTIONS[0]
  );

  function onChange(e: Event): void {
    const next = (e.currentTarget as HTMLSelectElement).value as PermissionMode;
    agent.setPermissionMode(next);
  }
</script>

<label class="relative inline-flex items-center">
  <span class="sr-only">Permission mode</span>
  <select
    class="appearance-none text-[10px] uppercase tracking-wider pl-2 pr-6 py-1
      rounded border cursor-pointer
      disabled:opacity-50 disabled:cursor-not-allowed
      focus:outline-none focus:ring-1 focus:ring-slate-400
      {toneClass(agent.permissionMode)}"
    value={agent.permissionMode}
    onchange={onChange}
    disabled={agent.state !== 'open'}
    aria-label="Permission mode"
    title={current.hint}
    data-testid="permission-mode-select"
  >
    {#each OPTIONS as opt (opt.value)}
      <option value={opt.value}>{opt.label}</option>
    {/each}
  </select>
  <span
    class="pointer-events-none absolute right-1.5 text-[8px]"
    aria-hidden="true">▾</span
  >
</label>
