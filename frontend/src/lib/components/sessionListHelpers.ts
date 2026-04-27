/**
 * Pure helper functions extracted from `SessionList.svelte` (§FileSize).
 * No reactive state — every input comes through arguments so the
 * helpers are easy to unit-test in isolation and the parent component
 * can stay focused on layout + reactivity wiring.
 */

import type { Session, Tag } from '$lib/api';

/** Resolve the four-state sidebar indicator for a session row.
 *
 *   'red'    — look at it now. Runner is parked on a user decision
 *              (tool-use approval OR AskUserQuestion) OR the last
 *              turn errored and hasn't been cleared by a subsequent
 *              successful turn (server-side `error_pending` latch).
 *              Clears the moment the user submits the pending
 *              answer or a later turn completes without crashing.
 *   'orange' — the agent is actively working a turn that isn't
 *              currently parked on a decision. Clears when the turn
 *              ends.
 *   'green'  — a turn finished while the user was elsewhere and
 *              hasn't been viewed yet. Drives the "new output
 *              waiting for you" signal (re-added per Dave's call
 *              after watching the three-state version run —
 *              recency-by-sort-order wasn't enough to spot freshly-
 *              finished sessions at a glance). Clears the moment
 *              the user focuses the row (`markViewed` bumps
 *              `last_viewed_at`).
 *   null     — nothing to signal. Session is idle and caught up,
 *              or closed.
 *
 * Priority (red > orange > green > null): the "look at this now"
 * signal pre-empts everything; running pre-empts unviewed because
 * an in-flight turn is about to produce new unviewed output anyway
 * and the orange ping already tells Dave a turn is landing.
 */
export function indicatorState(
  session: Session,
  awaiting: ReadonlySet<string>,
  running: ReadonlySet<string>
): 'red' | 'orange' | 'green' | null {
  if (awaiting.has(session.id)) return 'red';
  if (session.error_pending) return 'red';
  if (running.has(session.id)) return 'orange';
  // Green = finished, waiting to be viewed. Needs both a completion
  // timestamp (the session ever finished a turn) AND either no view
  // stamp or a view stamp that precedes the completion.
  if (session.last_completed_at) {
    if (!session.last_viewed_at) return 'green';
    if (session.last_completed_at > session.last_viewed_at) return 'green';
  }
  return null;
}

export function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

export function costClass(session: Session): string {
  const cap = session.max_budget_usd;
  if (cap == null || cap <= 0) return 'text-slate-600';
  const ratio = session.total_cost_usd / cap;
  if (ratio >= 1) return 'text-rose-400';
  if (ratio >= 0.8) return 'text-amber-400';
  return 'text-slate-600';
}

/** Resolve a session's `tag_ids` into the in-memory tag rows so the
 * medallion row can pull color + group without a per-row fetch.
 * Returns only the tags the store has loaded — unknown ids drop
 * silently. */
export function tagsFor(session: Session, allTags: readonly Tag[]): Tag[] {
  const byId = new Map(allTags.map((t) => [t.id, t]));
  const ids = session.tag_ids ?? [];
  const out: Tag[] = [];
  for (const id of ids) {
    const hit = byId.get(id);
    if (hit) out.push(hit);
  }
  return out;
}

/** Split a session's tag list into the severity slot (one tag or
 * null) and the ordered general-tag list. Severity lookup is by
 * `tag_group` — the exactly-one invariant is enforced server-side
 * so we don't re-check here. */
export function medallionData(
  session: Session,
  allTags: readonly Tag[]
): {
  severity: Tag | null;
  general: Tag[];
} {
  const resolved = tagsFor(session, allTags);
  const severity = resolved.find((t) => t.tag_group === 'severity') ?? null;
  const general = resolved.filter((t) => t.tag_group !== 'severity');
  return { severity, general };
}
