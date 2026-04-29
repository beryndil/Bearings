/**
 * Typed client for ``POST /api/checklist-items/{id}/spawn-chat``
 * (item 1.7; ``src/bearings/web/routes/paired_chats.py``).
 *
 * Per ``docs/behavior/paired-chats.md`` §"Spawning a new pair" the
 * **💬 Work on this** click on an unpaired leaf creates a fresh chat
 * (201 Created) or returns the existing pair (200 OK on the
 * idempotent re-click). The spawn inherits the checklist's working
 * directory, model, and tags; the chat title defaults to the item's
 * label.
 *
 * Wire shapes mirror the Pydantic models in
 * :mod:`bearings.web.models.paired_chats`.
 */
import { apiChecklistItemEndpoint } from "../config";
import { postJson, type RequestOptions } from "./client";

/**
 * Response shape for ``POST /api/checklist-items/{id}/spawn-chat`` —
 * one-to-one with :class:`bearings.web.models.paired_chats.SpawnPairedChatOut`.
 *
 * ``created`` ``true`` on first spawn (HTTP 201); ``false`` when the
 * idempotent path returned an existing pair (HTTP 200). Callers
 * typically don't branch on this — the next ``getChecklistOverview``
 * refresh paints the pair regardless — but tests assert the value to
 * verify the idempotent path didn't double-spawn.
 *
 * Not exported: the consumers (PairedChatLinkSpawn) read the shape
 * via :func:`spawnPairedChat`'s return value without re-naming the
 * type at the call site.
 */
interface SpawnPairedChatOut {
  chat_session_id: string;
  item_id: number;
  title: string;
  working_dir: string;
  model: string;
  created: boolean;
}

interface SpawnPairedChatBody {
  /** Override the default chat title (the item's label). */
  title?: string | null;
  /** Optional plug — used by the auto-driver leg-spawn path. */
  plug?: string | null;
  /** ``"user"`` for human spawns; ``"driver"`` for auto-driver spawns. */
  spawned_by?: string;
}

/**
 * Spawn (or return the existing pair for) the checklist item's chat.
 *
 * @throws :class:`ApiError` on non-2xx — 404 for unknown item, 422 for
 *   parent-item / closed-chat / unresolvable working-directory paths.
 */
export async function spawnPairedChat(
  itemId: number,
  body: SpawnPairedChatBody = {},
  options: RequestOptions = {},
): Promise<SpawnPairedChatOut> {
  return await postJson<SpawnPairedChatOut>(
    `${apiChecklistItemEndpoint(itemId)}/spawn-chat`,
    body,
    options,
  );
}
