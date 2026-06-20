<script lang="ts">
  /**
   * Instructions subsection — renders the full assembled system-prompt
   * layer breakdown for the active session.  Each layer appears as a
   * clickable card showing the kind label, optional source path, and
   * approximate token count.  Clicking a card opens a dedicated editor
   * or viewer modal for that layer:
   *
   * - ``session_instructions`` → ``SessionInstructionsModal`` (editable).
   * - Filesystem-sourced layers (``source_path`` set) → ``ClaudemdEdit``
   *   (editable file write via PUT layer endpoint).
   * - ``baseline``, ``tag_memory``, ``template_baseline`` → ``LayerViewModal``
   *   (read-only view with contextual note).
   *
   * Behavior anchors:
   * - ``docs/behavior/chat.md`` §"System-prompt layers contract" —
   *   layer kinds, display order, and empty-state rules.
   * - ``docs/architecture-v1.md`` §1.2 — component registered as
   *   ``InspectorInstructions.svelte`` under ``components/inspector/``.
   */
  import { INSPECTOR_STRINGS } from "../../config";
  import type { SessionOut, SystemPromptLayer } from "../../api/sessions";
  import { getSessionSystemPrompt } from "../../api/sessions";
  import { refreshSessions } from "../../stores/sessions.svelte";
  import { currentFilter } from "../../stores/tags.svelte";
  import ClaudemdEdit from "../modals/ClaudemdEdit.svelte";
  import SessionInstructionsModal from "../modals/SessionInstructionsModal.svelte";
  import LayerViewModal from "../modals/LayerViewModal.svelte";

  interface Props {
    session: SessionOut;
  }

  const { session }: Props = $props();

  // ---- layer kinds in display order -------------------------------------

  type LayerKind =
    | "session_instructions"
    | "baseline"
    | "project_claude_md"
    | "user_claude_md"
    | "user_rules_md"
    | "tag_claude_md"
    | "tag_memory"
    | "template_baseline";

  /**
   * Display order follows splice order: per-session first, then filesystem
   * sources (baseline, project, user, per-tag CLAUDE.md, per-tag rules),
   * then DB-resident memory rows, then template baseline.
   * ``tag_claude_md`` sits before ``tag_memory`` because the backend
   * splices per-tag CLAUDE.md blocks before memory rows so that memory
   * bodies win on any directive conflicts (docs/behavior/memories.md
   * §"System-prompt injection").
   */
  const LAYER_DISPLAY_ORDER: readonly LayerKind[] = [
    "session_instructions",
    "baseline",
    "project_claude_md",
    "user_claude_md",
    "user_rules_md",
    "tag_claude_md",
    "tag_memory",
    "template_baseline",
  ] as const;

  // ---- system-prompt layers state ---------------------------------------

  let layersLoading = $state(true);
  let layersError = $state(false);
  let allLayers = $state<SystemPromptLayer[]>([]);

  $effect(() => {
    const id = session.id;
    layersLoading = true;
    layersError = false;
    allLayers = [];
    getSessionSystemPrompt(id)
      .then((out) => {
        allLayers = out.layers;
        layersLoading = false;
      })
      .catch(() => {
        layersError = true;
        layersLoading = false;
      });
  });

  // Group layers by kind (derived so it re-computes when allLayers changes).
  const layersByKind = $derived(
    Object.fromEntries(
      LAYER_DISPLAY_ORDER.map((kind) => [kind, allLayers.filter((l) => l.kind === kind)]),
    ) as Record<LayerKind, SystemPromptLayer[]>,
  );

  // ---- layer re-fetch helper -------------------------------------------

  async function refetchLayers(): Promise<void> {
    try {
      const out = await getSessionSystemPrompt(session.id);
      allLayers = out.layers;
    } catch {
      // Non-fatal — stale layers are acceptable until next mount.
    }
  }

  // ---- session-instructions modal state ----------------------------------

  let showSessionInstrModal = $state(false);
  let sessionInstrInitialContent = $state("");

  function openSessionInstrModal(content: string): void {
    sessionInstrInitialContent = content;
    showSessionInstrModal = true;
  }

  async function handleSessionInstrSave(): Promise<void> {
    showSessionInstrModal = false;
    await refreshSessions(currentFilter());
    await refetchLayers();
  }

  // ---- file-edit (ClaudemdEdit) modal state ------------------------------

  let showFileEditModal = $state(false);
  let fileEditPath = $state("");
  let fileEditContent = $state("");

  function openFileEdit(layer: SystemPromptLayer): void {
    if (!layer.source_path) return;
    fileEditPath = layer.source_path;
    fileEditContent = layer.body;
    showFileEditModal = true;
  }

  async function handleFileEditSave(): Promise<void> {
    showFileEditModal = false;
    await refetchLayers();
  }

  // ---- read-only view modal state -----------------------------------------

  let showViewModal = $state(false);
  let viewModalKind = $state("");
  let viewModalKindLabel = $state("");
  let viewModalContent = $state("");
  let viewModalPath = $state<string | null>(null);

  function openViewModal(layer: SystemPromptLayer): void {
    viewModalKind = layer.kind;
    viewModalKindLabel =
      INSPECTOR_STRINGS.instructionsLayerKindLabels[layer.kind as LayerKind] ?? layer.kind;
    viewModalContent = layer.body;
    viewModalPath = layer.source_path ?? null;
    showViewModal = true;
  }

  // ---- unified click handler ----------------------------------------------

  function handleLayerClick(kind: LayerKind, layer: SystemPromptLayer): void {
    if (kind === "session_instructions") {
      openSessionInstrModal(layer.body);
    } else if (layer.source_path) {
      openFileEdit(layer);
    } else {
      openViewModal(layer);
    }
  }

  /** For the session_instructions empty-state: click to add instructions. */
  function handleSessionInstrEmptyClick(): void {
    openSessionInstrModal("");
  }
</script>

{#if showSessionInstrModal}
  <SessionInstructionsModal
    sessionId={session.id}
    initialContent={sessionInstrInitialContent}
    onSave={() => void handleSessionInstrSave()}
    onCancel={() => {
      showSessionInstrModal = false;
    }}
  />
{/if}

{#if showFileEditModal}
  <ClaudemdEdit
    sessionId={session.id}
    path={fileEditPath}
    initialContent={fileEditContent}
    onSave={() => void handleFileEditSave()}
    onCancel={() => {
      showFileEditModal = false;
    }}
  />
{/if}

{#if showViewModal}
  <LayerViewModal
    kind={viewModalKind}
    kindLabel={viewModalKindLabel}
    content={viewModalContent}
    path={viewModalPath}
    onClose={() => {
      showViewModal = false;
    }}
  />
{/if}

<section class="inspector-instructions flex flex-col gap-4" data-testid="inspector-instructions">
  <div class="flex items-center justify-between">
    <h3 class="text-xs font-semibold uppercase tracking-wider text-fg-muted">
      {INSPECTOR_STRINGS.instructionsHeading}
    </h3>
  </div>

  {#if layersLoading}
    <p class="text-xs text-fg-muted" data-testid="inspector-instructions-loading">
      {INSPECTOR_STRINGS.instructionsLoadingLayers}
    </p>
  {:else if layersError}
    <p class="text-xs text-fg-error" data-testid="inspector-instructions-error">
      {INSPECTOR_STRINGS.instructionsLayersError}
    </p>
  {:else}
    {#each LAYER_DISPLAY_ORDER as kind (kind)}
      {@const kindLayers = layersByKind[kind]}
      {@const kindLabel = INSPECTOR_STRINGS.instructionsLayerKindLabels[kind]}
      {@const emptyMsg = INSPECTOR_STRINGS.instructionsLayerEmptyState[kind]}

      <div class="flex flex-col gap-1.5" data-testid={`instructions-section-${kind}`}>
        <!-- Section heading -->
        <span class="text-xs font-medium uppercase tracking-wider text-fg-muted">
          {kindLabel}
        </span>

        {#if kindLayers.length === 0}
          {#if kind === "session_instructions"}
            <!-- Clickable empty state for session_instructions -->
            <button
              type="button"
              class="instructions-layer-card instructions-layer-card--empty"
              data-testid={`instructions-empty-${kind}`}
              onclick={handleSessionInstrEmptyClick}
            >
              <span class="text-xs italic text-fg-muted">{emptyMsg}</span>
              <span class="instructions-layer-card__hint">Click to add</span>
            </button>
          {:else}
            <p class="text-xs italic text-fg-muted" data-testid={`instructions-empty-${kind}`}>
              {emptyMsg}
            </p>
          {/if}
        {:else}
          {#each kindLayers as layer, i (i)}
            <button
              type="button"
              class="instructions-layer-card"
              data-testid={`instructions-layer-${kind}-${i}`}
              onclick={() => handleLayerClick(kind, layer)}
            >
              <span
                class="min-w-0 break-all text-left font-mono text-xs text-fg"
                title={layer.source_path ?? undefined}
                data-testid={`instructions-layer-path-${kind}-${i}`}
              >
                {#if layer.source_path}
                  <span class="text-fg-muted">{INSPECTOR_STRINGS.instructionsLayerSourceLabel}</span
                  >
                  {layer.source_path}
                {:else}
                  <span class="text-fg-muted">{kindLabel}</span>
                {/if}
              </span>
              <span class="text-xs text-fg-muted">
                {INSPECTOR_STRINGS.instructionsLayerTokensLabel(layer.token_count)}
              </span>
            </button>
          {/each}
        {/if}
      </div>
    {/each}
  {/if}
</section>

<style>
  .instructions-layer-card {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    border-radius: 0.25rem;
    border: 1px solid rgb(var(--bearings-border));
    background: rgb(var(--bearings-surface-2));
    padding: 0.5rem 0.625rem;
    width: 100%;
    text-align: left;
    cursor: pointer;
    transition: background 0.1s ease;
  }

  .instructions-layer-card:hover {
    background: rgb(var(--bearings-surface-1));
    border-color: rgb(var(--bearings-accent) / 0.5);
  }

  .instructions-layer-card--empty {
    flex-direction: row;
    align-items: center;
  }
</style>
