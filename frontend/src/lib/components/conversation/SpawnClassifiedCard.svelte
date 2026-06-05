<script lang="ts">
  /**
   * Warning banner rendered above the conversation body when the session
   * has been classified as containing sensitive data (T3-03).
   *
   * Behavior anchors:
   *
   * - Reads ``SessionOut.classified`` (set by
   *   ``POST /api/sessions/{id}/spawn_classify`` — T2-07). This banner
   *   is purely informational — no PATCH is made from here.
   * - The banner is dismissible per-session via a local ``$state`` flag
   *   (not persisted; reappears on page reload). The ``classified`` DB
   *   flag itself stays set until a new spawn_classify scan returns
   *   ``classified: false``.
   * - Rendered by :class:`Conversation` above the ``<div class="relative
   *   flex-1 overflow-hidden">`` wrapper so it appears between the
   *   AccentCards and the message list.
   *
   * The ``classified`` prop is derived from the sessions store; the
   * parent passes it so this component stays presentational.
   */
  import { CLASSIFIED_CARD_STRINGS } from "../../config";

  interface Props {
    /** ``true`` when the session's ``classified`` flag is set. */
    classified: boolean;
  }

  const { classified }: Props = $props();

  /** Local dismissal flag — hidden until next page load when dismissed. */
  let dismissed = $state(false);
</script>

{#if classified && !dismissed}
  <div
    class="classified-card flex items-start gap-2 border-b border-amber-600/30 bg-amber-900/10 px-4 py-2"
    role="alert"
    data-testid="spawn-classified-card"
    aria-label={CLASSIFIED_CARD_STRINGS.ariaLabel}
  >
    <span class="mt-0.5 shrink-0 text-amber-500" aria-hidden="true">⚠</span>
    <div class="flex-1 min-w-0">
      <p class="text-sm font-medium text-amber-500">
        {CLASSIFIED_CARD_STRINGS.title}
      </p>
      <p class="text-xs text-amber-400/80">
        {CLASSIFIED_CARD_STRINGS.description}
      </p>
    </div>
    <button
      type="button"
      class="shrink-0 rounded px-1.5 py-0.5 text-xs text-amber-500/70 hover:bg-amber-800/20 hover:text-amber-400"
      aria-label={CLASSIFIED_CARD_STRINGS.dismissAriaLabel}
      data-testid="classified-card-dismiss"
      onclick={() => {
        dismissed = true;
      }}
    >
      {CLASSIFIED_CARD_STRINGS.dismissLabel}
    </button>
  </div>
{/if}
