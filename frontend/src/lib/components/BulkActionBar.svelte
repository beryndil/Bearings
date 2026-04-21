<script lang="ts">
  // Slice 4 of the Session Reorg plan
  // (`~/.claude/plans/sparkling-triaging-otter.md`). Floating action
  // bar anchored to the bottom of the conversation view whenever the
  // user has bulk-select mode engaged. Visible even with zero rows
  // selected so the user can always cancel out of the mode.
  //
  // Keyboard shortcuts (bound here, not at the parent, so tests can
  // verify the bar is the source of truth):
  //   - `m`  → fire `onMove`   (needs count > 0)
  //   - `s`  → fire `onSplit`  (needs count > 0)
  //   - `Esc` → fire `onCancel`
  // Keys are swallowed only when no input / textarea / contenteditable
  // owns focus, so typing a prompt while bulk mode is on doesn't
  // accidentally trigger a move.

  type Props = {
    count: number;
    onMove: () => void;
    onSplit: () => void;
    onCancel: () => void;
  };

  const { count, onMove, onSplit, onCancel }: Props = $props();

  $effect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.isComposing) return;
      const active = document.activeElement as HTMLElement | null;
      if (
        active &&
        (active.tagName === 'INPUT' ||
          active.tagName === 'TEXTAREA' ||
          active.isContentEditable)
      ) {
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
        return;
      }
      // Bare `m` / `s` only — no modifiers so Cmd+S / Ctrl+M reach the
      // browser as usual.
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === 'm' && count > 0) {
        e.preventDefault();
        onMove();
      } else if (e.key === 's' && count > 0) {
        e.preventDefault();
        onSplit();
      }
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  });
</script>

<div
  class="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 rounded-lg border border-slate-700
    bg-slate-900 shadow-2xl px-4 py-2 flex items-center gap-3"
  role="toolbar"
  aria-label="Bulk message actions"
  data-testid="bulk-action-bar"
>
  <span class="text-xs text-slate-300">
    {count} selected
  </span>
  <button
    type="button"
    class="rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-1.5 text-xs text-white
      disabled:opacity-50"
    disabled={count === 0}
    title="Move selected messages (m)"
    onclick={onMove}
    data-testid="bulk-move"
  >
    Move {count}…
  </button>
  <button
    type="button"
    class="rounded bg-emerald-700 hover:bg-emerald-600 px-3 py-1.5 text-xs text-white
      disabled:opacity-50"
    disabled={count === 0}
    title="Move selected messages into a new session (s)"
    onclick={onSplit}
    data-testid="bulk-split"
  >
    Split into new session…
  </button>
  <button
    type="button"
    class="rounded bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs text-slate-200"
    title="Leave bulk mode (Esc)"
    onclick={onCancel}
    data-testid="bulk-cancel"
  >
    Cancel
  </button>
</div>
