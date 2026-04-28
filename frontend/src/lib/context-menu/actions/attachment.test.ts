/**
 * Frozen ID snapshot per plan §7.4 — Phase 14 of docs/context-menu-plan.md.
 *
 * Attachment action IDs are public API for `~/.config/bearings/menus.toml`
 * overrides (pin / hide / shortcut binds). Renames must go through
 * `Action.aliases` with a deprecation warning, never silently.
 */

import { describe, expect, it } from 'vitest';

import { ATTACHMENT_ACTIONS } from './attachment';
import type { AttachmentTarget } from '../types';

const COMPOSER: AttachmentTarget = {
  type: 'attachment',
  n: 1,
  path: '/abs/path/to/file.png',
  filename: 'file.png',
  size_bytes: 1024,
  sessionId: 's-1',
  messageId: null,
};

const SENT: AttachmentTarget = {
  type: 'attachment',
  n: 2,
  path: '/abs/path/to/sent.txt',
  filename: 'sent.txt',
  size_bytes: 256,
  sessionId: 's-1',
  messageId: 'm-1',
};

describe('attachment.ts — action-ID stability', () => {
  it('exposes the frozen v0.16.0 catalog', () => {
    const ids = ATTACHMENT_ACTIONS.map((a) => a.id).sort();
    expect(ids).toEqual([
      'attachment.copy_filename',
      'attachment.copy_path',
      'attachment.open_in.editor',
      'attachment.open_in.file_explorer',
      'attachment.remove',
    ]);
  });

  it('every ID follows `attachment.<verb>[.<qualifier>]` naming', () => {
    for (const a of ATTACHMENT_ACTIONS) {
      expect(a.id.startsWith('attachment.')).toBe(true);
      expect(a.id).toMatch(/^attachment\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$/);
    }
  });

  it('remove is destructive, copy actions live under copy section', () => {
    const remove = ATTACHMENT_ACTIONS.find((a) => a.id === 'attachment.remove');
    const copyPath = ATTACHMENT_ACTIONS.find((a) => a.id === 'attachment.copy_path');
    expect(remove?.destructive).toBe(true);
    expect(remove?.section).toBe('destructive');
    expect(copyPath?.section).toBe('copy');
  });

  it('remove is disabled on already-sent attachments, enabled in composer', () => {
    const remove = ATTACHMENT_ACTIONS.find((a) => a.id === 'attachment.remove');
    expect(remove?.disabled?.(COMPOSER)).toBeNull();
    expect(remove?.disabled?.(SENT)).toBeTruthy();
  });
});
