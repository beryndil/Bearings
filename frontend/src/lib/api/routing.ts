/**
 * Typed client for ``POST /api/routing/preview`` (spec §6 + §9).
 *
 * The new-session dialog (item 2.4 / spec §6) calls this on every
 * keystroke (debounced 300 ms per
 * :data:`ROUTING_PREVIEW_DEBOUNCE_MS` in ``../config``). Backend
 * route + Pydantic shapes:
 *
 * * route — :func:`bearings.web.routes.routing.preview_routing`
 *   (``src/bearings/web/routes/routing.py:389``);
 * * request — :class:`bearings.web.models.routing.RoutingPreviewIn`;
 * * response — :class:`bearings.web.models.routing.RoutingPreviewOut`.
 */
import { API_ROUTING_PREVIEW_ENDPOINT } from "../config";
import { postJson, type RequestOptions } from "./client";

/**
 * Request body for ``POST /api/routing/preview`` (spec §9).
 *
 * Mirrors :class:`bearings.web.models.routing.RoutingPreviewIn`.
 * Internal-only — :func:`previewRouting`'s body parameter is the
 * single consumer and the parameter is typed inline.
 */
interface RoutingPreviewRequest {
  /** Tag ids attached to the session-to-be (priority-ordered server-side). */
  tags: number[];
  /** First user message body — empty string is valid (spec §9 default). */
  message: string;
}

/**
 * Response body for ``POST /api/routing/preview`` (spec §9).
 *
 * Mirrors :class:`bearings.web.models.routing.RoutingPreviewOut`. The
 * dialog reads ``executor`` / ``advisor`` / ``advisor_max_uses`` /
 * ``effort`` to populate the two-axis selector defaults; ``source`` +
 * ``reason`` for the "Routed from…" line; ``quota_downgrade_applied``
 * to render the yellow downgrade banner with the "Use anyway"
 * override; ``quota_state`` to render the in-dialog QuotaBars when a
 * preview already carries a fresh snapshot.
 */
export interface RoutingPreview {
  executor: string;
  advisor: string | null;
  advisor_max_uses: number;
  effort: string;
  source: string;
  reason: string;
  matched_rule_id: number | null;
  evaluated_rules: number[];
  quota_downgrade_applied: boolean;
  quota_state: Record<string, number>;
}

/**
 * Resolve routing for the supplied tags + first message.
 *
 * @throws :class:`ApiError` on a non-2xx response. The dialog
 *   surfaces the failure via the preview-error string so the user
 *   sees something rather than a stuck spinner.
 */
export async function previewRouting(
  body: RoutingPreviewRequest,
  options: { signal?: AbortSignal } = {},
): Promise<RoutingPreview> {
  const requestOptions: RequestOptions = {};
  if (options.signal !== undefined) {
    requestOptions.signal = options.signal;
  }
  return await postJson<RoutingPreview>(API_ROUTING_PREVIEW_ENDPOINT, body, requestOptions);
}
