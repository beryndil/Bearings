import { voidFetch } from './core';

/** Kinds the backend's `/api/shell/open` dispatcher understands. Each
 * maps to a `shell.<kind>_command` key in `config.toml` — the server
 * returns 400 with the exact key name when the selected kind isn't
 * configured, so the frontend tooltip can be actionable. See
 * `src/bearings/api/routes_shell.py`. */
export type ShellKind =
  | 'editor'
  | 'terminal'
  | 'file_explorer'
  | 'git_gui'
  | 'claude_cli';

/** Ask the server to spawn a GUI app (editor / terminal / file
 * explorer / git GUI / Claude CLI) on `path`. Detached spawn — the
 * subprocess outlives this request. Resolves on 204 with no body.
 *
 * Throws when the server returns 400 ("shell.<kind>_command not
 * configured") so the caller can surface a stub toast pointing at the
 * exact config key. The thrown error's message includes the key name
 * verbatim; a context-menu handler can paste it straight into the
 * "Not yet configured" toast. */
export function openShell(
  kind: ShellKind,
  path: string,
  fetchImpl: typeof fetch = fetch
): Promise<void> {
  return voidFetch(fetchImpl, '/api/shell/open', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ kind, path })
  });
}
