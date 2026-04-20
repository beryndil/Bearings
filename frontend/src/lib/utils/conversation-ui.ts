import type { Message } from '$lib/api';
import type { ConnectionState, PermissionMode } from '$lib/agent.svelte';

export function pressureClass(spent: number, cap: number | null | undefined): string {
  if (cap == null || cap <= 0) return 'text-slate-500';
  const ratio = spent / cap;
  if (ratio >= 1) return 'text-rose-400';
  if (ratio >= 0.8) return 'text-amber-400';
  return 'text-slate-500';
}

export function connectionLabel(
  state: ConnectionState,
  reconnectDelayMs: number | null,
  lastCloseCode: number | null
): string {
  if (reconnectDelayMs !== null) {
    return `retrying in ${Math.ceil(reconnectDelayMs / 1000)}s`;
  }
  switch (state) {
    case 'idle':
      return 'idle';
    case 'connecting':
      return 'connecting…';
    case 'open':
      return 'connected';
    case 'closed':
      return lastCloseCode === 4404 ? 'session not found' : 'disconnected';
    case 'error':
      return 'error';
  }
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function messagesAsMarkdown(msgs: Message[]): string {
  return msgs.map((m) => `## ${m.role}\n\n${m.content}`).join('\n\n');
}

/** Map a slash command + the current permission mode to the next mode,
 *  or `null` when the input isn't a recognized command. */
export function nextPermissionMode(
  text: string,
  current: PermissionMode
): PermissionMode | null {
  const [cmd, rawArg] = text.split(/\s+/);
  if (cmd !== '/plan') return null;
  const arg = (rawArg ?? '').toLowerCase();
  if (arg === 'off' || arg === 'default') return 'default';
  if (arg === 'on') return 'plan';
  return current === 'default' ? 'plan' : 'default';
}

// Keep the param unused-shape explicit for ConnectionState so removing
// a case above triggers a TS exhaustiveness error.
export type { ConnectionState, PermissionMode };
