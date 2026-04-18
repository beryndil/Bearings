import * as api from '$lib/api';
import { conversation } from '$lib/stores/conversation.svelte';

export type ConnectionState = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

class AgentConnection {
  state = $state<ConnectionState>('idle');
  sessionId = $state<string | null>(null);
  lastCloseCode = $state<number | null>(null);

  private socket: WebSocket | null = null;

  async connect(sessionId: string): Promise<void> {
    this.close();
    this.sessionId = sessionId;
    this.state = 'connecting';
    this.lastCloseCode = null;
    await conversation.load(sessionId);

    const ws = api.openAgentSocket(sessionId);
    this.socket = ws;

    ws.addEventListener('open', () => {
      this.state = 'open';
    });

    ws.addEventListener('message', (msg) => {
      try {
        const event = JSON.parse(msg.data) as api.AgentEvent;
        conversation.handleEvent(event);
      } catch (e) {
        conversation.error = e instanceof Error ? e.message : String(e);
      }
    });

    ws.addEventListener('close', (ev) => {
      this.state = 'closed';
      this.lastCloseCode = ev.code;
      this.socket = null;
    });

    ws.addEventListener('error', () => {
      this.state = 'error';
    });
  }

  send(prompt: string): boolean {
    if (!this.socket || this.state !== 'open' || !this.sessionId) return false;
    conversation.pushUserMessage(this.sessionId, prompt);
    this.socket.send(JSON.stringify({ type: 'prompt', content: prompt }));
    return true;
  }

  close(): void {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.state = 'idle';
  }
}

export const agent = new AgentConnection();
