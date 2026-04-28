/**
 * Tool-call-target actions — Phase 5.
 *
 * Bound by `use:contextmenu` on each rendered tool-call row inside
 * `MessageTurn.svelte`'s tool-work drawer. Copy actions format the live
 * `LiveToolCall` pulled from the conversation store at click time —
 * snapshotting into the target would capture a half-streamed output
 * for calls still running.
 *
 * `tool_call.retry` lands disabled-with-tooltip: plan §15 defers
 * retry / regenerate to v0.10.x+ because rewinding the SDK's hidden
 * `sdk_session_id` state requires a new backend primitive (see §8
 * open question 4). The button stays here so its ID is reserved in
 * the public catalog from day one — shuffling it later breaks TOML
 * overrides.
 */

import { conversation } from '$lib/stores/conversation.svelte';
import type { LiveToolCall } from '$lib/stores/conversation.svelte';
import { writeClipboard } from '../clipboard';
import { notYetImplemented } from '../stub.svelte';
import type { Action, ContextTarget, ToolCallTarget } from '../types';

function asToolCall(t: ContextTarget): ToolCallTarget | null {
  return t.type === 'tool_call' ? t : null;
}

/** Live tool-call row by id. `null` when the store hasn't loaded or
 * the call was evicted (e.g. after a session.forget). Handlers treat
 * `null` as a silent no-op. */
function lookupCall(id: string): LiveToolCall | null {
  return conversation.toolCalls.find((c) => c.id === id) ?? null;
}

/** Pretty-print the call input as JSON so the copied payload matches
 * what the drawer renders on screen. Fallback to `String(v)` when
 * JSON.stringify throws (cyclic refs from live objects shouldn't
 * appear — the reducer parses JSON strings — but guard anyway). */
function formatInput(input: unknown): string {
  try {
    return JSON.stringify(input, null, 2);
  } catch {
    return String(input);
  }
}

export const TOOL_CALL_ACTIONS: readonly Action[] = [
  {
    id: 'tool_call.copy.name',
    label: 'Copy tool name',
    section: 'copy',
    mnemonic: 'n',
    handler: async ({ target }) => {
      const t = asToolCall(target);
      if (!t) return;
      const call = lookupCall(t.id);
      if (!call) return;
      await writeClipboard(call.name);
    },
  },
  {
    id: 'tool_call.copy.input',
    label: 'Copy tool input',
    section: 'copy',
    mnemonic: 'i',
    handler: async ({ target }) => {
      const t = asToolCall(target);
      if (!t) return;
      const call = lookupCall(t.id);
      if (!call) return;
      await writeClipboard(formatInput(call.input));
    },
  },
  {
    id: 'tool_call.copy.output',
    label: 'Copy tool output',
    section: 'copy',
    mnemonic: 'o',
    handler: async ({ target }) => {
      const t = asToolCall(target);
      if (!t) return;
      const call = lookupCall(t.id);
      if (!call) return;
      // Prefer error text when the call failed — that's the thing a
      // user right-clicks to grab for a bug report. Fall back to an
      // empty string when the call is still running; copying the
      // shell's blank "truncated" marker wouldn't help anyone.
      const payload = call.error ?? call.output ?? '';
      await writeClipboard(payload);
    },
    disabled: (target) => {
      const t = asToolCall(target);
      if (!t) return null;
      const call = lookupCall(t.id);
      if (!call) return null;
      if (call.output === null && call.error === null) {
        return 'No output yet — the tool is still running';
      }
      return null;
    },
  },
  {
    id: 'tool_call.copy.id',
    label: 'Copy tool call ID',
    section: 'copy',
    advanced: true,
    handler: async ({ target }) => {
      const t = asToolCall(target);
      if (!t) return;
      await writeClipboard(t.id);
    },
  },
  {
    id: 'tool_call.retry',
    label: 'Retry tool call',
    section: 'edit',
    advanced: true,
    handler: () => notYetImplemented('tool_call.retry'),
    disabled: () => 'Retry / regenerate lands in v0.10.x+',
  },
];
