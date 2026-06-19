/**
 * Typed client for shell-open context-menu actions (M-12/R-4).
 *
 * GUI-targeting openers (editor, file explorer, terminal) use
 * ``POST /api/shell/open`` — fire-and-forget semantics (204 response)
 * so the HTTP response returns immediately without waiting for the
 * child process to exit.
 *
 * The blocking ``POST /api/shell/exec`` endpoint is kept in config.ts
 * for callers that genuinely need stdout/stderr/exit-code.
 *
 * Behavior anchor:
 * ``docs/behavior/context-menus.md`` §"Shell-open integration".
 */
import { API_SHELL_OPEN_ENDPOINT } from "../config";
import { ApiError } from "./client";

// ---- Wire shapes ------------------------------------------------------------

interface ShellOpenIn {
  readonly argv: readonly string[];
}

// ---- Helpers ----------------------------------------------------------------

/**
 * Return the parent directory of an absolute ``path`` by stripping the
 * last path component.  Falls back to ``/`` for bare top-level paths.
 */
function parentDir(path: string): string {
  const idx = path.lastIndexOf("/");
  return idx > 0 ? path.slice(0, idx) : "/";
}

/**
 * Dispatch a fire-and-forget shell open via ``POST /api/shell/open``.
 * Returns when the server confirms the spawn (204). Throws
 * :class:`ApiError` on non-2xx.
 */
async function _open(argv: readonly string[]): Promise<void> {
  const response = await fetch(API_SHELL_OPEN_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ argv } satisfies ShellOpenIn),
  });
  if (response.status >= 200 && response.status < 300) return;
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    try {
      body = await response.text();
    } catch {
      // ignore
    }
  }
  throw new ApiError(
    response.status,
    body,
    `POST ${API_SHELL_OPEN_ENDPOINT} → ${response.status} ${response.statusText}`,
  );
}

// ---- Public API -------------------------------------------------------------

/**
 * Open ``path`` in the user's default editor via ``xdg-open``
 * (fire-and-forget — returns 204 immediately).
 *
 * Throws :class:`ApiError` on a non-2xx response.
 */
export async function shellOpenInEditor(path: string): Promise<void> {
  await _open(["xdg-open", path]);
}

/**
 * Open the parent directory of ``path`` in the file manager via
 * ``xdg-open`` (fire-and-forget — returns 204 immediately).
 *
 * Throws :class:`ApiError` on a non-2xx response.
 */
export async function shellRevealInExplorer(path: string): Promise<void> {
  await _open(["xdg-open", parentDir(path)]);
}

/**
 * Open ``dir`` via ``xdg-open`` (fire-and-forget — returns 204
 * immediately).  On most desktop environments this opens a file
 * manager; users who have associated directories with a terminal
 * emulator in their XDG MIME database will get a terminal window.
 *
 * Throws :class:`ApiError` on a non-2xx response.
 */
export async function shellOpenInTerminal(dir: string): Promise<void> {
  await _open(["xdg-open", dir]);
}
