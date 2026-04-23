/**
 * Central registry mapping target types to action lists.
 *
 * Phase 1 ships a plain static lookup — Phase 10 grows this to merge
 * the user's `~/.config/bearings/menus.toml` overrides (pinned, hidden,
 * shortcut rebindings) with the defaults declared per target.
 *
 * Invariants:
 *   - Every `Action` belongs to exactly one target type.
 *   - IDs are unique within a target type. Enforced by registry.test.ts.
 *   - IDs are public API. Renames go through `Action.aliases` with a
 *     deprecation warning, never silently. See §7.3 of the plan.
 */

import type {
  Action,
  ActionSection,
  ContextTarget,
  RenderedMenu,
  TargetType
} from './types';
import { SECTIONS } from './types';
import { SESSION_ACTIONS } from './actions/session';
import { MESSAGE_ACTIONS } from './actions/message';
import { TAG_ACTIONS, TAG_CHIP_ACTIONS } from './actions/tag';
import { TOOL_CALL_ACTIONS } from './actions/tool_call';
import { CODE_BLOCK_ACTIONS } from './actions/code_block';
import { LINK_ACTIONS } from './actions/link';
import { CHECKPOINT_ACTIONS } from './actions/checkpoint';
import { MULTI_SELECT_ACTIONS } from './actions/multi_select';

const REGISTRY: Record<TargetType, readonly Action[]> = {
  session: SESSION_ACTIONS,
  message: MESSAGE_ACTIONS,
  tag: TAG_ACTIONS,
  tag_chip: TAG_CHIP_ACTIONS,
  tool_call: TOOL_CALL_ACTIONS,
  code_block: CODE_BLOCK_ACTIONS,
  link: LINK_ACTIONS,
  checkpoint: CHECKPOINT_ACTIONS,
  multi_select: MULTI_SELECT_ACTIONS
};

/** Unfiltered actions for a target type. */
export function getActions(type: TargetType): readonly Action[] {
  return REGISTRY[type] ?? [];
}

/**
 * Resolve the menu for a specific target at render time.
 *
 * Filters out:
 *   - `advanced: true` items when `advanced` is false.
 *   - items whose `requires(target)` returns false.
 *
 * Does NOT filter by `disabled` — disabled items render in place
 * (greyed with tooltip) per decision §2.3.
 *
 * Groups results by section, preserving the spec's canonical section
 * order. Empty sections are dropped so the renderer doesn't produce
 * stray dividers.
 */
export function resolveMenu(
  target: ContextTarget,
  advanced: boolean
): RenderedMenu {
  const all = getActions(target.type);
  const visible = all.filter((a) => {
    if (a.advanced && !advanced) return false;
    if (a.requires && !a.requires(target)) return false;
    return true;
  });
  const bySection = new Map<ActionSection, Action[]>();
  for (const action of visible) {
    const bucket = bySection.get(action.section);
    if (bucket) bucket.push(action);
    else bySection.set(action.section, [action]);
  }
  const groups: RenderedMenu['groups'] = [];
  for (const section of SECTIONS) {
    const actions = bySection.get(section);
    if (actions && actions.length > 0) groups.push({ section, actions });
  }
  return { target, advanced, groups };
}
