/**
 * Vault store — read-only filesystem index over ``~/.claude/plans/*.md``
 * + project ``TODO.md`` files (item 2.10; ``docs/behavior/vault.md``).
 *
 * Per arch §2.2 one canonical store per feature, one file. The vault
 * pane reads:
 *
 * - the bucketed list (plans + todos) returned by ``GET /api/vault``;
 * - the currently-selected doc body + redaction ranges (cache id);
 * - the search query + result envelope (debounced as the user types).
 *
 * The vault is **read-only** per vault.md §"CRUD flow". This module
 * exposes no create / update / delete helpers — a coding-standards
 * grep should turn up zero write affordances. Mutation against the
 * filesystem happens outside Bearings (the user's editor, git, agent
 * sessions); the store exposes :func:`refreshVault` so the UI can
 * re-read after the user expects fresh content.
 */
import {
  getVaultDoc,
  listVault,
  searchVault,
  type SearchResultOut,
  type VaultDocOut,
  type VaultListOut,
} from "../api/vault";

interface VaultState {
  /** Last successful response from ``GET /api/vault``; ``null`` until first load. */
  list: VaultListOut | null;
  /** Currently-selected doc (entry + body + redactions); ``null`` for none. */
  selected: VaultDocOut | null;
  /** Live search query (already-trimmed); empty string clears the result. */
  searchQuery: string;
  /** Last successful search response; ``null`` when no search is active. */
  searchResult: SearchResultOut | null;
  /** ``true`` while an index / doc / search refresh is in flight. */
  loading: boolean;
  /** ``true`` when ``selected`` is in flight (independent of ``loading``). */
  selectedLoading: boolean;
  /** Last error from the most recent attempt; cleared on success. */
  error: Error | null;
}

const state: VaultState = $state({
  list: null,
  selected: null,
  searchQuery: "",
  searchResult: null,
  loading: false,
  selectedLoading: false,
  error: null,
});

export const vaultStore = state;

let listController: AbortController | null = null;
let selectController: AbortController | null = null;
let searchController: AbortController | null = null;

/**
 * Refresh the bucketed list. Cancels any in-flight list call so the
 * latest user-triggered refresh wins. Called by the panel on mount,
 * by the explicit refresh button, and by :func:`runSearch` (which
 * shares the index because the server rescans every list request).
 */
export async function refreshVault(): Promise<void> {
  listController?.abort();
  const controller = new AbortController();
  listController = controller;
  state.loading = true;
  try {
    const list = await listVault({ signal: controller.signal });
    if (controller.signal.aborted) return;
    state.list = list;
    state.error = null;
  } catch (error) {
    if (controller.signal.aborted || isAbortError(error)) return;
    state.error = error instanceof Error ? error : new Error(String(error));
  } finally {
    if (listController === controller) {
      listController = null;
    }
    state.loading = false;
  }
}

/**
 * Open one vault doc by cache id. Cancels any in-flight select so a
 * rapid click on a different row doesn't paint stale content.
 */
export async function selectVaultDoc(vaultId: number): Promise<void> {
  selectController?.abort();
  const controller = new AbortController();
  selectController = controller;
  state.selectedLoading = true;
  try {
    const doc = await getVaultDoc(vaultId, { signal: controller.signal });
    if (controller.signal.aborted) return;
    state.selected = doc;
    state.error = null;
  } catch (error) {
    if (controller.signal.aborted || isAbortError(error)) return;
    state.error = error instanceof Error ? error : new Error(String(error));
  } finally {
    if (selectController === controller) {
      selectController = null;
    }
    state.selectedLoading = false;
  }
}

/** Clear the selected doc — collapses the reading panel. */
export function clearVaultSelection(): void {
  selectController?.abort();
  selectController = null;
  state.selected = null;
}

/**
 * Set the search query (caller should already have applied any debounce
 * at the input layer). Empty / whitespace-only clears the result; a
 * non-empty query schedules a :func:`runSearch` automatically so the
 * panel doesn't have to wire two calls.
 */
export async function setVaultSearchQuery(rawQuery: string): Promise<void> {
  state.searchQuery = rawQuery;
  if (rawQuery.trim() === "") {
    searchController?.abort();
    searchController = null;
    state.searchResult = null;
    return;
  }
  await runSearch(rawQuery);
}

async function runSearch(query: string): Promise<void> {
  searchController?.abort();
  const controller = new AbortController();
  searchController = controller;
  state.loading = true;
  try {
    const result = await searchVault(query, { signal: controller.signal });
    if (controller.signal.aborted) return;
    state.searchResult = result;
    state.error = null;
  } catch (error) {
    if (controller.signal.aborted || isAbortError(error)) return;
    state.error = error instanceof Error ? error : new Error(String(error));
  } finally {
    if (searchController === controller) {
      searchController = null;
    }
    state.loading = false;
  }
}

/** Test seam — restores the boot state without re-importing the module. */
export function _resetForTests(): void {
  listController?.abort();
  selectController?.abort();
  searchController?.abort();
  listController = null;
  selectController = null;
  searchController = null;
  state.list = null;
  state.selected = null;
  state.searchQuery = "";
  state.searchResult = null;
  state.loading = false;
  state.selectedLoading = false;
  state.error = null;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
