import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render } from '@testing-library/svelte';

// Test-scoped controllable stand-in for the agent singleton. The
// component reads `agent.permissionMode` and `agent.state` and calls
// `agent.setPermissionMode(next)` on change; that's the whole surface.
const setPermissionMode = vi.fn();
const agentStub: {
  permissionMode: 'default' | 'plan' | 'acceptEdits' | 'bypassPermissions';
  state: 'idle' | 'connecting' | 'open' | 'closed' | 'error';
  setPermissionMode: (mode: string) => boolean;
} = {
  permissionMode: 'default',
  state: 'open',
  setPermissionMode: (mode: string) => {
    setPermissionMode(mode);
    agentStub.permissionMode =
      mode as typeof agentStub.permissionMode;
    return true;
  }
};

vi.mock('$lib/agent.svelte', () => ({
  get agent() {
    return agentStub;
  }
}));

// Imported after vi.mock so the component picks up the mocked module.
const { default: PermissionModeSelector } = await import('./PermissionModeSelector.svelte');

beforeEach(() => {
  setPermissionMode.mockReset();
  agentStub.permissionMode = 'default';
  agentStub.state = 'open';
});

afterEach(() => cleanup());

describe('PermissionModeSelector', () => {
  it('renders all four modes as options', () => {
    const { getByTestId } = render(PermissionModeSelector);
    const select = getByTestId('permission-mode-select') as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual([
      'default',
      'plan',
      'acceptEdits',
      'bypassPermissions'
    ]);
  });

  it('reflects the current permission mode as the selected option', () => {
    agentStub.permissionMode = 'bypassPermissions';
    const { getByTestId } = render(PermissionModeSelector);
    const select = getByTestId('permission-mode-select') as HTMLSelectElement;
    expect(select.value).toBe('bypassPermissions');
  });

  it('applies tone class matching the current mode', () => {
    agentStub.permissionMode = 'acceptEdits';
    const { getByTestId } = render(PermissionModeSelector);
    const select = getByTestId('permission-mode-select');
    // Amber tone is the Auto-edit warning level — the exact class is
    // asserted so a style regression (e.g. silently dropping the amber
    // tier) fails the test rather than shipping a flat-looking UI.
    expect(select.className).toContain('bg-amber-900');
  });

  it('dispatches setPermissionMode on change', async () => {
    const { getByTestId } = render(PermissionModeSelector);
    const select = getByTestId('permission-mode-select') as HTMLSelectElement;
    await fireEvent.change(select, { target: { value: 'bypassPermissions' } });
    expect(setPermissionMode).toHaveBeenCalledWith('bypassPermissions');
  });

  it('disables the control when the socket is not open', () => {
    agentStub.state = 'closed';
    const { getByTestId } = render(PermissionModeSelector);
    const select = getByTestId('permission-mode-select') as HTMLSelectElement;
    expect(select).toBeDisabled();
  });

  it('exposes the current mode hint as the title attribute', () => {
    agentStub.permissionMode = 'bypassPermissions';
    const { getByTestId } = render(PermissionModeSelector);
    const select = getByTestId('permission-mode-select');
    // The hint copy is the safety affordance — confirm the dangerous
    // mode gets a warning-flavored description surfaced to the user.
    expect(select.getAttribute('title')).toMatch(/every tool call/i);
  });
});
