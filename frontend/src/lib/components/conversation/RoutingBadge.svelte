<script lang="ts">
  /**
   * Per-message routing badge — small chip in the corner of an
   * assistant bubble.
   *
   * Per spec §5: "Sonnet" / "Sonnet → Opus×2" / "Haiku → Opus×1" /
   * "Opus xhigh" labels. The full routing reason rides in a tooltip
   * (``title`` attribute for the v1 surface; richer hover popovers
   * are a later item).
   *
   * Per arch §1.2 ``RoutingBadge.svelte`` is one of the conversation
   * cluster's NEW components; it lives alongside ``MessageTurn``.
   */
  import { CONVERSATION_STRINGS } from "../../config";
  import type { TurnRouting } from "../../stores/conversation.svelte";

  interface Props {
    routing: TurnRouting;
  }

  const { routing }: Props = $props();

  const label = $derived(buildLabel(routing));
  const tooltip = $derived(
    routing.routingReason || CONVERSATION_STRINGS.routingBadgeTooltipFallback,
  );

  function buildLabel(r: TurnRouting): string {
    const head = capitalize(r.executorModel);
    if (r.advisorModel === null || r.advisorCallsCount === 0) {
      const effort = effortSuffix(r.effortLevel);
      return effort.length > 0 ? `${head} ${effort}` : head;
    }
    const advisor = capitalize(r.advisorModel);
    return `${head} → ${advisor}×${r.advisorCallsCount}`;
  }

  function capitalize(model: string): string {
    if (model.length === 0) {
      return model;
    }
    return model.charAt(0).toUpperCase() + model.slice(1);
  }

  function effortSuffix(effort: string): string {
    if (effort === "" || effort === "med" || effort === "medium") {
      return "";
    }
    return effort;
  }
</script>

<span
  class="rounded bg-surface-2 px-1.5 py-0.5 text-xs font-medium text-fg-muted"
  data-testid="routing-badge"
  data-executor-model={routing.executorModel}
  data-advisor-model={routing.advisorModel ?? ""}
  title={tooltip}
>
  {label}
</span>
