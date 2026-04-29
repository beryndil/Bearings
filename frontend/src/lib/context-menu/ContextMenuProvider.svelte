<script lang="ts">
  /**
   * Context-menu provider — mounts the floating menu component once at
   * the app shell. Consumers don't import this; they wire
   * ``use:contextMenu`` from :file:`actions/contextMenu.ts` which
   * dispatches into the same store the menu reads from.
   *
   * The provider re-exports its ``children`` slot unchanged — it is a
   * cross-cutting concern, like :class:`ThemeProvider.svelte`.
   */
  import type { Snippet } from "svelte";

  import ContextMenu from "./ContextMenu.svelte";

  interface Props {
    children?: Snippet;
  }

  const { children }: Props = $props();
</script>

{#if children}
  {@render children()}
{/if}

<ContextMenu />
