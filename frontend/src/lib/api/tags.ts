/**
 * Typed client for ``GET /api/tags`` and ``GET /api/sessions/{id}/tags``.
 *
 * Mirrors :class:`bearings.web.models.tags.TagOut`. Per
 * ``docs/behavior/chat.md`` the user observes tag chips on every
 * session row; the sidebar reads the per-session list to render those
 * chips and the global list to populate the filter panel.
 */
import { API_TAGS_ENDPOINT, sessionTagsEndpoint } from "../config";
import { getJson, type RequestOptions } from "./client";

/**
 * Wire shape for one tag — one-to-one with
 * :class:`bearings.web.models.tags.TagOut`. The ``group`` field is
 * derived on the backend (slash-prefix of ``name``) and round-tripped
 * here so the filter-panel UI doesn't have to reparse names.
 */
export interface TagOut {
  id: number;
  name: string;
  color: string | null;
  default_model: string | null;
  working_dir: string | null;
  group: string | null;
  created_at: string;
  updated_at: string;
}

interface ListTagsParams {
  /** Optional group prefix; matches via the backend's ``LIKE "<group>/%"``. */
  group?: string;
  signal?: AbortSignal;
}

export async function listTags(params: ListTagsParams = {}): Promise<TagOut[]> {
  const options: RequestOptions = {};
  if (params.group !== undefined) {
    options.query = [["group", params.group]];
  }
  if (params.signal !== undefined) {
    options.signal = params.signal;
  }
  return await getJson<TagOut[]>(API_TAGS_ENDPOINT, options);
}

export async function listSessionTags(
  sessionId: string,
  params: { signal?: AbortSignal } = {},
): Promise<TagOut[]> {
  const options: RequestOptions = {};
  if (params.signal !== undefined) {
    options.signal = params.signal;
  }
  return await getJson<TagOut[]>(sessionTagsEndpoint(sessionId), options);
}
