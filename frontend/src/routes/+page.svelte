<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import AuthGate from '$lib/components/AuthGate.svelte';
  import Conversation from '$lib/components/Conversation.svelte';
  import Inspector from '$lib/components/Inspector.svelte';
  import SessionList from '$lib/components/SessionList.svelte';
  import { agent } from '$lib/agent.svelte';
  import { auth } from '$lib/stores/auth.svelte';
  import { sessions } from '$lib/stores/sessions.svelte';

  let booted = $state(false);

  async function boot() {
    if (booted) return;
    booted = true;
    await sessions.refresh();
    if (sessions.selectedId) await agent.connect(sessions.selectedId);
  }

  onMount(async () => {
    await auth.check();
    if (auth.status === 'open' || auth.status === 'ok') await boot();
  });

  // Re-trigger once the user clears the gate.
  $effect(() => {
    if ((auth.status === 'open' || auth.status === 'ok') && !booted) boot();
  });
</script>

<AuthGate />
<main class="grid h-full grid-cols-[280px_1fr_320px]">
  <SessionList />
  <Conversation />
  <Inspector />
</main>
