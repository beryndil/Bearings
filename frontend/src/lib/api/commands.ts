import { jsonFetch } from './core';

export type CommandKind = 'command' | 'skill';
export type CommandScope = 'user' | 'project' | 'plugin';

export type CommandEntry = {
  slug: string;
  description: string;
  kind: CommandKind;
  scope: CommandScope;
  source_path: string;
};

export type CommandsList = {
  entries: CommandEntry[];
};

/** Fetch the palette of slash commands + skills. Pass the session's
 *  `working_dir` as `cwd` so any project-local `.claude/commands` are
 *  included with highest precedence. */
export function listCommands(
  cwd: string | null | undefined,
  fetchImpl: typeof fetch = fetch
): Promise<CommandsList> {
  const query = cwd ? `?cwd=${encodeURIComponent(cwd)}` : '';
  return jsonFetch<CommandsList>(fetchImpl, `/api/commands${query}`);
}
