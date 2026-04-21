import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ApprovalRequestEvent } from '$lib/api';
import ApprovalModal from './ApprovalModal.svelte';

afterEach(cleanup);

function fakeRequest(overrides: Partial<ApprovalRequestEvent> = {}): ApprovalRequestEvent {
  return {
    type: 'approval_request',
    session_id: 'sess-1',
    request_id: 'req-1',
    tool_name: 'ExitPlanMode',
    input: { plan: '# plan' },
    tool_use_id: 'tu_1',
    ...overrides
  };
}

describe('ApprovalModal', () => {
  it('renders the tool name and pretty-printed input', () => {
    const onRespond = vi.fn(() => true);
    const { getByText, getByTestId } = render(ApprovalModal, {
      request: fakeRequest(),
      connected: true,
      onRespond
    });
    expect(getByText('ExitPlanMode')).toBeInTheDocument();
    // JSON.stringify with spaces produces the plan value on its own line.
    expect(getByTestId('approval-input').textContent).toContain('"plan": "# plan"');
  });

  it('Approve button calls onRespond with the allow decision', async () => {
    const onRespond = vi.fn(() => true);
    const { getByTestId } = render(ApprovalModal, {
      request: fakeRequest(),
      connected: true,
      onRespond
    });
    await fireEvent.click(getByTestId('approval-allow'));
    expect(onRespond).toHaveBeenCalledWith('req-1', 'allow');
  });

  it('Deny button calls onRespond with the deny decision', async () => {
    const onRespond = vi.fn(() => true);
    const { getByTestId } = render(ApprovalModal, {
      request: fakeRequest({ request_id: 'req-2' }),
      connected: true,
      onRespond
    });
    await fireEvent.click(getByTestId('approval-deny'));
    expect(onRespond).toHaveBeenCalledWith('req-2', 'deny');
  });

  it('disables buttons while the socket is disconnected', () => {
    const onRespond = vi.fn(() => true);
    const { getByTestId, getByText } = render(ApprovalModal, {
      request: fakeRequest(),
      connected: false,
      onRespond
    });
    expect(getByTestId('approval-allow')).toBeDisabled();
    expect(getByTestId('approval-deny')).toBeDisabled();
    expect(getByText(/Reconnecting/)).toBeInTheDocument();
  });

  it('swallows Escape so the gate cannot be closed without a click', async () => {
    const onRespond = vi.fn(() => true);
    render(ApprovalModal, { request: fakeRequest(), connected: true, onRespond });

    // Outer handler the modal must block. If Escape propagated, this
    // spy would fire. The modal registers a capture-phase listener
    // that calls stopPropagation, so the outer one must stay silent.
    const outer = vi.fn();
    window.addEventListener('keydown', outer);
    try {
      await fireEvent.keyDown(document.body, { key: 'Escape' });
      expect(outer).not.toHaveBeenCalled();
      expect(onRespond).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener('keydown', outer);
    }
  });

  it('shows "Approving…" on the approve button while response is in-flight', async () => {
    const onRespond = vi.fn(() => true);
    const { getByTestId } = render(ApprovalModal, {
      request: fakeRequest(),
      connected: true,
      onRespond
    });
    const allow = getByTestId('approval-allow');
    await fireEvent.click(allow);
    expect(allow.textContent?.trim()).toBe('Approving…');
    expect(allow).toBeDisabled();
    // Deny should also be disabled so a double-click can't race.
    expect(getByTestId('approval-deny')).toBeDisabled();
  });

  it('re-enables buttons when the send fails (socket dropped)', async () => {
    // onRespond returns false when the agent connection is idle —
    // leave the modal visible so the user can retry after reconnect.
    const onRespond = vi.fn(() => false);
    const { getByTestId } = render(ApprovalModal, {
      request: fakeRequest(),
      connected: true,
      onRespond
    });
    const allow = getByTestId('approval-allow');
    await fireEvent.click(allow);
    expect(allow).not.toBeDisabled();
    expect(allow.textContent?.trim()).toBe('Approve');
  });
});
