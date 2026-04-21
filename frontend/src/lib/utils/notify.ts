/**
 * Thin wrapper around the browser's `Notification` API used to raise
 * desktop/tray notifications when an agent turn completes.
 *
 * Localhost (`127.0.0.1`) counts as a secure context for the
 * Notification API in Chromium and Firefox, so Bearings can call it
 * without HTTPS. The API is still unavailable in SSR (node) and in
 * browsers that never shipped it, so every entry point guards on
 * `typeof Notification !== 'undefined'` and returns a safe default.
 *
 * On Linux (KDE / Hyprland + mako / GNOME Shell) the browser forwards
 * notifications through the desktop portal — they land in the tray /
 * notification history exactly like any other app's.
 */

export type NotifyPermission = 'default' | 'granted' | 'denied' | 'unsupported';

export function notifySupported(): boolean {
  return typeof Notification !== 'undefined';
}

export function notifyPermission(): NotifyPermission {
  if (!notifySupported()) return 'unsupported';
  return Notification.permission;
}

/** Ask the browser for notification permission. Returns the resulting
 * permission state. Idempotent: a granted/denied answer is returned
 * immediately without re-prompting. */
export async function requestNotifyPermission(): Promise<NotifyPermission> {
  if (!notifySupported()) return 'unsupported';
  if (Notification.permission !== 'default') return Notification.permission;
  try {
    return await Notification.requestPermission();
  } catch {
    // Older Safari returns a callback-style API. Not a supported target,
    // but fall back to whatever the browser recorded.
    return Notification.permission;
  }
}

export type NotifyOptions = {
  /** Notification body. Kept short — most DEs truncate aggressively. */
  body?: string;
  /** Dedup key. A later notification with the same tag silently
   * replaces the earlier one on Linux DEs, so rapid-fire turns don't
   * pile up in the tray. */
  tag?: string;
};

/** Raise a notification. No-op when unsupported or permission isn't
 * granted — callers don't need to re-check. Clicking the notification
 * focuses the Bearings window. */
export function notify(title: string, options: NotifyOptions = {}): void {
  if (!notifySupported()) return;
  if (Notification.permission !== 'granted') return;
  try {
    const n = new Notification(title, {
      body: options.body,
      tag: options.tag,
      icon: '/icon-192.png'
    });
    n.onclick = () => {
      try {
        window.focus();
      } catch {
        // window.focus can throw in hardened contexts; swallow — the
        // notification still closes below.
      }
      n.close();
    };
  } catch {
    // Constructing Notification can throw on some permission edge
    // cases (e.g. permission revoked between the check above and
    // the constructor). Swallow — the user asked for a nicety, not
    // a hard dependency.
  }
}
