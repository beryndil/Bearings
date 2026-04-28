<script lang="ts">
  import { KNOWN_MODELS, isKnownModel } from '$lib/models';

  let {
    value = $bindable(''),
    placeholder = 'claude-opus-4-7',
  }: { value?: string; placeholder?: string } = $props();

  const CUSTOM_SENTINEL = '__custom__';

  // Display state: the select shows either a known model or the
  // CUSTOM_SENTINEL. Non-empty unknown values surface as Custom with
  // the input pre-populated. Empty value shows the disabled placeholder
  // unless the user explicitly chose Custom — in which case we keep
  // the input visible so they can type without fighting the UI.
  let userPickedCustom = $state(false);

  const selectValue = $derived.by(() => {
    if (isKnownModel(value)) return value;
    if (value !== '' || userPickedCustom) return CUSTOM_SENTINEL;
    return '';
  });

  const showCustomInput = $derived(
    (value !== '' && !isKnownModel(value)) || (value === '' && userPickedCustom)
  );

  let customInput: HTMLInputElement | undefined = $state();

  function onSelectChange(e: Event) {
    const next = (e.target as HTMLSelectElement).value;
    if (next === CUSTOM_SENTINEL) {
      userPickedCustom = true;
      value = '';
      // Focus the reveal-on-Custom input so the user can start typing
      // immediately. The input isn't in the DOM until the next render,
      // so defer via queueMicrotask.
      queueMicrotask(() => customInput?.focus());
    } else {
      userPickedCustom = false;
      value = next;
    }
  }
</script>

<div class="flex flex-col gap-1">
  <select
    class="rounded border border-slate-800 bg-slate-950 px-2 py-2 font-mono text-sm
      focus:border-slate-600 focus:outline-none"
    value={selectValue}
    onchange={onSelectChange}
    aria-label="Model"
  >
    <option value="" disabled>— choose a model —</option>
    {#each KNOWN_MODELS as model (model)}
      <option value={model}>{model}</option>
    {/each}
    <option value={CUSTOM_SENTINEL}>Custom…</option>
  </select>
  {#if showCustomInput}
    <input
      bind:this={customInput}
      type="text"
      class="rounded border border-slate-800 bg-slate-950 px-2 py-2 font-mono text-sm
        focus:border-slate-600 focus:outline-none"
      {placeholder}
      bind:value
      aria-label="Custom model id"
    />
  {/if}
</div>
