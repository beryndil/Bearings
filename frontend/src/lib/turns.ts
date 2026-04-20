import type { Message } from '$lib/api';
import type { LiveToolCall } from '$lib/stores/conversation.svelte';

export type Turn = {
  key: string;
  user: Message | null;
  assistant: Message | null;
  thinking: string;
  toolCalls: LiveToolCall[];
  streamingContent: string;
  streamingThinking: string;
  isStreaming: boolean;
};

function empty(key: string, user: Message | null): Turn {
  return {
    key,
    user,
    assistant: null,
    thinking: '',
    toolCalls: [],
    streamingContent: '',
    streamingThinking: '',
    isStreaming: false
  };
}

export type TurnsInput = {
  messages: Message[];
  toolCalls: LiveToolCall[];
  streamingActive: boolean;
  streamingMessageId: string | null;
  streamingThinking: string;
  streamingText: string;
};

/** Collapse the flat (messages, toolCalls) stream into turn-oriented
 *  groups for the Conversation view: one user message → its thinking,
 *  tool work, and the assistant reply. The tail turn folds in live
 *  streaming state when `streamingActive` is true. */
export function buildTurns(input: TurnsInput): Turn[] {
  const byMsgId = new Map<string, LiveToolCall[]>();
  for (const tc of input.toolCalls) {
    const key = tc.messageId ?? '';
    const arr = byMsgId.get(key) ?? [];
    arr.push(tc);
    byMsgId.set(key, arr);
  }

  const out: Turn[] = [];
  let current: Turn | null = null;
  for (const m of input.messages) {
    if (m.role === 'user') {
      if (current) out.push(current);
      current = empty(m.id, m);
    } else if (m.role === 'assistant') {
      if (!current) current = empty(m.id, null);
      current.assistant = m;
      current.thinking = m.thinking ?? '';
      current.toolCalls = byMsgId.get(m.id) ?? [];
      out.push(current);
      current = null;
    }
  }
  if (input.streamingActive) {
    if (!current) {
      const k = `streaming:${input.streamingMessageId ?? 'pending'}`;
      current = empty(k, null);
    }
    const liveId = input.streamingMessageId ?? '';
    current.streamingThinking = input.streamingThinking;
    current.streamingContent = input.streamingText;
    current.toolCalls = [...current.toolCalls, ...(byMsgId.get(liveId) ?? [])];
    current.isStreaming = true;
    out.push(current);
  } else if (current) {
    out.push(current);
  }
  return out;
}
