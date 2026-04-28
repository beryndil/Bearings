/**
 * Command palette resolver — Phase 4b.
 *
 * The palette (Ctrl+Shift+P) is a flat, global action-finder that
 * reuses the registry built for right-click menus. Because right-click
 * hands an action a `ContextTarget` carrying the surface it was invoked
 * from, the palette has to synthesise a target for the user: "run
 * `session.pin` on *what*?"
 *
 * Scope decision for Phase 4b: auto-resolve targets from app state when
 * there's an obvious default (currently-selected session), and *drop*
 * actions whose target has no such default. Users reach tag / tag_chip
 * / message actions via right-click on the relevant surface; surfacing
 * them with a disabled "no target" tooltip bloats the palette without
 * adding discoverability (the palette is a flat list; scrolling past
 * 80% greyed-out rows is a worse UX than not seeing the rows at all).
 *
 * Message actions are deferred to Phase 5 — there is no "current
 * message" in app state today, and introducing one just for the palette
 * would couple the message-turn component to a global focus tracker.
 *
 * Filter ranking mirrors `CommandMenu.svelte`: prefix > substring on
 * label > substring on id. IDs are deliberately part of the match
 * surface because `menus.toml` future customisations key on IDs and
 * power users memorise them.
 */

import type { Action, ContextTarget, TargetType } from './types';
import { getActions } from './registry';

/** One row in the palette. Mirrors the Action type but adds an
 * auto-resolved `target` + the disabled-reason string (computed once
 * here so the UI doesn't re-run the predicate on every render). */
export type PaletteEntry = {
  id: string;
  label: string;
  section: Action['section'];
  target: ContextTarget;
  action: Action;
  /** Non-null ⇒ row renders greyed with this as tooltip; Enter on a
   * disabled row is a no-op. */
  disabledReason: string | null;
  /** True when the action has `advanced: true` — palette shows these
   * by default because it's an explicit-discovery surface; Shift-
   * right-click gating exists for right-click only. */
  advanced: boolean;
};

/** Target-type → current-target auto-resolver. Returning `null` drops
 * every action of that type from the palette. */
export type TargetResolver = (type: TargetType) => ContextTarget | null;

/** Scan every target type in the registry, auto-resolve its target,
 * filter by `requires`, and emit palette entries. Deterministic order:
 * target-type order (the REGISTRY iteration order) then action order
 * within each type — the filter pass rearranges by rank, so this
 * ordering only matters for "no query" baseline listing. */
export function collectPaletteEntries(
  resolver: TargetResolver,
  types: readonly TargetType[]
): PaletteEntry[] {
  const entries: PaletteEntry[] = [];
  for (const type of types) {
    const target = resolver(type);
    if (!target) continue;
    for (const action of getActions(type)) {
      if (action.requires && !action.requires(target)) continue;
      // Skip submenu-parents (handler is a no-op, they only make sense
      // as an anchor for their children in a popup). Children surface
      // as standalone palette entries further down when the resolver
      // reaches them via their own target — but for now the children
      // share the parent's target, so enumerate them inline.
      if (action.submenu) {
        const children =
          typeof action.submenu === 'function' ? action.submenu(target) : action.submenu;
        for (const child of children) {
          entries.push(buildEntry(child, target, action.label));
        }
        continue;
      }
      entries.push(buildEntry(action, target, null));
    }
  }
  return entries;
}

function buildEntry(
  action: Action,
  target: ContextTarget,
  parentLabel: string | null
): PaletteEntry {
  // Submenu-leaf labels look ambiguous on their own ("claude-opus-4-7")
  // so prefix with the parent label stripped of its ▸ indicator.
  const label = parentLabel
    ? `${parentLabel.replace(/\s*▸\s*$/, '')}: ${action.label}`
    : action.label;
  return {
    id: action.id,
    label,
    section: action.section,
    target,
    action,
    disabledReason: action.disabled?.(target) ?? null,
    advanced: action.advanced === true,
  };
}

/** Rank a single entry against a (lowercased, trimmed) query. Lower is
 * better. Returns -1 when the entry doesn't match at all. */
export function rankEntry(entry: PaletteEntry, q: string): number {
  if (q === '') return 100;
  const idLower = entry.id.toLowerCase();
  const labelLower = entry.label.toLowerCase();
  if (labelLower.startsWith(q)) return 0;
  if (idLower.startsWith(q)) return 1;
  if (labelLower.includes(q)) return 2;
  if (idLower.includes(q)) return 3;
  // Also match the last segment of the id (e.g. "pin" matches
  // "session.pin"). Makes verb-first queries cheap.
  const idTail = idLower.split('.').pop() ?? idLower;
  if (idTail.startsWith(q)) return 4;
  return -1;
}

/** Filter + rank entries for a query. Ties break on label asc. */
export function filterEntries(entries: readonly PaletteEntry[], query: string): PaletteEntry[] {
  const q = query.trim().toLowerCase();
  const scored: { entry: PaletteEntry; rank: number }[] = [];
  for (const entry of entries) {
    const rank = rankEntry(entry, q);
    if (rank < 0) continue;
    scored.push({ entry, rank });
  }
  scored.sort((a, b) => {
    if (a.rank !== b.rank) return a.rank - b.rank;
    return a.entry.label.localeCompare(b.entry.label);
  });
  return scored.map((s) => s.entry);
}
