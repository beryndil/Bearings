/**
 * Typed clients for the tag-rule + system-rule CRUD surfaces (spec §9).
 *
 * Backend route module: :mod:`bearings.web.routes.routing` (item 1.8).
 * Pydantic shapes: :class:`bearings.web.models.routing.RoutingRuleIn` /
 * ``RoutingRuleOut`` / ``SystemRoutingRuleIn`` / ``SystemRoutingRuleOut``
 * / ``RoutingReorderIn`` (``src/bearings/web/models/routing.py``).
 *
 * Consumers:
 *
 * * :class:`RoutingRuleEditor` (item 2.8) — list / create / patch /
 *   delete / reorder + per-rule duplicate.
 * * :class:`RuleRow` reads the typed shape; the editor owns the
 *   side-effects.
 * * :class:`TestAgainstMessageDialog` evaluates a single rule
 *   client-side via :func:`evaluateRuleMatch` (no API call — spec §10
 *   "deterministic dialog — no LLM call").
 *
 * Decided-and-documented surface differences vs spec §9:
 *
 * * Tag-rule reorder uses the documented endpoint
 *   ``PATCH /api/tags/{id}/routing/reorder``.
 * * System rules have no documented reorder endpoint; the editor
 *   re-stamps priorities by issuing per-rule PATCHes
 *   (:func:`reorderSystemRules` below) — see the editor docstring for
 *   the rationale.
 */
import {
  ROUTING_MATCH_TYPE_ALWAYS,
  ROUTING_MATCH_TYPE_KEYWORD,
  ROUTING_MATCH_TYPE_LENGTH_GT,
  ROUTING_MATCH_TYPE_LENGTH_LT,
  ROUTING_MATCH_TYPE_REGEX,
  type RoutingMatchType,
  API_SYSTEM_ROUTING_RULES_ENDPOINT,
  systemRoutingRuleEndpoint,
  tagRoutingReorderEndpoint,
  tagRoutingRuleEndpoint,
  tagRoutingRulesEndpoint,
} from "../config";
import { deleteResource, getJson, patchJson, postJson, type RequestOptions } from "./client";

/**
 * Tag-rule shape. Mirrors :class:`bearings.db.routing.RoutingRule` /
 * :class:`bearings.web.models.routing.RoutingRuleOut` per spec §3
 * schema + spec §App A field reference.
 */
export interface RoutingRuleOut {
  id: number;
  tag_id: number;
  priority: number;
  enabled: boolean;
  match_type: string;
  match_value: string | null;
  executor_model: string;
  advisor_model: string | null;
  advisor_max_uses: number;
  effort_level: string;
  reason: string;
  created_at: number;
  updated_at: number;
}

/**
 * System-rule shape. Mirrors
 * :class:`bearings.db.routing.SystemRoutingRule` /
 * :class:`bearings.web.models.routing.SystemRoutingRuleOut`. The
 * ``seeded`` boolean is ``true`` for shipped defaults (priority
 * 10/20/30/40/50/60/1000 per spec §3 seeded table) and ``false`` for
 * user-added rules — the editor renders a small badge when
 * ``seeded`` so the user knows disabling is preferred over deletion.
 */
export interface SystemRoutingRuleOut {
  id: number;
  priority: number;
  enabled: boolean;
  match_type: string;
  match_value: string | null;
  executor_model: string;
  advisor_model: string | null;
  advisor_max_uses: number;
  effort_level: string;
  reason: string;
  seeded: boolean;
  created_at: number;
  updated_at: number;
}

/**
 * Request body shared by the tag-rule + system-rule create/patch
 * endpoints. Mirrors :class:`RoutingRuleIn` /
 * :class:`SystemRoutingRuleIn` — both Pydantic shapes have the same
 * mutable fields, so one TS interface covers both wire surfaces.
 */
export interface RoutingRuleIn {
  priority: number;
  enabled: boolean;
  match_type: string;
  match_value: string | null;
  executor_model: string;
  advisor_model: string | null;
  advisor_max_uses: number;
  effort_level: string;
  reason: string;
}

// ---- Tag rules -----------------------------------------------------------

export async function listTagRules(
  tagId: number,
  options: RequestOptions = {},
): Promise<RoutingRuleOut[]> {
  return await getJson<RoutingRuleOut[]>(tagRoutingRulesEndpoint(tagId), options);
}

export async function createTagRule(
  tagId: number,
  body: RoutingRuleIn,
  options: RequestOptions = {},
): Promise<RoutingRuleOut> {
  return await postJson<RoutingRuleOut>(tagRoutingRulesEndpoint(tagId), body, options);
}

export async function updateTagRule(
  ruleId: number,
  body: RoutingRuleIn,
  options: RequestOptions = {},
): Promise<RoutingRuleOut> {
  return await patchJson<RoutingRuleOut>(tagRoutingRuleEndpoint(ruleId), body, options);
}

export async function deleteTagRule(ruleId: number, options: RequestOptions = {}): Promise<void> {
  await deleteResource<void>(tagRoutingRuleEndpoint(ruleId), options);
}

/**
 * Re-stamp tag-rule priorities to match the supplied id order
 * (spec §9 ``PATCH /api/tags/{id}/routing/reorder``).
 *
 * The backend handler re-issues priorities at sparse stride to keep
 * the original ordering intent (item 1.8); the response is the
 * re-stamped rule list in the new priority order.
 */
export async function reorderTagRules(
  tagId: number,
  idsInPriorityOrder: number[],
  options: RequestOptions = {},
): Promise<RoutingRuleOut[]> {
  return await patchJson<RoutingRuleOut[]>(
    tagRoutingReorderEndpoint(tagId),
    { ids_in_priority_order: idsInPriorityOrder },
    options,
  );
}

// ---- System rules --------------------------------------------------------

export async function listSystemRules(
  options: RequestOptions = {},
): Promise<SystemRoutingRuleOut[]> {
  return await getJson<SystemRoutingRuleOut[]>(API_SYSTEM_ROUTING_RULES_ENDPOINT, options);
}

export async function createSystemRule(
  body: RoutingRuleIn,
  options: RequestOptions = {},
): Promise<SystemRoutingRuleOut> {
  return await postJson<SystemRoutingRuleOut>(API_SYSTEM_ROUTING_RULES_ENDPOINT, body, options);
}

export async function updateSystemRule(
  ruleId: number,
  body: RoutingRuleIn,
  options: RequestOptions = {},
): Promise<SystemRoutingRuleOut> {
  return await patchJson<SystemRoutingRuleOut>(systemRoutingRuleEndpoint(ruleId), body, options);
}

export async function deleteSystemRule(
  ruleId: number,
  options: RequestOptions = {},
): Promise<void> {
  await deleteResource<void>(systemRoutingRuleEndpoint(ruleId), options);
}

// ---- Helpers: derive ``RoutingRuleIn`` from a row -----------------------

/**
 * Project a tag-rule row onto the request shape — used by the editor
 * when toggling ``enabled`` or duplicating a rule. Keeps the wire
 * shape internal to this module so the component doesn't have to
 * remember which ``Out`` columns are mutable.
 */
export function tagRuleToInput(row: RoutingRuleOut): RoutingRuleIn {
  return {
    priority: row.priority,
    enabled: row.enabled,
    match_type: row.match_type,
    match_value: row.match_value,
    executor_model: row.executor_model,
    advisor_model: row.advisor_model,
    advisor_max_uses: row.advisor_max_uses,
    effort_level: row.effort_level,
    reason: row.reason,
  };
}

export function systemRuleToInput(row: SystemRoutingRuleOut): RoutingRuleIn {
  return {
    priority: row.priority,
    enabled: row.enabled,
    match_type: row.match_type,
    match_value: row.match_value,
    executor_model: row.executor_model,
    advisor_model: row.advisor_model,
    advisor_max_uses: row.advisor_max_uses,
    effort_level: row.effort_level,
    reason: row.reason,
  };
}

// ---- Pure rule evaluation (deterministic test dialog) -------------------

/**
 * Outcome of testing a single rule against a candidate message.
 *
 * The :class:`TestAgainstMessageDialog` (item 2.8) renders this verbatim
 * — no LLM call, no API call. Spec §10: "deterministic dialog — it
 * evaluates the rule's match condition against pasted text and shows
 * the resulting routing decision. No LLM call. Test inputs are not
 * stored."
 */
export interface RuleEvaluationResult {
  /** ``true`` when the rule's match clause holds for the candidate text. */
  matched: boolean;
  /**
   * ``true`` when ``match_type === 'regex'`` and the supplied
   * ``match_value`` is not a parseable JS regex. Spec §3: "Invalid
   * regexes disable the rule and surface an error in the editor."
   */
  invalidRegex: boolean;
}

/**
 * Test whether ``message`` would trigger a rule with the given
 * ``match_type`` + ``match_value``. Mirrors the backend semantics in
 * :func:`bearings.agent.routing._matches` (item 1.8) so the dialog's
 * verdict agrees with the live evaluator.
 *
 * Match semantics per spec §3:
 *
 * * ``keyword`` — case-insensitive substring; ``match_value`` is a
 *   comma-separated list; any one match triggers the rule.
 * * ``regex`` — case-insensitive regex. JS's ``RegExp`` engine differs
 *   from Python ``re`` on a few exotic constructs, but the simple
 *   character-class / alternation / anchor patterns the editor is
 *   meant to support evaluate identically. The function reports
 *   ``invalidRegex = true`` when the pattern fails to parse so the UI
 *   can surface the spec-mandated error.
 * * ``length_gt`` / ``length_lt`` — character-length comparison with
 *   ``parseInt(match_value)``; non-numeric values fail closed (no
 *   match) per the spec's "fail safe" wording.
 * * ``always`` — unconditional.
 *
 * Empty / null ``match_value`` is treated as a non-match for every
 * type except ``always`` (which ignores the value entirely).
 */
export function evaluateRuleMatch(
  matchType: RoutingMatchType,
  matchValue: string | null,
  message: string,
): RuleEvaluationResult {
  switch (matchType) {
    case ROUTING_MATCH_TYPE_ALWAYS:
      return { matched: true, invalidRegex: false };
    case ROUTING_MATCH_TYPE_KEYWORD: {
      if (matchValue === null || matchValue.trim() === "") {
        return { matched: false, invalidRegex: false };
      }
      const haystack = message.toLowerCase();
      const needles = matchValue
        .split(",")
        .map((part) => part.trim().toLowerCase())
        .filter((part) => part.length > 0);
      const matched = needles.some((needle) => haystack.includes(needle));
      return { matched, invalidRegex: false };
    }
    case ROUTING_MATCH_TYPE_REGEX: {
      if (matchValue === null || matchValue === "") {
        return { matched: false, invalidRegex: false };
      }
      let pattern: RegExp;
      try {
        pattern = new RegExp(matchValue, "i");
      } catch {
        return { matched: false, invalidRegex: true };
      }
      return { matched: pattern.test(message), invalidRegex: false };
    }
    case ROUTING_MATCH_TYPE_LENGTH_GT: {
      const threshold = parseLengthThreshold(matchValue);
      if (threshold === null) {
        return { matched: false, invalidRegex: false };
      }
      return { matched: message.length > threshold, invalidRegex: false };
    }
    case ROUTING_MATCH_TYPE_LENGTH_LT: {
      const threshold = parseLengthThreshold(matchValue);
      if (threshold === null) {
        return { matched: false, invalidRegex: false };
      }
      return { matched: message.length < threshold, invalidRegex: false };
    }
  }
}

function parseLengthThreshold(matchValue: string | null): number | null {
  if (matchValue === null) {
    return null;
  }
  const trimmed = matchValue.trim();
  if (trimmed === "" || !/^-?\d+$/.test(trimmed)) {
    return null;
  }
  const parsed = Number.parseInt(trimmed, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Cheap pre-check for the rule editor's row-level "invalid regex"
 * warning. Mirrors the regex branch of :func:`evaluateRuleMatch`
 * without running the match — exposed so :class:`RuleRow` can light
 * the warning the moment the user types an invalid pattern, before
 * any test-dialog is opened.
 */
export function isValidRegex(matchValue: string): boolean {
  try {
    new RegExp(matchValue, "i");
    return true;
  } catch {
    return false;
  }
}
