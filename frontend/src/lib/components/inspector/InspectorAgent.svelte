<script lang="ts">
  /**
   * Agent subsection — exposes the active session's executor-side
   * configuration in a longer-form layout than the conversation
   * header's compact row.
   *
   * Behavior anchors:
   *
   * - ``docs/architecture-v1.md`` §1.2 enumerates this component as
   *   ``InspectorAgent.svelte`` under ``components/inspector/``.
   * - ``docs/behavior/chat.md`` §"opens an existing chat" cross-references
   *   the inspector pane; the conversation header band ("title, severity
   *   shield, attached tag chips, … executor model dropdown, total-cost
   *   / context-window indicator, and a quota bar pair") is a compact
   *   summary surface — the inspector renders the same fields with the
   *   labels the user can read at a glance.
   *
   * Fields shown today come from :class:`SessionOut` per
   * ``api/sessions.ts``: ``model``, ``permission_mode``, ``working_dir``,
   * ``max_budget_usd``, ``total_cost_usd``, ``message_count``. Item 2.6
   * widens the row with the routing-spec fields (``advisor``,
   * ``effort``, ``fallback_model``, ``beta_headers``) — chat.md is silent
   * on the user-facing copy of those, so item 2.6's spec-governed
   * wiring lives in :class:`InspectorRouting` per arch §1.2's split.
   *
   * Work evidence (T2-08) — ``GET /api/sessions/{id}/work_evidence``
   * exposes bash/write/edit call counts and an optional ``git diff
   * --stat`` for the session's working directory. Loaded on mount and
   * refreshed when the session id changes.
   */
  import { INSPECTOR_STRINGS, NEW_SESSION_STRINGS } from "../../config";
  import { getWorkEvidence, type SessionOut, type WorkEvidenceOut } from "../../api/sessions";

  interface Props {
    session: SessionOut;
  }

  const { session }: Props = $props();

  // ---- work evidence (T2-08) -----------------------------------------------

  let workEvidence = $state<WorkEvidenceOut | null>(null);
  let workEvidenceError = $state(false);
  let workEvidenceLoading = $state(false);

  $effect(() => {
    // Re-fetch whenever the session changes.
    const sid = session.id;
    workEvidence = null;
    workEvidenceError = false;
    workEvidenceLoading = true;
    getWorkEvidence(sid)
      .then((ev) => {
        workEvidence = ev;
      })
      .catch(() => {
        workEvidenceError = true;
      })
      .finally(() => {
        workEvidenceLoading = false;
      });
  });

  /**
   * Map a backend wire model name to the user-facing label the
   * new-session dialog uses (chat.md §"creates a chat" pins the
   * displayed names — keeping the two surfaces in sync via the same
   * string table). An unknown wire value falls back to the raw string
   * so a future model id renders as itself rather than blanking.
   */
  const modelLabel = $derived(
    NEW_SESSION_STRINGS.executorLabels[
      session.model as keyof typeof NEW_SESSION_STRINGS.executorLabels
    ] ?? session.model,
  );

  // ``max_budget_usd`` / ``total_cost_usd`` round to two decimals so
  // the user reads "1.23" rather than the wire's full float (the
  // backend stores cents; the float conversion adds floating-point
  // noise that distracts from the magnitude).
  function formatUsd(value: number): string {
    return value.toFixed(2);
  }
</script>

<section class="inspector-agent flex flex-col gap-3" data-testid="inspector-agent">
  <h3 class="text-xs font-semibold uppercase tracking-wider text-fg-muted">
    {INSPECTOR_STRINGS.agentHeading}
  </h3>

  <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
    <dt class="text-fg-muted">{INSPECTOR_STRINGS.agentModelLabel}</dt>
    <dd class="font-mono text-fg" data-testid="inspector-agent-model">
      {modelLabel}
    </dd>

    <dt class="text-fg-muted">{INSPECTOR_STRINGS.agentPermissionModeLabel}</dt>
    <dd class="font-mono text-fg" data-testid="inspector-agent-permission-mode">
      {session.permission_mode ?? INSPECTOR_STRINGS.agentPermissionModeUnset}
    </dd>

    <dt class="text-fg-muted">{INSPECTOR_STRINGS.agentWorkingDirLabel}</dt>
    <dd class="break-all font-mono text-fg" data-testid="inspector-agent-working-dir">
      {session.working_dir}
    </dd>

    <dt class="text-fg-muted">{INSPECTOR_STRINGS.agentMaxBudgetLabel}</dt>
    <dd class="font-mono text-fg" data-testid="inspector-agent-max-budget">
      {session.max_budget_usd === null
        ? INSPECTOR_STRINGS.agentMaxBudgetUnset
        : formatUsd(session.max_budget_usd)}
    </dd>

    <dt class="text-fg-muted">{INSPECTOR_STRINGS.agentTotalCostLabel}</dt>
    <dd class="font-mono text-fg" data-testid="inspector-agent-total-cost">
      {formatUsd(session.total_cost_usd)}
    </dd>

    <dt class="text-fg-muted">{INSPECTOR_STRINGS.agentMessageCountLabel}</dt>
    <dd class="font-mono text-fg" data-testid="inspector-agent-message-count">
      {session.message_count}
    </dd>
  </dl>

  <!-- Work evidence (T2-08) -->
  <h4 class="text-xs font-semibold uppercase tracking-wider text-fg-muted">
    {INSPECTOR_STRINGS.agentWorkEvidenceHeading}
  </h4>

  {#if workEvidenceLoading}
    <p class="text-xs text-fg-muted" data-testid="inspector-agent-work-evidence-loading">
      {INSPECTOR_STRINGS.agentWorkEvidenceLoading}
    </p>
  {:else if workEvidenceError}
    <p class="text-xs text-fg-error" data-testid="inspector-agent-work-evidence-error">
      {INSPECTOR_STRINGS.agentWorkEvidenceError}
    </p>
  {:else if workEvidence !== null}
    <dl
      class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm"
      data-testid="inspector-agent-work-evidence"
    >
      <dt class="text-fg-muted">{INSPECTOR_STRINGS.agentWorkEvidenceBashLabel}</dt>
      <dd class="font-mono text-fg" data-testid="inspector-agent-work-evidence-bash">
        {workEvidence.bash_calls}
      </dd>

      <dt class="text-fg-muted">{INSPECTOR_STRINGS.agentWorkEvidenceWriteLabel}</dt>
      <dd class="font-mono text-fg" data-testid="inspector-agent-work-evidence-write">
        {workEvidence.write_calls}
      </dd>

      <dt class="text-fg-muted">{INSPECTOR_STRINGS.agentWorkEvidenceEditLabel}</dt>
      <dd class="font-mono text-fg" data-testid="inspector-agent-work-evidence-edit">
        {workEvidence.edit_calls}
      </dd>

      <dt class="text-fg-muted">{INSPECTOR_STRINGS.agentWorkEvidenceTotalLabel}</dt>
      <dd class="font-mono text-fg" data-testid="inspector-agent-work-evidence-total">
        {workEvidence.total_work_tool_calls}
      </dd>

      {#if workEvidence.git_diff_available && workEvidence.git_diff_stat}
        <dt class="text-fg-muted">{INSPECTOR_STRINGS.agentWorkEvidenceGitDiffLabel}</dt>
        <dd
          class="break-all font-mono text-fg"
          data-testid="inspector-agent-work-evidence-git-diff"
        >
          <pre class="whitespace-pre-wrap text-xs">{workEvidence.git_diff_stat}</pre>
        </dd>
      {:else if workEvidence.git_diff_available === false}
        <dt class="text-fg-muted">{INSPECTOR_STRINGS.agentWorkEvidenceGitDiffLabel}</dt>
        <dd class="text-fg-muted" data-testid="inspector-agent-work-evidence-git-diff-unavailable">
          {INSPECTOR_STRINGS.agentWorkEvidenceGitDiffUnavailable}
        </dd>
      {/if}
    </dl>
  {/if}
</section>
