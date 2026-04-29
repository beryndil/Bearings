<script lang="ts">
  /**
   * Context subsection — surfaces the active session's *contextual*
   * metadata: title, description, last context-window pressure /
   * tokens / max. These are the fields that describe what the agent
   * has been *given* this turn rather than how it is configured (the
   * Agent subsection's territory).
   *
   * Behavior anchors:
   *
   * - ``docs/architecture-v1.md`` §1.2 enumerates this component as
   *   ``InspectorContext.svelte`` under ``components/inspector/``.
   * - ``docs/behavior/chat.md`` §"opens an existing chat" lists the
   *   header band's "total-cost / context-window indicator" — the
   *   inspector renders the same context-window numbers in long form,
   *   plus the title / description that the sidebar row truncates.
   *
   * The "assembled context" pieces (system prompt, tag-default
   * overlays per item 1.4, vault attachments per item 1.5) are gated
   * on the per-session assembly API which lands in those items'
   * scopes; this component renders a placeholder paragraph there so
   * the visual structure is in place when those endpoints arrive. Doc
   * gap recorded in the executor's self-verification — chat.md is
   * silent on this subsection's exact copy, so the placeholder text
   * is provisional pending a doc augmentation per plan §"Behavioral
   * gap escalation".
   */
  import { INSPECTOR_STRINGS } from "../../config";
  import type { SessionOut } from "../../api/sessions";

  interface Props {
    session: SessionOut;
  }

  const { session }: Props = $props();

  /**
   * The wire shape carries the most-recent context-pressure as a
   * fraction in ``[0, 1]``; the user-facing display is a percentage
   * with no decimal. ``null`` means "no turn observed yet" — render
   * the documented copy rather than ``0%`` (which would suggest the
   * agent has run and is at idle).
   */
  function formatPct(fraction: number | null): string {
    if (fraction === null) {
      return INSPECTOR_STRINGS.contextLastContextNotSeen;
    }
    return `${Math.round(fraction * 100)}%`;
  }

  function formatTokens(value: number | null): string {
    if (value === null) {
      return INSPECTOR_STRINGS.contextLastContextNotSeen;
    }
    return value.toLocaleString();
  }
</script>

<section class="inspector-context flex flex-col gap-3" data-testid="inspector-context">
  <h3 class="text-xs font-semibold uppercase tracking-wider text-fg-muted">
    {INSPECTOR_STRINGS.contextHeading}
  </h3>

  <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
    <dt class="text-fg-muted">{INSPECTOR_STRINGS.contextSessionTitleLabel}</dt>
    <dd class="text-fg" data-testid="inspector-context-title">{session.title}</dd>

    <dt class="text-fg-muted">{INSPECTOR_STRINGS.contextDescriptionLabel}</dt>
    <dd class="whitespace-pre-wrap text-fg" data-testid="inspector-context-description">
      {session.description ?? INSPECTOR_STRINGS.contextDescriptionEmpty}
    </dd>

    <dt class="text-fg-muted">{INSPECTOR_STRINGS.contextLastContextPctLabel}</dt>
    <dd class="font-mono text-fg" data-testid="inspector-context-last-pct">
      {formatPct(session.last_context_pct)}
    </dd>

    <dt class="text-fg-muted">{INSPECTOR_STRINGS.contextLastContextTokensLabel}</dt>
    <dd class="font-mono text-fg" data-testid="inspector-context-last-tokens">
      {formatTokens(session.last_context_tokens)}
    </dd>

    <dt class="text-fg-muted">{INSPECTOR_STRINGS.contextLastContextMaxLabel}</dt>
    <dd class="font-mono text-fg" data-testid="inspector-context-last-max">
      {formatTokens(session.last_context_max)}
    </dd>
  </dl>

  <section
    class="inspector-context__assembled flex flex-col gap-1"
    data-testid="inspector-context-assembled"
  >
    <h4 class="text-xs font-semibold uppercase tracking-wider text-fg-muted">
      {INSPECTOR_STRINGS.contextAssembledHeading}
    </h4>
    <p class="text-fg-muted">{INSPECTOR_STRINGS.contextAssembledPlaceholder}</p>
  </section>
</section>
