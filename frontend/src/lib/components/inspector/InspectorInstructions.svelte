<script lang="ts">
  /**
   * Instructions subsection — exposes the active session's
   * user-customisable instructions (``session_instructions`` on
   * :class:`SessionOut`). When the field is ``null`` or empty the
   * component renders the documented empty-state copy rather than a
   * blank pre-block.
   *
   * Behavior anchors:
   *
   * - ``docs/architecture-v1.md`` §1.2 enumerates this component as
   *   ``InspectorInstructions.svelte`` under ``components/inspector/``.
   * - ``docs/behavior/chat.md`` carries the per-session-instructions
   *   field implicitly via the session shape (see ``SessionOut``);
   *   chat.md does not yet describe an in-app editor for the field.
   *   Item 2.5 ships read-only rendering; an editor is deferred to
   *   later items (the v0.17.x parity surface for editing the field
   *   lived in the SessionEdit modal — see ``components/modals/`` per
   *   arch §1.2).
   *
   * The pre-block uses ``whitespace-pre-wrap`` so multi-line
   * instructions render with their original line breaks while still
   * wrapping at the column edge — matches the conversation pane's
   * behaviour on long lines per chat.md §"Conversation rendering".
   */
  import { INSPECTOR_STRINGS } from "../../config";
  import type { SessionOut } from "../../api/sessions";

  interface Props {
    session: SessionOut;
  }

  const { session }: Props = $props();

  // ``session_instructions`` is ``string | null`` on the wire. An empty
  // string is treated the same as ``null`` for display purposes — both
  // render the empty-state copy. Whitespace-only strings are also
  // treated as empty so a stray newline doesn't masquerade as content.
  const trimmed = $derived(session.session_instructions?.trim() ?? "");
  const hasInstructions = $derived(trimmed.length > 0);
</script>

<section class="inspector-instructions flex flex-col gap-3" data-testid="inspector-instructions">
  <h3 class="text-xs font-semibold uppercase tracking-wider text-fg-muted">
    {INSPECTOR_STRINGS.instructionsHeading}
  </h3>

  {#if hasInstructions}
    <pre
      class="inspector-instructions__body whitespace-pre-wrap break-words rounded border border-border bg-surface-2 p-2 font-mono text-xs text-fg"
      data-testid="inspector-instructions-body"
      aria-label={INSPECTOR_STRINGS.instructionsBodyLabel}>{session.session_instructions}</pre>
  {:else}
    <p class="text-fg-muted" data-testid="inspector-instructions-empty">
      {INSPECTOR_STRINGS.instructionsEmpty}
    </p>
  {/if}
</section>
