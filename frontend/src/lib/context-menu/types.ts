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

/** Sidebar row or conversation header for a session. */
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

/** Discriminated union of every right-clickable target. Extend this
 * whenever a new target type is added to the spec. */
export type ContextTarget = SessionTarget | MessageTarget;
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
