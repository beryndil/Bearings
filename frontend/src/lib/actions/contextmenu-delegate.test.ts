/**
 * Unit tests for the Phase 6 contextmenu-delegate Svelte action.
 *
 * The delegate is the bridge between raw `{@html}`-rendered Markdown
 * (code blocks, links) and the context-menu registry. We verify:
 *   - right-click on a `[data-bearings-code-block]` wrapper publishes a
 *     `code_block` target with the snapshotted text + language,
 *   - right-click on an `<a href>` publishes a `link` target,
 *   - anchors inside a code block take precedence (rare edge case, but
 *     a `<pre><a>…</a></pre>` shouldn't offer code actions),
 *   - right-click on plain text bubbles (no target published by the
 *     delegate — the outer article's `use:contextmenu` handles it),
 *   - `Ctrl+Shift+right-click` always defers to the native menu.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { contextMenu } from '$lib/context-menu/store.svelte';
import { contextmenuDelegate } from './contextmenu-delegate';

function rightClick(el: Element, init: MouseEventInit = {}): MouseEvent {
  const ev = new MouseEvent('contextmenu', {
    bubbles: true,
    cancelable: true,
    button: 2,
    ...init
  });
  el.dispatchEvent(ev);
  return ev;
}

beforeEach(() => {
  contextMenu.close();
});

afterEach(() => {
  contextMenu.close();
  document.body.innerHTML = '';
});

describe('contextmenuDelegate — code block', () => {
  it('opens a code_block target when clicking inside a wrapper', () => {
    const host = document.createElement('div');
    host.innerHTML = `
      <div data-bearings-code-block data-language="python">
        <pre class="shiki"><code>print("hi")</code></pre>
      </div>
    `;
    document.body.appendChild(host);
    const action = contextmenuDelegate(host, {
      sessionId: 's-1',
      messageId: 'm-1'
    });

    const code = host.querySelector('code')!;
    const ev = rightClick(code);

    expect(contextMenu.state.open).toBe(true);
    expect(contextMenu.state.target).toEqual({
      type: 'code_block',
      text: 'print("hi")',
      language: 'python',
      sessionId: 's-1',
      messageId: 'm-1'
    });
    expect(ev.defaultPrevented).toBe(true);

    action.destroy();
  });

  it('treats a missing data-language as null (fenceless block)', () => {
    const host = document.createElement('div');
    host.innerHTML = `
      <div data-bearings-code-block>
        <pre><code>echo hi</code></pre>
      </div>
    `;
    document.body.appendChild(host);
    const action = contextmenuDelegate(host, {
      sessionId: null,
      messageId: null
    });

    rightClick(host.querySelector('code')!);

    expect(contextMenu.state.target).toMatchObject({
      type: 'code_block',
      language: null,
      text: 'echo hi'
    });

    action.destroy();
  });
});

describe('contextmenuDelegate — link', () => {
  it('opens a link target when clicking an <a href>', () => {
    const host = document.createElement('div');
    host.innerHTML = `<p>see <a href="https://example.com">example</a></p>`;
    document.body.appendChild(host);
    const action = contextmenuDelegate(host, {
      sessionId: 's-1',
      messageId: 'm-1'
    });

    const anchor = host.querySelector('a')!;
    const ev = rightClick(anchor);

    expect(contextMenu.state.target).toEqual({
      type: 'link',
      href: 'https://example.com',
      text: 'example',
      sessionId: 's-1',
      messageId: 'm-1'
    });
    expect(ev.defaultPrevented).toBe(true);

    action.destroy();
  });

  it('prefers an anchor over an enclosing code block', () => {
    // Edge case: a code block containing an anchor. Link actions win
    // because "Open in new tab" is more useful than "Copy code" for a
    // pure link right-click.
    const host = document.createElement('div');
    host.innerHTML = `
      <div data-bearings-code-block data-language="html">
        <pre><code>click <a href="https://x.test">here</a></code></pre>
      </div>
    `;
    document.body.appendChild(host);
    const action = contextmenuDelegate(host, {
      sessionId: 's-1',
      messageId: 'm-1'
    });

    rightClick(host.querySelector('a')!);

    expect(contextMenu.state.target?.type).toBe('link');

    action.destroy();
  });
});

describe('contextmenuDelegate — passthrough', () => {
  it('does not open a menu on plain-text right-click', () => {
    const host = document.createElement('div');
    host.innerHTML = `<p>just some prose here</p>`;
    document.body.appendChild(host);
    const action = contextmenuDelegate(host, {
      sessionId: 's-1',
      messageId: 'm-1'
    });

    const ev = rightClick(host.querySelector('p')!);

    expect(contextMenu.state.open).toBe(false);
    // The outer article handler expects the event to be un-prevented
    // so its own `use:contextmenu` can fire on the bubble.
    expect(ev.defaultPrevented).toBe(false);

    action.destroy();
  });

  it('defers to native menu on Ctrl+Shift+right-click inside a code block', () => {
    const host = document.createElement('div');
    host.innerHTML = `
      <div data-bearings-code-block data-language="python">
        <pre><code>print("hi")</code></pre>
      </div>
    `;
    document.body.appendChild(host);
    const action = contextmenuDelegate(host, {
      sessionId: null,
      messageId: null
    });

    const ev = rightClick(host.querySelector('code')!, {
      ctrlKey: true,
      shiftKey: true
    });

    expect(contextMenu.state.open).toBe(false);
    expect(ev.defaultPrevented).toBe(false);

    action.destroy();
  });

  it('passes Shift alone through as advanced-mode flag', () => {
    const host = document.createElement('div');
    host.innerHTML = `<p>with <a href="file:///tmp/x">file</a></p>`;
    document.body.appendChild(host);
    const action = contextmenuDelegate(host, {
      sessionId: null,
      messageId: null
    });

    rightClick(host.querySelector('a')!, { shiftKey: true });

    expect(contextMenu.state.open).toBe(true);
    expect(contextMenu.state.advanced).toBe(true);

    action.destroy();
  });
});

describe('contextmenuDelegate — binding updates', () => {
  it('picks up new sessionId / messageId via update()', () => {
    const host = document.createElement('div');
    host.innerHTML = `<p><a href="https://example.com">x</a></p>`;
    document.body.appendChild(host);
    const action = contextmenuDelegate(host, {
      sessionId: 's-1',
      messageId: 'm-1'
    });
    action.update({ sessionId: 's-2', messageId: 'm-9' });

    rightClick(host.querySelector('a')!);

    expect(contextMenu.state.target).toMatchObject({
      sessionId: 's-2',
      messageId: 'm-9'
    });

    action.destroy();
  });
});
