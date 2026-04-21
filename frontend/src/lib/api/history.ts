import { jsonFetch } from './core';
import type { Message, Session, ToolCall } from './sessions';

export type SearchHit = {
  message_id: string;
  session_id: string;
  session_title: string | null;
  model: string;
  role: string;
  snippet: string;
  created_at: string;
};

export function searchHistory(
  query: string,
  limit = 50,
  fetchImpl: typeof fetch = fetch
): Promise<SearchHit[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return jsonFetch<SearchHit[]>(fetchImpl, `/api/history/search?${params}`);
}

export type SessionExport = {
  session: Session;
  messages: Message[];
  tool_calls: ToolCall[];
};

export function exportSession(
  sessionId: string,
  fetchImpl: typeof fetch = fetch
): Promise<SessionExport> {
  return jsonFetch<SessionExport>(fetchImpl, `/api/sessions/${sessionId}/export`);
}

export function importSession(
  payload: SessionExport,
  fetchImpl: typeof fetch = fetch
): Promise<Session> {
  return jsonFetch<Session>(fetchImpl, '/api/sessions/import', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export type SystemPromptLayer = {
  name: string;
  kind: 'base' | 'session_description' | 'tag_memory' | 'session';
  content: string;
  token_count: number;
};

export type SystemPrompt = {
  layers: SystemPromptLayer[];
  total_tokens: number;
};

export function getSystemPrompt(
  sessionId: string,
  fetchImpl: typeof fetch = fetch
): Promise<SystemPrompt> {
  return jsonFetch<SystemPrompt>(fetchImpl, `/api/sessions/${sessionId}/system_prompt`);
}
