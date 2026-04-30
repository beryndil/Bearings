/** Analytics aggregate fetched by the v1.0.0 dashboard's `/analytics`
 * page. Mirrors the `AnalyticsSummaryOut` Pydantic model on the
 * server (see `bearings.api.models.analytics`). One request renders
 * the whole page; per-card endpoints would multiply round-trips
 * without changing the freshness story. */

import { jsonFetch } from './core';

export type SessionsByDay = {
  /** ISO date 'YYYY-MM-DD'. */
  day: string;
  count: number;
};

export type TopTag = {
  id: number;
  name: string;
  color: string | null;
  session_count: number;
};

export type AnalyticsSummary = {
  total_sessions: number;
  open_sessions: number;
  closed_sessions: number;

  total_messages: number;

  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read_tokens: number;
  total_cache_creation_tokens: number;
  total_tokens: number;

  total_cost_usd: number;

  /** Always `days` entries long, zero-filled where no sessions
   * were created on a given day. */
  sessions_by_day: SessionsByDay[];

  /** Top 10 tags by session_count desc, then name asc. */
  top_tags: TopTag[];
};

/** Fetch the per-instance analytics rollup. `days` clamps the
 * sessions-by-day time series only; the headline totals are
 * all-time and ignore it. */
export function fetchAnalyticsSummary(
  days = 30,
  fetchImpl: typeof fetch = fetch
): Promise<AnalyticsSummary> {
  return jsonFetch<AnalyticsSummary>(fetchImpl, `/api/analytics/summary?days=${days}`);
}
