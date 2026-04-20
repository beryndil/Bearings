import { jsonFetch } from './core';

export type FsEntry = {
  name: string;
  path: string;
};

export type FsList = {
  path: string;
  parent: string | null;
  entries: FsEntry[];
};

export type FsListOptions = {
  path?: string | null;
  hidden?: boolean;
};

export function listDir(
  opts: FsListOptions = {},
  fetchImpl: typeof fetch = fetch
): Promise<FsList> {
  const params = new URLSearchParams();
  if (opts.path) params.set('path', opts.path);
  if (opts.hidden) params.set('hidden', 'true');
  const query = params.toString();
  return jsonFetch<FsList>(fetchImpl, `/api/fs/list${query ? `?${query}` : ''}`);
}
