/**
 * Typed clients for the ``/api/usage/*`` surface (spec §9).
 *
 * Backend route module: :mod:`bearings.web.routes.usage`. Pydantic
 * shapes: :class:`bearings.web.models.usage.UsageByModelRow` /
 * :class:`OverrideRateOut` (``src/bearings/web/models/usage.py``).
 *
 * Consumers:
 *
 * * :class:`InspectorUsage` (item 2.6) — calls :func:`getUsageByModel`
 *   for the by-model table and the advisor-effectiveness widget;
 *   :func:`getOverrideRates` for the rules-to-review list.
 * * Item 2.7's RoutingRuleEditor will reuse :func:`getOverrideRates`
 *   for the inline "Review:" highlight.
 *
 * The clients are deliberately thin — every error surface (503 from
 * a missing DB, 422 from an unknown ``period``) flows through
 * :class:`ApiError`; the InspectorUsage container renders the
 * documented copy in :data:`INSPECTOR_STRINGS.usageError`.
 */
import {
  API_USAGE_BY_MODEL_ENDPOINT,
  API_USAGE_OVERRIDE_RATES_ENDPOINT,
  OVERRIDE_RATE_WINDOW_DAYS,
} from "../config";
import { getJson, type RequestOptions } from "./client";

/**
 * Period accepted by ``GET /api/usage/by_model``. Mirrors the
 * server-side ``_KNOWN_USAGE_PERIODS`` alphabet
 * (``src/bearings/web/routes/usage.py:38``). The wire type is a bare
 * string so callers can interpolate freely; this union narrows the
 * compile-time surface to the documented values.
 *
 * Internal-only — :func:`getUsageByModel`'s ``period`` parameter is
 * the single consumer; widening to ``export`` waits until a second
 * caller (item 2.7's RoutingRuleEditor) needs the symbol.
 */
type UsagePeriod = "day" | "week";

/**
 * One row of ``GET /api/usage/by_model?period=week`` (spec §9 +
 * §App A). Mirrors :class:`bearings.web.models.usage.UsageByModelRow`.
 *
 * The endpoint emits one row per model+role pair: an "executor" row
 * sums the per-message executor token columns; an "advisor" row sums
 * the per-message advisor columns. ``cache_read_tokens`` is zeroed on
 * advisor rows because cache reads are an executor-side measure.
 */
export interface UsageByModelRow {
  model: string;
  /** ``"executor"`` or ``"advisor"`` per the backend aggregation. */
  role: string;
  input_tokens: number;
  output_tokens: number;
  advisor_calls: number;
  cache_read_tokens: number;
  sessions: number;
}

/**
 * One row of ``GET /api/usage/override_rates?days=14`` (spec §8 +
 * §10). Mirrors :class:`bearings.web.models.usage.OverrideRateOut`.
 *
 * ``review`` is server-computed against
 * :data:`OVERRIDE_RATE_REVIEW_THRESHOLD` so the UI doesn't re-decide
 * the threshold; the table highlights rows whose ``review`` is
 * ``true``. ``rule_kind`` is ``"tag"`` or ``"system"`` per the
 * underlying rule table.
 */
export interface OverrideRateOut {
  rule_kind: string;
  rule_id: number;
  fired_count: number;
  overridden_count: number;
  rate: number;
  review: boolean;
}

/**
 * Fetch the per-model token totals for the requested period.
 *
 * Period defaults to ``"week"`` to match the spec §10 "By model
 * table" surface (which shows the rolling-7-day rollup); the
 * parameter is widened to the full alphabet so a future "today"
 * pivot can reuse the same client.
 *
 * @throws :class:`ApiError` on non-2xx — 422 for an unknown
 *   ``period``, 503 when the DB connection is unavailable.
 */
export async function getUsageByModel(
  options: { period?: UsagePeriod; signal?: AbortSignal } = {},
): Promise<UsageByModelRow[]> {
  const period = options.period ?? "week";
  const requestOptions: RequestOptions = { query: [["period", period]] };
  if (options.signal !== undefined) {
    requestOptions.signal = options.signal;
  }
  return await getJson<UsageByModelRow[]>(API_USAGE_BY_MODEL_ENDPOINT, requestOptions);
}

/**
 * Fetch per-rule override rates for the rolling window.
 *
 * Window defaults to :data:`OVERRIDE_RATE_WINDOW_DAYS` (14 days per
 * spec §8); the parameter clamps server-side to ``[1, 365]``.
 *
 * @throws :class:`ApiError` on non-2xx — 422 for an out-of-range
 *   ``days`` value, 503 when the DB connection is unavailable.
 */
export async function getOverrideRates(
  options: { days?: number; signal?: AbortSignal } = {},
): Promise<OverrideRateOut[]> {
  const days = options.days ?? OVERRIDE_RATE_WINDOW_DAYS;
  const requestOptions: RequestOptions = { query: [["days", String(days)]] };
  if (options.signal !== undefined) {
    requestOptions.signal = options.signal;
  }
  return await getJson<OverrideRateOut[]>(API_USAGE_OVERRIDE_RATES_ENDPOINT, requestOptions);
}
