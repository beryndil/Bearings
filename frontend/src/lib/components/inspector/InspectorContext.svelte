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
   * - ``docs/behavior/chat.md`` §"Context" — below the grid an
   *   "Assembled context" section shows the system-prompt layer
   *   breakdown summary, wired to
   *   ``GET /api/sessions/{id}/system_prompt``.
   */
  import { INSPECTOR_STRINGS } from "../../config";
  import type { SessionOut, SystemPromptLayersOut } from "../../api/sessions";
  import { getSessionSystemPrompt } from "../../api/sessions";

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

  // ---- assembled-context fetch -------------------------------------------

  type AssembledLoadState = "loading" | "ready" | "error";

  let assembledState: AssembledLoadState = $state("loading");
  let assembledData = $state<SystemPromptLayersOut | null>(null);

  $effect(() => {
    const id = session.id;
    assembledState = "loading";
    assembledData = null;
    getSessionSystemPrompt(id)
      .then((out) => {
        assembledData = out;
        assembledState = "ready";
      })
      .catch(() => {
        assembledState = "error";
      });
  });

  /**
   * Present layers in the same order InspectorInstructions uses so the
   * two subsections are consistent. Unknown kinds fall through after the
   * known set.
   */
  const LAYER_ORDER: ReadonlyArray<string> = [
    "session_instructions",
    "baseline",
    "project_claude_md",
    "user_claude_md",
    "user_rules_md",
    "tag_claude_md",
    "tag_memory",
    "template_baseline",
  ];

  const sortedLayers = $derived(
    (assembledData?.layers ?? []).slice().sort((a, b) => {
      const ai = LAYER_ORDER.indexOf(a.kind);
      const bi = LAYER_ORDER.indexOf(b.kind);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    }),
  );

  function kindLabel(kind: string): string {
    const labels = INSPECTOR_STRINGS.instructionsLayerKindLabels as Record<string, string>;
    return labels[kind] ?? kind;
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

    {#if assembledState === "loading"}
      <p class="text-xs text-fg-muted" data-testid="inspector-context-assembled-loading">
        {INSPECTOR_STRINGS.contextAssembledLoading}
      </p>
    {:else if assembledState === "error"}
      <p class="text-xs text-fg-error" data-testid="inspector-context-assembled-error">
        {INSPECTOR_STRINGS.contextAssembledError}
      </p>
    {:else if assembledData !== null}
      <dl
        class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs"
        data-testid="inspector-context-assembled-layers"
      >
        {#each sortedLayers as layer (layer.kind)}
          <dt class="text-fg-muted">{kindLabel(layer.kind)}</dt>
          <dd class="font-mono text-fg" data-testid={`inspector-context-assembled-${layer.kind}`}>
            {INSPECTOR_STRINGS.instructionsLayerTokensLabel(layer.token_count)}
            {#if layer.source_path}
              <span class="truncate text-fg-muted" title={layer.source_path}>
                · {layer.source_path}
              </span>
            {/if}
          </dd>
        {/each}

        <dt class="border-t border-border pt-1 text-fg-muted">
          {INSPECTOR_STRINGS.contextAssembledTotalLabel}
        </dt>
        <dd
          class="border-t border-border pt-1 font-mono text-fg"
          data-testid="inspector-context-assembled-total"
        >
          {INSPECTOR_STRINGS.instructionsLayerTokensLabel(assembledData.total_tokens)}
        </dd>
      </dl>
    {/if}
  </section>
</section>
