import type { Message } from '$lib/api';
import type { ConnectionState } from '$lib/agent.svelte';

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
