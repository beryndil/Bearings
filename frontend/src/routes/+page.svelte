<script lang="ts">
  import '../app.css';
  import SessionList from '$lib/components/SessionList.svelte';
  import Conversation from '$lib/components/Conversation.svelte';
  import Inspector from '$lib/components/Inspector.svelte';
</script>

<main class="grid h-full grid-cols-[280px_1fr_320px]">
  <SessionList />
  <Conversation />
  <Inspector />
</main>
