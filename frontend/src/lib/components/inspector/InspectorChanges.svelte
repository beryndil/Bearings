<script lang="ts">
  /**
   * Changes subsection — chronological list of every WRITE-side tool
   * call (``Edit`` / ``Write`` / ``NotebookEdit``) made in the active
   * session.
   *
   * Behavior anchors:
   *
   * - ``docs/behavior/chat.md`` §"Inspector pane" §"Changes" documents
   *   the data source, verb mapping, and excerpt extraction rule.
   * - gap-cycle-09-004 specifies the row shape: home-shortened path,
   *   verb badge (Created / Edited / Notebook-edited) with distinct
   *   colour treatment, single-line excerpt (≤ 120 chars), and
   *   timestamp; sorted most-recent first.
   *
   * Verb mapping:
   * - ``Write``        → "Created"        — emerald badge
   * - ``Edit``         → "Edited"         — amber badge
   * - ``NotebookEdit`` → "Notebook-edited" — indigo badge
   *
   * Excerpt extraction:
   * 1. ``Write``        → ``content``    field of ``inputJson``
   * 2. ``Edit``         → ``new_string`` field of ``inputJson``
   * 3. ``NotebookEdit`` → ``new_source`` field of ``inputJson``
   * Take the first newline-delimited line, trim leading whitespace,
   * clip to 120 characters.
   *
   * The ``turns`` prop is a test seam — production callers pass
   * nothing and the component reads from :data:`conversationStore`.
   */
  import { INSPECTOR_STRINGS } from "../../config";
  import { conversationStore, type MessageTurnView } from "../../stores/conversation.svelte";
  import { formatAbsolute } from "../../utils/datetime";
  import type { SessionOut } from "../../api/sessions";
  import { listReorgAudits, type ReorgAuditOut } from "../../api/reorg";

  /** Write-side tool names this subsection tracks. */
  const WRITE_TOOLS = new Set(["Edit", "Write", "NotebookEdit"]);

  /** A single change-row derived from one Write-side tool call. */
  interface ChangeRow {
    /** Unique tool-call id — used as the Svelte keyed-each key. */
    id: string;
    /** Original unshortened path (title tooltip). */
    path: string;
    /** ``/home/<user>/…`` shortened to ``~/…`` for column fit. */
    shortPath: string;
    /** User-facing verb: "Created", "Edited", or "Notebook-edited". */
    verb: string;
    /** Tailwind class string for the verb badge background + text. */
    badgeClass: string;
    /** First line of the new content, trimmed and clipped to 120 chars. */
    excerpt: string;
    /** Epoch-ms timestamp; ``null`` when unavailable. */
    timestampMs: number | null;
  }

  interface Props {
    /**
     * Active session row. Used to fetch reorg audit history (T1-11).
     */
    session: SessionOut;
    /**
     * Test seam. Production callers pass nothing; the component reads
     * :data:`conversationStore.turns`. Tests inject a fixture list so
     * each test owns its state without touching the module-singleton
     * store.
     */
    turns?: readonly MessageTurnView[];
    /**
     * Test seam for reorg audit fetch. Production callers pass nothing.
     */
    fetchReorgAudits?: (sessionId: string) => Promise<{ items: ReorgAuditOut[] }>;
  }

  const {
    session,
    turns: turnsProp = undefined,
    fetchReorgAudits = listReorgAudits,
  }: Props = $props();

  // ---- reorg history (T1-11) ---------------------------------------------

  let reorgAudits = $state<ReorgAuditOut[]>([]);
  let reorgLoading = $state(false);
  let reorgError = $state(false);

  $effect(() => {
    const sid = session.id;
    reorgAudits = [];
    reorgError = false;
    reorgLoading = true;
    fetchReorgAudits(sid)
      .then((result) => {
        reorgAudits = result.items;
      })
      .catch(() => {
        reorgError = true;
      })
      .finally(() => {
        reorgLoading = false;
      });
  });

  /**
   * Map a Write-side tool name to its user-facing verb string.
   */
  function mapVerb(name: string): string {
    if (name === "Write") return "Created";
    if (name === "NotebookEdit") return "Notebook-edited";
    return "Edited"; // "Edit"
  }

  /**
   * Map a Write-side tool name to its verb-badge Tailwind classes.
   *
   * Colour treatments (v17 parity via v18 theme tokens):
   * - Created (Write)        → emerald
   * - Edited (Edit)          → amber
   * - Notebook-edited        → indigo
   */
  function mapBadgeClass(name: string): string {
    if (name === "Write") {
      return "bg-emerald-500/15 text-emerald-400";
    }
    if (name === "NotebookEdit") {
      return "bg-indigo-500/15 text-indigo-400";
    }
    return "bg-amber-500/15 text-amber-400"; // "Edit"
  }

  /**
   * Extract the file path from a tool call's ``inputJson``.
   *
   * ``Write`` / ``Edit`` → ``file_path``
   * ``NotebookEdit``     → ``notebook_path``
   *
   * Returns ``null`` when ``inputJson`` cannot be parsed or the expected
   * key is absent / non-string.
   */
  function extractPath(name: string, inputJson: string): string | null {
    try {
      const parsed = JSON.parse(inputJson) as Record<string, unknown>;
      if (name === "NotebookEdit") {
        return typeof parsed.notebook_path === "string" && parsed.notebook_path.length > 0
          ? parsed.notebook_path
          : null;
      }
      return typeof parsed.file_path === "string" && parsed.file_path.length > 0
        ? parsed.file_path
        : null;
    } catch {
      return null;
    }
  }

  /**
   * Extract a single-line excerpt from a tool call's ``inputJson``.
   *
   * Content key by tool:
   * - ``Write``        → ``content``
   * - ``Edit``         → ``new_string``
   * - ``NotebookEdit`` → ``new_source``
   *
   * Processing: split on ``\n``, take index 0, trim leading whitespace,
   * clip to 120 characters.  Returns an empty string on parse failure
   * or when the content key is absent.
   */
  function extractExcerpt(name: string, inputJson: string): string {
    try {
      const parsed = JSON.parse(inputJson) as Record<string, unknown>;
      let raw: string | undefined;
      if (name === "Write" && typeof parsed.content === "string") {
        raw = parsed.content;
      } else if (name === "Edit" && typeof parsed.new_string === "string") {
        raw = parsed.new_string;
      } else if (name === "NotebookEdit" && typeof parsed.new_source === "string") {
        raw = parsed.new_source;
      }
      if (raw === undefined) return "";
      const firstLine = raw.split("\n")[0].trimStart();
      return firstLine.length > 120 ? firstLine.slice(0, 120) : firstLine;
    } catch {
      return "";
    }
  }

  /**
   * Shorten ``/home/<user>/…`` to ``~/…`` for column fit.
   *
   * Matches exactly one path segment after ``/home/`` so nested home
   * directories collapse to ``~/…``.
   */
  function shortenHome(path: string): string {
    return path.replace(/^\/home\/[^/]+\//, "~/");
  }

  /** Active turns: the test-injected list when provided, else the store. */
  const activeTurns = $derived(turnsProp ?? conversationStore.turns);

  /**
   * Change rows, sorted most-recent first.
   *
   * One row per Write-side tool call (no deduplication — each call is
   * a discrete change event). Timestamp derivation mirrors
   * :class:`InspectorFiles`:
   * 1. ``startedAt`` if non-zero.
   * 2. Parsed ``createdAt`` of the parent turn (hydrated calls).
   * 3. ``null`` when neither is available; these rows sort last.
   */
  const changeRows = $derived.by<ChangeRow[]>(() => {
    const rows: ChangeRow[] = [];

    for (const turn of activeTurns) {
      for (const tc of turn.toolCalls) {
        if (!WRITE_TOOLS.has(tc.name)) continue;

        const path = extractPath(tc.name, tc.inputJson);
        if (path === null) continue;

        let timestampMs: number | null = null;
        if (tc.startedAt !== 0) {
          timestampMs = tc.startedAt;
        } else if (turn.createdAt !== null) {
          timestampMs = new Date(turn.createdAt).getTime();
        }

        rows.push({
          id: tc.id,
          path,
          shortPath: shortenHome(path),
          verb: mapVerb(tc.name),
          badgeClass: mapBadgeClass(tc.name),
          excerpt: extractExcerpt(tc.name, tc.inputJson),
          timestampMs,
        });
      }
    }

    return rows.sort((a, b) => {
      if (a.timestampMs === null && b.timestampMs === null) return 0;
      if (a.timestampMs === null) return 1;
      if (b.timestampMs === null) return -1;
      return b.timestampMs - a.timestampMs;
    });
  });
</script>

<div class="inspector-changes flex flex-col gap-6" data-testid="inspector-changes">
  <!-- File-edit changes section (tool-call derived) -->
  <section class="flex flex-col gap-3" data-testid="inspector-changes-edits">
    <h3
      class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-fg-muted"
    >
      {INSPECTOR_STRINGS.changesHeading}
      {#if changeRows.length > 0}
        <span
          class="rounded bg-surface-2 px-1.5 py-0.5 text-xs font-medium tabular-nums text-fg"
          data-testid="inspector-changes-count"
        >
          {changeRows.length}
        </span>
      {/if}
    </h3>

    {#if changeRows.length === 0}
      <div data-testid="inspector-changes-empty">
        <p class="text-sm text-fg-muted">
          {INSPECTOR_STRINGS.changesEmptyHeading}
        </p>
        <p class="mt-1 text-xs text-fg-muted">
          {INSPECTOR_STRINGS.changesEmptyBody}
        </p>
      </div>
    {:else}
      <ul class="flex flex-col gap-2" data-testid="inspector-changes-list">
        {#each changeRows as row (row.id)}
          <li class="flex min-w-0 flex-col gap-0.5 text-xs" data-testid="inspector-changes-row">
            <div class="flex min-w-0 items-baseline gap-2">
              <span
                class="min-w-0 flex-1 truncate font-mono text-fg"
                title={row.path}
                data-testid="inspector-changes-path"
              >
                {row.shortPath}
              </span>
              <span
                class="shrink-0 rounded px-1.5 py-0.5 text-xs font-medium {row.badgeClass}"
                data-testid="inspector-changes-verb"
              >
                {row.verb}
              </span>
              <span
                class="shrink-0 tabular-nums text-fg-muted"
                data-testid="inspector-changes-time"
              >
                {row.timestampMs !== null ? formatAbsolute(row.timestampMs) : "—"}
              </span>
            </div>
            {#if row.excerpt.length > 0}
              <p class="truncate font-mono text-fg-muted" data-testid="inspector-changes-excerpt">
                {row.excerpt}
              </p>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <!-- Reorg history section (T1-11) — merge/split/move audit records -->
  <section class="flex flex-col gap-3" data-testid="inspector-reorg-history">
    <h3
      class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-fg-muted"
    >
      {INSPECTOR_STRINGS.reorgHistoryHeading}
      {#if reorgAudits.length > 0}
        <span
          class="rounded bg-surface-2 px-1.5 py-0.5 text-xs font-medium tabular-nums text-fg"
          data-testid="inspector-reorg-count"
        >
          {reorgAudits.length}
        </span>
      {/if}
    </h3>

    {#if reorgLoading}
      <p class="text-xs text-fg-muted" data-testid="inspector-reorg-loading">
        {INSPECTOR_STRINGS.reorgHistoryLoadingLabel}
      </p>
    {:else if reorgError}
      <p class="text-xs text-red-400" data-testid="inspector-reorg-error">
        {INSPECTOR_STRINGS.reorgHistoryErrorLabel}
      </p>
    {:else if reorgAudits.length === 0}
      <div data-testid="inspector-reorg-empty">
        <p class="text-sm text-fg-muted">{INSPECTOR_STRINGS.reorgHistoryEmptyHeading}</p>
        <p class="mt-1 text-xs text-fg-muted">{INSPECTOR_STRINGS.reorgHistoryEmptyBody}</p>
      </div>
    {:else}
      <ul class="flex flex-col gap-2" data-testid="inspector-reorg-list">
        {#each reorgAudits as audit (audit.id)}
          <li class="flex min-w-0 flex-col gap-0.5 text-xs" data-testid="inspector-reorg-row">
            <div class="flex min-w-0 items-baseline gap-2">
              <span
                class="shrink-0 rounded bg-surface-2 px-1.5 py-0.5 font-medium text-fg"
                data-testid="inspector-reorg-kind"
              >
                {INSPECTOR_STRINGS.reorgHistoryKindLabels[audit.kind]}
              </span>
              <span
                class="min-w-0 flex-1 truncate text-fg-muted"
                title={audit.src_title}
                data-testid="inspector-reorg-src-title"
              >
                {audit.src_title}
              </span>
              <span class="shrink-0 tabular-nums text-fg-muted" data-testid="inspector-reorg-time">
                {formatAbsolute(new Date(audit.merged_at).getTime())}
              </span>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </section>
</div>
