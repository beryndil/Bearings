import { describe, expect, it } from 'vitest';
import {
  connectionLabel,
  messagesAsMarkdown,
  nextPermissionMode,
  pressureClass
} from './conversation-ui';

describe('pressureClass', () => {
  it('returns slate when no cap is set', () => {
    expect(pressureClass(5, null)).toBe('text-slate-500');
    expect(pressureClass(5, 0)).toBe('text-slate-500');
  });

  it('escalates through amber and rose as the ratio grows', () => {
    expect(pressureClass(0.5, 10)).toBe('text-slate-500');
    expect(pressureClass(8.5, 10)).toBe('text-amber-400');
    expect(pressureClass(10, 10)).toBe('text-rose-400');
  });
});

describe('connectionLabel', () => {
  it('prefers the retry countdown when reconnectDelayMs is set', () => {
    expect(connectionLabel('closed', 2500, null)).toBe('retrying in 3s');
  });

  it('maps the session-not-found close code to its own copy', () => {
    expect(connectionLabel('closed', null, 4404)).toBe('session not found');
    expect(connectionLabel('closed', null, 1000)).toBe('disconnected');
  });

  it.each([
    ['idle', 'idle'],
    ['connecting', 'connecting…'],
    ['open', 'connected'],
    ['error', 'error']
  ] as const)('renders %s as "%s"', (state, label) => {
    expect(connectionLabel(state, null, null)).toBe(label);
  });
});

describe('nextPermissionMode', () => {
  it('returns null for non-plan input', () => {
    expect(nextPermissionMode('hello', 'default')).toBeNull();
    expect(nextPermissionMode('/something', 'default')).toBeNull();
  });

  it('toggles between default and plan on a bare /plan', () => {
    expect(nextPermissionMode('/plan', 'default')).toBe('plan');
    expect(nextPermissionMode('/plan', 'plan')).toBe('default');
  });

  it('honors explicit on/off arguments', () => {
    expect(nextPermissionMode('/plan off', 'plan')).toBe('default');
    expect(nextPermissionMode('/plan default', 'plan')).toBe('default');
    expect(nextPermissionMode('/plan on', 'default')).toBe('plan');
  });
});

describe('messagesAsMarkdown', () => {
  it('emits ## role headers in order', () => {
    expect(
      messagesAsMarkdown([
        {
          id: 'a',
          session_id: 's',
          role: 'user',
          content: 'hi',
          thinking: null,
          created_at: 't'
        },
        {
          id: 'b',
          session_id: 's',
          role: 'assistant',
          content: 'hello',
          thinking: null,
          created_at: 't'
        }
      ])
    ).toBe('## user\n\nhi\n\n## assistant\n\nhello');
  });
});
