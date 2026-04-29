/**
 * RoutingBadge tests — verifies the per-message badge renders the
 * spec §5 label variants ("Sonnet" / "Sonnet → Opus×N" / "Opus
 * xhigh") and surfaces the routing source / reason on the data
 * attributes + tooltip the inspector + a11y consumers read.
 *
 * Per item 2.6 description: "RoutingBadge tests — badge render
 * variants (rule/manual/default/override sources)". The badge label
 * itself is model-shaped per spec §5; the source is exposed via the
 * ``data-executor-model`` / ``data-advisor-model`` data attributes
 * + the ``title`` tooltip carrying ``routingReason``.
 */
import { render } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";

import RoutingBadge from "../RoutingBadge.svelte";
import type { TurnRouting } from "../../../stores/conversation.svelte";
import {
  CONVERSATION_STRINGS,
  KNOWN_ROUTING_SOURCES,
  ROUTING_SOURCE_DEFAULT,
  ROUTING_SOURCE_MANUAL,
  ROUTING_SOURCE_MANUAL_OVERRIDE_QUOTA,
  ROUTING_SOURCE_QUOTA_DOWNGRADE,
  ROUTING_SOURCE_SYSTEM_RULE,
  ROUTING_SOURCE_TAG_RULE,
  ROUTING_SOURCE_UNKNOWN_LEGACY,
  type RoutingSource,
} from "../../../config";

function routing(overrides: Partial<TurnRouting> = {}): TurnRouting {
  return {
    executorModel: "sonnet",
    advisorModel: null,
    advisorCallsCount: 0,
    effortLevel: "medium",
    routingSource: ROUTING_SOURCE_TAG_RULE,
    routingReason: "matched bearings/architect",
    ...overrides,
  };
}

describe("RoutingBadge — spec §5 label variants", () => {
  it("renders 'Sonnet' for the no-advisor variant", () => {
    const { getByTestId } = render(RoutingBadge, {
      props: { routing: routing({ executorModel: "sonnet", advisorCallsCount: 0 }) },
    });
    const badge = getByTestId("routing-badge");
    expect(badge.textContent?.trim()).toBe("Sonnet");
  });

  it("renders 'Sonnet → Opus×2' when an advisor was consulted twice", () => {
    const { getByTestId } = render(RoutingBadge, {
      props: {
        routing: routing({
          executorModel: "sonnet",
          advisorModel: "opus",
          advisorCallsCount: 2,
        }),
      },
    });
    expect(getByTestId("routing-badge").textContent?.trim()).toBe("Sonnet → Opus×2");
  });

  it("renders 'Haiku → Opus×1' for a Haiku executor with one advisor call", () => {
    const { getByTestId } = render(RoutingBadge, {
      props: {
        routing: routing({
          executorModel: "haiku",
          advisorModel: "opus",
          advisorCallsCount: 1,
        }),
      },
    });
    expect(getByTestId("routing-badge").textContent?.trim()).toBe("Haiku → Opus×1");
  });

  it("renders 'Opus xhigh' for the Opus solo variant at xhigh effort", () => {
    const { getByTestId } = render(RoutingBadge, {
      props: {
        routing: routing({
          executorModel: "opus",
          advisorModel: null,
          advisorCallsCount: 0,
          effortLevel: "xhigh",
        }),
      },
    });
    expect(getByTestId("routing-badge").textContent?.trim()).toBe("Opus xhigh");
  });

  it("omits the effort suffix on default 'medium' / 'med' levels", () => {
    const { getByTestId } = render(RoutingBadge, {
      props: { routing: routing({ executorModel: "sonnet", effortLevel: "med" }) },
    });
    expect(getByTestId("routing-badge").textContent?.trim()).toBe("Sonnet");
  });
});

describe("RoutingBadge — source surface", () => {
  it("exposes the executor + advisor models on data attributes", () => {
    const { getByTestId } = render(RoutingBadge, {
      props: {
        routing: routing({
          executorModel: "haiku",
          advisorModel: "opus",
          advisorCallsCount: 1,
        }),
      },
    });
    const badge = getByTestId("routing-badge");
    expect(badge.getAttribute("data-executor-model")).toBe("haiku");
    expect(badge.getAttribute("data-advisor-model")).toBe("opus");
  });

  it("clears the advisor data attribute when the advisor is null", () => {
    const { getByTestId } = render(RoutingBadge, {
      props: { routing: routing({ executorModel: "sonnet", advisorModel: null }) },
    });
    expect(getByTestId("routing-badge").getAttribute("data-advisor-model")).toBe("");
  });

  it("renders the routing reason in the tooltip for the tag_rule variant", () => {
    const reason = "matched tag rule: bearings/architect — Hard architectural reasoning";
    const { getByTestId } = render(RoutingBadge, {
      props: {
        routing: routing({ routingSource: ROUTING_SOURCE_TAG_RULE, routingReason: reason }),
      },
    });
    expect(getByTestId("routing-badge").getAttribute("title")).toBe(reason);
  });

  it("renders the routing reason in the tooltip for the manual override variant", () => {
    const reason = "manual override from new-session dialog";
    const { getByTestId } = render(RoutingBadge, {
      props: {
        routing: routing({
          executorModel: "opus",
          advisorModel: null,
          advisorCallsCount: 0,
          routingSource: ROUTING_SOURCE_MANUAL,
          routingReason: reason,
        }),
      },
    });
    expect(getByTestId("routing-badge").getAttribute("title")).toBe(reason);
  });

  it("renders the routing reason in the tooltip for the default fallback variant", () => {
    const reason = "Workhorse default";
    const { getByTestId } = render(RoutingBadge, {
      props: {
        routing: routing({ routingSource: ROUTING_SOURCE_DEFAULT, routingReason: reason }),
      },
    });
    expect(getByTestId("routing-badge").getAttribute("title")).toBe(reason);
  });

  it("renders the routing reason in the tooltip for the quota_downgrade variant", () => {
    const reason = "quota guard: overall used 81% — downgraded Opus → Sonnet";
    const { getByTestId } = render(RoutingBadge, {
      props: {
        routing: routing({
          executorModel: "sonnet",
          advisorModel: null,
          advisorCallsCount: 0,
          routingSource: ROUTING_SOURCE_QUOTA_DOWNGRADE,
          routingReason: reason,
        }),
      },
    });
    expect(getByTestId("routing-badge").getAttribute("title")).toBe(reason);
  });

  it("falls back to the documented copy when the reason is empty", () => {
    const { getByTestId } = render(RoutingBadge, {
      props: { routing: routing({ routingReason: "" }) },
    });
    expect(getByTestId("routing-badge").getAttribute("title")).toBe(
      CONVERSATION_STRINGS.routingBadgeTooltipFallback,
    );
  });
});

describe("RoutingBadge — source-alphabet coverage", () => {
  // Spec §App A enumerates seven routing-source values; the badge
  // should render cleanly against every one of them since the wire
  // shape can carry any (the new-session dialog produces ``manual``
  // / ``manual_override_quota``, the rule evaluator produces
  // ``tag_rule`` / ``system_rule`` / ``default`` / ``quota_downgrade``,
  // and the legacy backfill produces ``unknown_legacy``).
  const sourceCases: ReadonlyArray<{ source: RoutingSource; reason: string }> = [
    { source: ROUTING_SOURCE_TAG_RULE, reason: "tag rule fired" },
    { source: ROUTING_SOURCE_SYSTEM_RULE, reason: "system rule fired" },
    { source: ROUTING_SOURCE_DEFAULT, reason: "Workhorse default" },
    { source: ROUTING_SOURCE_MANUAL, reason: "manual override from dialog" },
    { source: ROUTING_SOURCE_QUOTA_DOWNGRADE, reason: "quota guard downgrade" },
    {
      source: ROUTING_SOURCE_MANUAL_OVERRIDE_QUOTA,
      reason: "user reverted the quota downgrade",
    },
    { source: ROUTING_SOURCE_UNKNOWN_LEGACY, reason: "pre-v1 legacy row" },
  ];

  it("covers every value in KNOWN_ROUTING_SOURCES", () => {
    const covered = sourceCases.map((c) => c.source);
    expect([...covered].sort()).toEqual([...KNOWN_ROUTING_SOURCES].sort());
  });

  for (const { source, reason } of sourceCases) {
    it(`renders the badge for routingSource='${source}' with the reason in the tooltip`, () => {
      const { getByTestId } = render(RoutingBadge, {
        props: { routing: routing({ routingSource: source, routingReason: reason }) },
      });
      const badge = getByTestId("routing-badge");
      expect(badge.textContent?.trim()).not.toBe("");
      expect(badge.getAttribute("title")).toBe(reason);
    });
  }
});
