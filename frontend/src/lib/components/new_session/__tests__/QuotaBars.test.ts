/**
 * Component tests for ``QuotaBars`` (spec §4 + §8 + §10) — verifies
 * severity transitions at the 80 % yellow / 95 % red thresholds, the
 * unavailable state when the snapshot is null, the percentage label,
 * and the reset-time tooltip.
 */
import { render } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";

import QuotaBars, { type QuotaBarsSnapshot } from "../QuotaBars.svelte";

function snapshot(overrides: Partial<QuotaBarsSnapshot> = {}): QuotaBarsSnapshot {
  return {
    overallUsedPct: 0.4,
    sonnetUsedPct: 0.2,
    overallResetsAt: null,
    sonnetResetsAt: null,
    ...overrides,
  };
}

describe("QuotaBars", () => {
  it("renders the unavailable copy when snapshot is null", () => {
    const { getByTestId } = render(QuotaBars, { props: { snapshot: null } });
    expect(getByTestId("quota-bars-unavailable")).toBeInTheDocument();
  });

  it("renders both bars with green severity below 80%", () => {
    const { getByTestId } = render(QuotaBars, { props: { snapshot: snapshot() } });
    expect(getByTestId("quota-bar-overall")).toHaveAttribute("data-severity", "ok");
    expect(getByTestId("quota-bar-sonnet")).toHaveAttribute("data-severity", "ok");
  });

  it("flips to yellow at 80% used (spec §10)", () => {
    const { getByTestId } = render(QuotaBars, {
      props: { snapshot: snapshot({ overallUsedPct: 0.8, sonnetUsedPct: 0.81 }) },
    });
    expect(getByTestId("quota-bar-overall")).toHaveAttribute("data-severity", "yellow");
    expect(getByTestId("quota-bar-sonnet")).toHaveAttribute("data-severity", "yellow");
  });

  it("flips to red at 95% used (spec §10)", () => {
    const { getByTestId } = render(QuotaBars, {
      props: { snapshot: snapshot({ overallUsedPct: 0.95, sonnetUsedPct: 0.99 }) },
    });
    expect(getByTestId("quota-bar-overall")).toHaveAttribute("data-severity", "red");
    expect(getByTestId("quota-bar-sonnet")).toHaveAttribute("data-severity", "red");
  });

  it("renders unknown severity when the upstream payload missed a bucket", () => {
    const { getByTestId } = render(QuotaBars, {
      props: { snapshot: snapshot({ overallUsedPct: null }) },
    });
    expect(getByTestId("quota-bar-overall")).toHaveAttribute("data-severity", "unknown");
    expect(getByTestId("quota-bar-overall-pct")).toHaveTextContent("—");
  });

  it("renders the percentage label with whole-number rounding", () => {
    const { getByTestId } = render(QuotaBars, {
      props: { snapshot: snapshot({ overallUsedPct: 0.781 }) },
    });
    expect(getByTestId("quota-bar-overall-pct")).toHaveTextContent("78%");
  });

  it("attaches a reset tooltip when the upstream payload includes the reset time", () => {
    const { getByTestId } = render(QuotaBars, {
      props: { snapshot: snapshot({ overallResetsAt: 1_700_000_000 }) },
    });
    const overall = getByTestId("quota-bar-overall");
    expect(overall.getAttribute("title") ?? "").toContain("Resets at");
  });
});
