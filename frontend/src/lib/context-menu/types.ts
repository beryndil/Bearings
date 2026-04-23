/**
 * Context-menu type system — the public contract for everything under
 * `$lib/context-menu/`. See `docs/context-menu-plan.md` §7 for the
 * action-ID stability policy (IDs are a public API referenced by
 * `~/.config/bearings/menus.toml`).
 *
 * Phase 1 ships with two target types (session, message) and two
 * actions (session.copy_id, message.copy_id). Growing the system
 * means: add a new variant to `ContextTarget`, add an
 * `actions/<target>.ts` file, register it in `registry.ts`.
 */

/** Section ordering matches the spec's Structural Ordering rule. */
export const SECTIONS = [
  'primary',
  'navigate',
  'create',
  'edit',
  'view',
  'copy',
  'organize',
  'destructive'
] as const;
export type ActionSection = (typeof SECTIONS)[number];

/** Sidebar row or conversation header for a session. The target
 * deliberately carries only the id — `requires` / `disabled`
 * predicates fetch fresh `closed_at` / `pinned` / `working_dir` from
 * the sessions store so a menu opened seconds before a WS update
 * doesn't render stale gating decisions. */
export type SessionTarget = {
  type: 'session';
  id: string;
};

/** A user or assistant message bubble. `sessionId` is carried so
 * cross-session actions (fork, jump) can reach backend without an
 * extra round-trip through the store. */
export type MessageTarget = {
  type: 'message';
  id: string;
  sessionId: string;
  role: 'user' | 'assistant';
};

/** Sidebar-filter tag row (either general group or severity group).
 * Only the id is needed — the handlers look the row up via the tags
 * store so `pinned` + `name` always reflect latest state. */
export type TagTarget = {
  type: 'tag';
  id: number;
};

/** A tag chip attached to a session. `sessionId` is nullable because
 * the NewSessionForm's attached-tag list renders chips for a session
 * that hasn't been persisted yet — `tag_chip.detach` gates on the
 * presence of `sessionId`. Chips attached to existing sessions (in
 * SessionEdit) always carry a real id. */
export type TagChipTarget = {
  type: 'tag_chip';
  tagId: number;
  sessionId: string | null;
};

/** A tool-call row inside an assistant turn's tool-work drawer. Carries
 * the live `LiveToolCall.id` so handlers can look up the latest
 * input/output from the conversation store — the row streams, and a
 * snapshot into the target would be stale by the time the handler
 * fires. `messageId` is the assistant message the call belongs to when
 * the reducer has stitched one (null during the first few streaming
 * frames of a brand-new turn). */
export type ToolCallTarget = {
  type: 'tool_call';
  id: string;
  sessionId: string;
  messageId: string | null;
};

/** A fenced code block rendered inside a message body. The payload is
 * snapshotted at right-click time from the DOM (the delegate action
 * reads `textContent` off the `<pre>` and the `data-language` off the
 * wrapper `<div>`) — so handlers don't have to re-parse the Markdown
 * source. `sessionId` / `messageId` are carried so future "run this
 * snippet" actions can attribute the result, but both are nullable
 * because the delegate fires on any message descendant (including the
 * streaming assistant bubble, which has no settled message id yet). */
export type CodeBlockTarget = {
  type: 'code_block';
  text: string;
  language: string | null;
  sessionId: string | null;
  messageId: string | null;
};

/** A Markdown link (`<a href>`) rendered inside a message body.
 * Delegate-captured the same way as code blocks — `text` is the
 * anchor's visible label, `href` is whatever marked wrote. Callers
 * MUST treat `href` as untrusted (the content comes from the user or
 * their agent); `open_new_tab` wraps it with `rel="noopener"`. */
export type LinkTarget = {
  type: 'link';
  href: string;
  text: string;
  sessionId: string | null;
  messageId: string | null;
};

/** A checkpoint chip rendered in the conversation gutter (Phase 7 of
 * docs/context-menu-plan.md). Carries the full row snapshot so the
 * handlers can stay synchronous against the store without refetching:
 * `messageId` is null when the anchor message was dropped (FK SET NULL)
 * — the `fork` action gates on that via `disabled`, the `copy_label`
 * and `delete` actions remain available. */
export type CheckpointTarget = {
  type: 'checkpoint';
  id: string;
  sessionId: string;
  messageId: string | null;
  label: string | null;
};

/** Discriminated union of every right-clickable target. Extend this
 * whenever a new target type is added to the spec. */
export type ContextTarget =
  | SessionTarget
  | MessageTarget
  | TagTarget
  | TagChipTarget
  | ToolCallTarget
  | CodeBlockTarget
  | LinkTarget
  | CheckpointTarget;
export type TargetType = ContextTarget['type'];

/** Passed to every handler. `event` is null when the action is fired
 * from the command palette (Phase 4b) rather than a right-click. */
export type ActionContext = {
  target: ContextTarget;
  event: Event | null;
  advanced: boolean;
};

/**
 * A single menu entry.
 *
 * - `id` is a stable public API. Renames must go through `aliases`
 *   with a major version bump (see §7.3).
 * - `advanced: true` items are only visible under Shift-right-click
 *   (decision §2.5).
 * - `destructive: true` items will route through ConfirmDialog when
 *   that lands in Phase 3.
 * - `disabled(target)` returning a non-null string renders the item
 *   greyed with that string as tooltip (decision §2.3 for primitives
 *   that don't exist yet).
 * - `submenu` is Phase 2+; Phase 1 ignores it.
 */
export type Action = {
  id: string;
  label: string;
  section: ActionSection;
  handler: (ctx: ActionContext) => void | Promise<void>;
  shortcut?: string;
  icon?: string;
  destructive?: boolean;
  advanced?: boolean;
  mnemonic?: string;
  aliases?: readonly string[];
  requires?: (target: ContextTarget) => boolean;
  disabled?: (target: ContextTarget) => string | null;
  submenu?: readonly Action[] | ((target: ContextTarget) => readonly Action[]);
};

/** Menu data after `resolveMenu` has filtered + grouped by section. */
export type RenderedMenu = {
  target: ContextTarget;
  advanced: boolean;
  /** Groups in spec section order; empty sections are omitted. */
  groups: Array<{ section: ActionSection; actions: Action[] }>;
};
