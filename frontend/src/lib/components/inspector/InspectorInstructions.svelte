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
    | "tag_memory"
    | "template_baseline";

  const LAYER_DISPLAY_ORDER: readonly LayerKind[] = [
    "session_instructions",
    "baseline",
    "project_claude_md",
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

  // ---- copy path ----------------------------------------------------------

  let copiedPath = $state<string | null>(null);

  function copyPath(event: MouseEvent, path: string): void {
    event.stopPropagation();
    void navigator.clipboard.writeText(path).then(() => {
      copiedPath = path;
      setTimeout(() => {
        copiedPath = null;
      }, 1500);
    });
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
            <!-- role="button" avoids nested <button> (copy btn is a real <button> inside) -->
            <div
              role="button"
              tabindex="0"
              class="instructions-layer-card"
              data-testid={`instructions-layer-${kind}-${i}`}
              onclick={() => handleLayerClick(kind, layer)}
              onkeydown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleLayerClick(kind, layer);
                }
              }}
            >
              <!-- Path / kind identifier row -->
              <div class="flex items-start gap-1.5">
                <span
                  class="min-w-0 flex-1 break-all text-left font-mono text-xs text-fg"
                  title={layer.source_path ?? undefined}
                  data-testid={`instructions-layer-path-${kind}-${i}`}
                >
                  {#if layer.source_path}
                    <span class="text-fg-muted"
                      >{INSPECTOR_STRINGS.instructionsLayerSourceLabel}</span
                    >
                    {layer.source_path}
                  {:else}
                    <span class="text-fg-muted">{kindLabel}</span>
                  {/if}
                </span>
              </div>

              <!-- Token count + actions row -->
              <div class="flex items-center gap-1.5">
                <span class="shrink-0 text-xs text-fg-muted">
                  {INSPECTOR_STRINGS.instructionsLayerTokensLabel(layer.token_count)}
                </span>
                <span class="flex-1"></span>
                {#if layer.source_path}
                  <button
                    type="button"
                    class="instructions-layer-card__action-btn"
                    data-testid={`instructions-layer-copy-${kind}-${i}`}
                    onclick={(e) => copyPath(e, layer.source_path!)}
                  >
                    {copiedPath === layer.source_path
                      ? INSPECTOR_STRINGS.instructionsCopyPathDone
                      : INSPECTOR_STRINGS.instructionsCopyPathButton}
                  </button>
                {/if}
                <span class="instructions-layer-card__hint">
                  {layer.source_path || kind === "session_instructions" ? "Edit →" : "View →"}
                </span>
              </div>
            </div>
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
    gap: 0.375rem;
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
    justify-content: space-between;
    gap: 0.5rem;
  }

  .instructions-layer-card__hint {
    flex-shrink: 0;
    font-size: 0.6875rem;
    color: rgb(var(--bearings-fg-muted));
    opacity: 0;
    transition: opacity 0.1s ease;
  }

  .instructions-layer-card:hover .instructions-layer-card__hint {
    opacity: 1;
    color: rgb(var(--bearings-accent));
  }

  .instructions-layer-card__action-btn {
    padding: 0.125rem 0.4rem;
    border-radius: 0.2rem;
    font-size: 0.6875rem;
    cursor: pointer;
    border: 1px solid rgb(var(--bearings-border));
    background: rgb(var(--bearings-surface-2));
    color: rgb(var(--bearings-fg-muted));
    flex-shrink: 0;
  }

  .instructions-layer-card__action-btn:hover {
    background: rgb(var(--bearings-surface-1));
    color: rgb(var(--bearings-fg));
  }
</style>
