import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { notify, notifyPermission, notifySupported, requestNotifyPermission } from './notify';

type NotificationCtor = typeof Notification;

type NotificationMock = {
  body?: string;
  tag?: string;
  icon?: string;
  onclick: ((ev?: unknown) => void) | null;
  close: () => void;
};

const ctorCalls: Array<{ title: string; options: Record<string, unknown> }> = [];
let lastInstance: NotificationMock | null = null;

function installNotificationMock(permission: NotificationPermission): void {
  const Mock = function (
    this: NotificationMock,
    title: string,
    options: Record<string, unknown> = {}
  ) {
    ctorCalls.push({ title, options });
    this.body = options.body as string | undefined;
    this.tag = options.tag as string | undefined;
    this.icon = options.icon as string | undefined;
    this.onclick = null;
    this.close = vi.fn();
    lastInstance = this;
  } as unknown as NotificationCtor & { permission: NotificationPermission };

  Mock.permission = permission;
  Mock.requestPermission = vi.fn(async () => permission);

  vi.stubGlobal('Notification', Mock);
}

beforeEach(() => {
  ctorCalls.length = 0;
  lastInstance = null;
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('notifySupported / notifyPermission', () => {
  it('returns unsupported when Notification is missing', () => {
    vi.stubGlobal('Notification', undefined);
    expect(notifySupported()).toBe(false);
    expect(notifyPermission()).toBe('unsupported');
  });

  it('reports the browser permission state when supported', () => {
    installNotificationMock('granted');
    expect(notifySupported()).toBe(true);
    expect(notifyPermission()).toBe('granted');
  });
});

describe('requestNotifyPermission', () => {
  it('is a no-op when unsupported', async () => {
    vi.stubGlobal('Notification', undefined);
    await expect(requestNotifyPermission()).resolves.toBe('unsupported');
  });

  it('short-circuits when permission is already granted', async () => {
    installNotificationMock('granted');
    const result = await requestNotifyPermission();
    expect(result).toBe('granted');
    const NotificationMock = globalThis.Notification as unknown as {
      requestPermission: ReturnType<typeof vi.fn>;
    };
    expect(NotificationMock.requestPermission).not.toHaveBeenCalled();
  });

  it('prompts when permission is default', async () => {
    installNotificationMock('default');
    const result = await requestNotifyPermission();
    expect(result).toBe('default');
    const NotificationMock = globalThis.Notification as unknown as {
      requestPermission: ReturnType<typeof vi.fn>;
    };
    expect(NotificationMock.requestPermission).toHaveBeenCalledOnce();
  });
});

describe('notify', () => {
  it('is a silent no-op when unsupported', () => {
    vi.stubGlobal('Notification', undefined);
    expect(() => notify('hi')).not.toThrow();
  });

  it('does not construct a Notification when permission denied', () => {
    installNotificationMock('denied');
    notify('hi', { body: 'nope' });
    expect(ctorCalls).toHaveLength(0);
  });

  it('raises a Notification with body + tag + icon when granted', () => {
    installNotificationMock('granted');
    notify('Claude finished replying', { body: 'Session A', tag: 'sess-1' });
    expect(ctorCalls).toHaveLength(1);
    expect(ctorCalls[0].title).toBe('Claude finished replying');
    expect(ctorCalls[0].options).toMatchObject({
      body: 'Session A',
      tag: 'sess-1',
      icon: '/icon-192.png',
    });
  });

  it('click handler focuses the window and closes the notification', () => {
    installNotificationMock('granted');
    const focusSpy = vi.spyOn(window, 'focus').mockImplementation(() => {});
    notify('t');
    expect(lastInstance).not.toBeNull();
    lastInstance?.onclick?.();
    expect(focusSpy).toHaveBeenCalled();
    expect(lastInstance?.close).toHaveBeenCalled();
  });
});
