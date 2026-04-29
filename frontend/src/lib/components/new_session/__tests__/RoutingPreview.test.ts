/**
 * Component tests for ``RoutingPreview`` — verifies each of the four
 * states (loading / manual / ready / error) renders the spec §6
 * copy.
 */
import { render } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";

import RoutingPreview from "../RoutingPreview.svelte";

describe("RoutingPreview", () => {
  it("renders the loading copy while the debounced fetch is in flight", () => {
    const { getByTestId } = render(RoutingPreview, {
      props: { state: { kind: "loading" } },
    });
    const node = getByTestId("routing-preview");
    expect(node).toHaveAttribute("data-kind", "loading");
    expect(node.textContent ?? "").toContain("Resolving routing");
  });

  it("renders 'Manual override' once the user has touched a selector (spec §6)", () => {
    const { getByTestId } = render(RoutingPreview, {
      props: { state: { kind: "manual" } },
    });
    const node = getByTestId("routing-preview");
    expect(node).toHaveAttribute("data-kind", "manual");
    expect(node.textContent ?? "").toContain("Manual override");
  });

  it("renders 'Routed from <reason>' when a fresh preview is available", () => {
    const { getByTestId } = render(RoutingPreview, {
      props: { state: { kind: "ready", reason: "Workhorse default" } },
    });
    const node = getByTestId("routing-preview");
    expect(node).toHaveAttribute("data-kind", "ready");
    expect(node.textContent ?? "").toContain("Routed from Workhorse default");
  });

  it("renders the failure copy when the last preview raised an error", () => {
    const { getByTestId } = render(RoutingPreview, {
      props: { state: { kind: "error" } },
    });
    const node = getByTestId("routing-preview");
    expect(node).toHaveAttribute("data-kind", "error");
    expect(node.textContent ?? "").toContain("Couldn't resolve routing");
  });
});
