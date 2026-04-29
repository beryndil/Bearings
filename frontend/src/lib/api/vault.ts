/**
 * Typed client for the read-only vault surface (item 1.5;
 * ``src/bearings/web/routes/vault.py``).
 *
 * Per ``docs/behavior/vault.md`` the vault is a read-only filesystem
 * index over ``~/.claude/plans/*.md`` + project ``TODO.md`` files —
 * the user can list, open, search, and copy out, but cannot create /
 * edit / rename / delete. This module surfaces the four observation
 * endpoints and intentionally exposes no write helpers so a
 * coding-standards review can grep this file and verify the read-only
 * semantic at the wire boundary.
 *
 * Wire shapes mirror the Pydantic models in
 * :mod:`bearings.web.models.vault`. A field rename on the backend MUST
 * be reflected here in the same commit; the route handlers use
 * ``extra="forbid"`` so a stray TS field also surfaces at the wire
 * boundary as a 422.
 */
import {
  API_VAULT_ENDPOINT,
  API_VAULT_BY_PATH_ENDPOINT,
  API_VAULT_SEARCH_ENDPOINT,
  vaultDocEndpoint,
  type VaultKind,
} from "../config";
import { getJson, type RequestOptions } from "./client";

/**
 * Wire shape for one vault row — one-to-one with
 * :class:`bearings.web.models.vault.VaultEntryOut`.
 *
 * ``markdown_link`` is server-computed (assembled by
 * :func:`bearings.agent.vault.build_markdown_link`) so the client
 * doesn't have to re-derive ``[Title](file:///abs/path)`` and risk
 * drifting from the linkifier's escape rules — see vault.md
 * §"Paste-into-message behavior".
 */
export interface VaultEntryOut {
  id: number;
  path: string;
  slug: string;
  title: string | null;
  /** Mirrors :const:`VAULT_KIND_PLAN` / :const:`VAULT_KIND_TODO`. */
  kind: VaultKind;
  mtime: number;
  size: number;
  last_indexed_at: number;
  markdown_link: string;
}

/**
 * Bucketed list shape — one-to-one with
 * :class:`bearings.web.models.vault.VaultListOut`. ``plan_roots`` /
 * ``todo_globs`` round-trip the configured paths so the empty-state
 * UI can name them per vault.md §"empty state" — "No plans found
 * under <configured roots>".
 */
export interface VaultListOut {
  plans: VaultEntryOut[];
  todos: VaultEntryOut[];
  plan_roots: string[];
  todo_globs: string[];
}

/**
 * One redaction range — mirrors :class:`bearings.web.models.vault.
 * RedactionOut`. The reading panel masks the slice ``body[offset,
 * offset + length)`` until the user toggles Show.
 */
export interface RedactionOut {
  offset: number;
  length: number;
  /** Detection pattern label (e.g. ``"key=value"``); useful for tooltips. */
  pattern: string;
}

/**
 * Single-doc shape — mirrors :class:`bearings.web.models.vault.
 * VaultDocOut`. ``body`` is the raw markdown; ``redactions`` is the
 * list of byte ranges the renderer should mask. ``truncated`` is
 * ``true`` when the on-disk size exceeded the server-side cap and the
 * tail was elided (vault.md §"Failure modes" — "Read error on a
 * single doc").
 */
export interface VaultDocOut {
  entry: VaultEntryOut;
  body: string;
  redactions: RedactionOut[];
  truncated: boolean;
}

/**
 * One search hit — mirrors :class:`bearings.web.models.vault.
 * SearchHitOut`. ``vault_id`` lets the UI cross-reference back into
 * the bucketed list when the user clicks a hit.
 */
export interface SearchHitOut {
  vault_id: number;
  path: string;
  title: string | null;
  kind: VaultKind;
  line_number: number;
  snippet: string;
}

/**
 * Search-result envelope. ``capped`` is the truthy flag the UI uses
 * to surface the "showing first N — narrow your query" indicator
 * per vault.md §"Search semantics".
 */
export interface SearchResultOut {
  hits: SearchHitOut[];
  capped: boolean;
}

/**
 * ``GET /api/vault`` — re-scans the filesystem and returns the
 * bucketed list. Per vault.md §"Failure modes" the index re-scans on
 * every list request, so callers don't need a separate "refresh"
 * action — just call :func:`listVault` again.
 */
export async function listVault(options: RequestOptions = {}): Promise<VaultListOut> {
  return await getJson<VaultListOut>(API_VAULT_ENDPOINT, options);
}

/**
 * ``GET /api/vault/search?q=...`` — case-insensitive substring
 * search. Whitespace-only queries return an empty result on the
 * server; the client passes them through verbatim and the empty-
 * state copy renders.
 */
export async function searchVault(
  query: string,
  options: RequestOptions = {},
): Promise<SearchResultOut> {
  const merged: RequestOptions = { ...options, query: [["q", query]] };
  return await getJson<SearchResultOut>(API_VAULT_SEARCH_ENDPOINT, merged);
}

/**
 * ``GET /api/vault/{id}`` — open by cache id. Read errors return
 * an empty body + empty redactions per vault.md §"Failure modes" —
 * "Read error on a single doc"; the entry metadata still surfaces.
 */
export async function getVaultDoc(
  vaultId: number,
  options: RequestOptions = {},
): Promise<VaultDocOut> {
  return await getJson<VaultDocOut>(vaultDocEndpoint(vaultId), options);
}

/**
 * ``GET /api/vault/by-path?path=...`` — open by absolute path.
 * The server resolves symlinks before the allowlist check (vault.md
 * §"Failure modes" — "Path outside the vault"); a path that resolves
 * outside the configured roots returns 404.
 */
export async function getVaultDocByPath(
  path: string,
  options: RequestOptions = {},
): Promise<VaultDocOut> {
  const merged: RequestOptions = { ...options, query: [["path", path]] };
  return await getJson<VaultDocOut>(API_VAULT_BY_PATH_ENDPOINT, merged);
}
