<script lang="ts" module>
  import {
    AUTO_DRIVER_FAILURE_POLICY_HALT,
    AUTO_DRIVER_FAILURE_POLICY_SKIP,
    AUTO_DRIVER_STATE_FINISHED,
    AUTO_DRIVER_STATE_IDLE,
    AUTO_DRIVER_STATE_PAUSED,
    AUTO_DRIVER_STATE_RUNNING,
    CHECKLIST_STRINGS,
    DRIVER_OUTCOME_HALTED_EMPTY,
  } from "../../config";
  import type { AutoDriverRunOut } from "../../api/checklists";

  /**
   * Format the status line per behavior/checklists.md §"Run-control
   * surface". Exported as a pure function so the unit tests assert
   * the template substitution without mounting the component.
   *
   * Parameters:
   * - ``run`` — the active run row (or ``null`` when no run has been
   *   recorded for the checklist yet);
   * - ``totalItems`` — total items the checklist contains (used as
   *   the denominator);
   * - ``currentIndex`` — 1-based index of the current item in the
   *   sort-order walk, or 0 when no item is in flight.
   */
  export function formatStatusLine(
    run: AutoDriverRunOut | null,
    totalItems: number,
    currentIndex: number,
  ): string {
    if (run === null || run.state === AUTO_DRIVER_STATE_IDLE) {
      return CHECKLIST_STRINGS.runStatusIdle;
    }
    const failures = run.items_failed;
    const completed = run.items_completed;
    const legs = run.legs_spawned;
    if (run.state === AUTO_DRIVER_STATE_RUNNING) {
      return CHECKLIST_STRINGS.runStatusRunningTemplate
        .replace("{currentIndex}", String(currentIndex))
        .replace("{total}", String(totalItems))
        .replace("{legs}", String(legs))
        .replace("{failures}", String(failures));
    }
    if (run.state === AUTO_DRIVER_STATE_PAUSED) {
      return CHECKLIST_STRINGS.runStatusPausedTemplate
        .replace("{completed}", String(completed))
        .replace("{total}", String(totalItems))
        .replace("{failures}", String(failures));
    }
    // Finished / errored — show the outcome text frozen on the line.
    if (run.state === AUTO_DRIVER_STATE_FINISHED) {
      const outcome = run.outcome ?? DRIVER_OUTCOME_HALTED_EMPTY;
      return CHECKLIST_STRINGS.runStatusOutcomeTemplate
        .replace("{outcome}", outcome)
        .replace("{completed}", String(completed))
        .replace("{total}", String(totalItems))
        .replace("{failures}", String(failures));
    }
    // Errored.
    return CHECKLIST_STRINGS.runStatusOutcomeTemplate
      .replace("{outcome}", run.outcome ?? "Errored")
      .replace("{completed}", String(completed))
      .replace("{total}", String(totalItems))
      .replace("{failures}", String(failures));
  }

  /**
   * Compute the 1-based current-item index from the active run +
   * the items list (sorted in display order). 0 when no current
   * item is set.
   */
  export function currentItemIndex(
    run: AutoDriverRunOut | null,
    sortedItemIds: readonly number[],
  ): number {
    if (run === null || run.current_item_id === null) return 0;
    const idx = sortedItemIds.indexOf(run.current_item_id);
    return idx === -1 ? 0 : idx + 1;
  }

  export const FAILURE_POLICIES = [
    AUTO_DRIVER_FAILURE_POLICY_HALT,
    AUTO_DRIVER_FAILURE_POLICY_SKIP,
  ] as const;
</script>

<script lang="ts">
  /**
   * AutoDriverControls — the run-control widget inside the checklist
   * pane's header band.
   *
   * Behavior anchors:
   *
   * - ``docs/behavior/checklists.md`` §"Run-control surface" — the
   *   Start / Stop / Pause / Skip controls + the status line ticker
   *   live on the checklist's header. Pause is an alias for Stop in
   *   v1 (per the same §). Failure-policy + visit-existing toggles
   *   apply to the next Start.
   * - ``docs/behavior/checklists.md`` §"When the user starts /
   *   pauses / stops a run" — the empty-checklist Start path flashes
   *   ``Halted: empty`` and the Start control re-enables.
   * - ``docs/behavior/keyboard-shortcuts.md`` — global chords are
   *   defined elsewhere; the controls are mouse-driven.
   *
   * Layer rules: write helpers (``startRun`` / ``stopRun`` / etc.)
   * are injected so unit tests don't monkey-patch the api module.
   */
  import type { AutoDriverFailurePolicy } from "../../config";
  import {
    pauseChecklistRun as pauseRunDefault,
    resumeChecklistRun as resumeRunDefault,
    skipCurrentChecklistRun as skipRunDefault,
    startChecklistRun as startRunDefault,
    stopChecklistRun as stopRunDefault,
  } from "../../api/checklists";

  interface Props {
    checklistId: string;
    /** Active-run row from the overview fetch; ``null`` for "no run yet". */
    activeRun: AutoDriverRunOut | null;
    /** Total checklist items (for the status line denominator). */
    totalItems: number;
    /** Items in display order — used to derive the 1-based current index. */
    sortedItemIds: readonly number[];
    /** Called after every successful write so the parent re-fetches. */
    onChange?: () => void;
    /** Test-injectable. */
    startRun?: typeof startRunDefault;
    /** Test-injectable. */
    stopRun?: typeof stopRunDefault;
    /** Test-injectable. */
    pauseRun?: typeof pauseRunDefault;
    /** Test-injectable. */
    resumeRun?: typeof resumeRunDefault;
    /** Test-injectable. */
    skipRun?: typeof skipRunDefault;
  }

  const {
    checklistId,
    activeRun,
    totalItems,
    sortedItemIds,
    onChange = () => {},
    startRun = startRunDefault,
    stopRun = stopRunDefault,
    pauseRun = pauseRunDefault,
    resumeRun = resumeRunDefault,
    skipRun = skipRunDefault,
  }: Props = $props();

  let busy = $state(false);
  let error = $state<string | null>(null);
  let failurePolicy = $state<AutoDriverFailurePolicy>(AUTO_DRIVER_FAILURE_POLICY_HALT);
  let visitExisting = $state(false);

  // The state-derived enable flags. ``runState === undefined`` is
  // collapsed to ``idle`` so the Start control enables on a fresh
  // checklist (no run row yet).
  const runState = $derived(activeRun?.state ?? AUTO_DRIVER_STATE_IDLE);
  const canStart = $derived(
    runState === AUTO_DRIVER_STATE_IDLE || runState === AUTO_DRIVER_STATE_FINISHED,
  );
  const canStop = $derived(runState === AUTO_DRIVER_STATE_RUNNING);
  const canPause = $derived(runState === AUTO_DRIVER_STATE_RUNNING);
  const canResume = $derived(runState === AUTO_DRIVER_STATE_PAUSED);
  const canSkip = $derived(runState === AUTO_DRIVER_STATE_RUNNING);

  const statusLine = $derived(
    formatStatusLine(activeRun, totalItems, currentItemIndex(activeRun, sortedItemIds)),
  );

  async function safeCall(fn: () => Promise<unknown>): Promise<void> {
    if (busy) return;
    busy = true;
    error = null;
    try {
      await fn();
      onChange();
    } catch (caught) {
      error = caught instanceof Error ? caught.message : "run-control call failed";
    } finally {
      busy = false;
    }
  }
</script>

<section
  class="auto-driver-controls flex flex-col gap-2"
  data-testid="auto-driver-controls"
  aria-label={CHECKLIST_STRINGS.runControlsAriaLabel}
>
  <div class="auto-driver-controls__row flex flex-row items-center gap-2">
    {#if canStart}
      <button
        type="button"
        class="auto-driver-controls__start rounded bg-surface-2 px-2 py-1 text-sm"
        data-testid="auto-driver-start"
        disabled={busy}
        onclick={() =>
          safeCall(() =>
            startRun(checklistId, {
              failure_policy: failurePolicy,
              visit_existing: visitExisting,
            }),
          )}
      >
        {CHECKLIST_STRINGS.runStartLabel}
      </button>
    {/if}

    {#if canStop}
      <button
        type="button"
        class="auto-driver-controls__stop rounded bg-surface-2 px-2 py-1 text-sm"
        data-testid="auto-driver-stop"
        disabled={busy}
        onclick={() => safeCall(() => stopRun(checklistId))}
      >
        {CHECKLIST_STRINGS.runStopLabel}
      </button>
    {/if}

    {#if canPause}
      <button
        type="button"
        class="auto-driver-controls__pause rounded bg-surface-2 px-2 py-1 text-sm"
        data-testid="auto-driver-pause"
        disabled={busy}
        onclick={() => safeCall(() => pauseRun(checklistId))}
      >
        {CHECKLIST_STRINGS.runPauseLabel}
      </button>
    {/if}

    {#if canResume}
      <button
        type="button"
        class="auto-driver-controls__resume rounded bg-surface-2 px-2 py-1 text-sm"
        data-testid="auto-driver-resume"
        disabled={busy}
        onclick={() => safeCall(() => resumeRun(checklistId))}
      >
        {CHECKLIST_STRINGS.runResumeLabel}
      </button>
    {/if}

    {#if canSkip}
      <button
        type="button"
        class="auto-driver-controls__skip rounded bg-surface-2 px-2 py-1 text-sm"
        data-testid="auto-driver-skip"
        disabled={busy}
        onclick={() => safeCall(() => skipRun(checklistId))}
      >
        {CHECKLIST_STRINGS.runSkipCurrentLabel}
      </button>
    {/if}

    <label class="ml-auto flex items-center gap-1 text-xs text-fg-muted">
      <span>{CHECKLIST_STRINGS.runFailurePolicyLabel}:</span>
      <select
        class="auto-driver-controls__failure-policy rounded bg-surface-2 px-1 py-0.5"
        data-testid="auto-driver-failure-policy"
        bind:value={failurePolicy}
        disabled={!canStart || busy}
      >
        {#each FAILURE_POLICIES as policy (policy)}
          <option value={policy}>
            {policy === AUTO_DRIVER_FAILURE_POLICY_HALT
              ? CHECKLIST_STRINGS.runFailurePolicyHaltLabel
              : CHECKLIST_STRINGS.runFailurePolicySkipLabel}
          </option>
        {/each}
      </select>
    </label>

    <label
      class="flex items-center gap-1 text-xs text-fg-muted"
      title={CHECKLIST_STRINGS.runVisitExistingTitle}
    >
      <input
        type="checkbox"
        data-testid="auto-driver-visit-existing"
        bind:checked={visitExisting}
        disabled={!canStart || busy}
      />
      <span>{CHECKLIST_STRINGS.runVisitExistingLabel}</span>
    </label>
  </div>

  <p class="auto-driver-controls__status text-xs text-fg-muted" data-testid="auto-driver-status">
    {statusLine}
  </p>

  {#if error !== null}
    <p class="auto-driver-controls__error text-xs text-red-400" data-testid="auto-driver-error">
      {error}
    </p>
  {/if}
</section>
