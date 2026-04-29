/**
 * Component tests for ``RecostDialog`` (the quota-downgrade banner
 * with "Use <model> anyway" override per spec §4 + §6 + §8).
 */
import { fireEvent, render } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import RecostDialog from "../RecostDialog.svelte";

describe("RecostDialog", () => {
  it("renders 'Routing downgraded to Sonnet (overall quota at 81%)' for an Opus→Sonnet downgrade", () => {
    const { getByTestId } = render(RecostDialog, {
      props: {
        downgradedTo: "sonnet",
        originalModel: "opus",
        bucket: "overall",
        usedPct: 0.81,
        onUseAnyway: vi.fn(),
      },
    });
    const copy = getByTestId("recost-dialog-copy");
    expect(copy.textContent ?? "").toContain("Routing downgraded to Sonnet");
    expect(copy.textContent ?? "").toContain("(overall quota at 81%)");
  });

  it("renders the sonnet-bucket copy for a Sonnet→Haiku downgrade", () => {
    const { getByTestId } = render(RecostDialog, {
      props: {
        downgradedTo: "haiku",
        originalModel: "sonnet",
        bucket: "sonnet",
        usedPct: 0.83,
        onUseAnyway: vi.fn(),
      },
    });
    const copy = getByTestId("recost-dialog-copy");
    expect(copy.textContent ?? "").toContain("Routing downgraded to Haiku");
    expect(copy.textContent ?? "").toContain("(sonnet quota at 83%)");
  });

  it("renders the 'Use Opus anyway' button label when restoring Opus", () => {
    const { getByTestId } = render(RecostDialog, {
      props: {
        downgradedTo: "sonnet",
        originalModel: "opus",
        bucket: "overall",
        usedPct: 0.82,
        onUseAnyway: vi.fn(),
      },
    });
    expect(getByTestId("recost-dialog-use-anyway").textContent ?? "").toContain("Use Opus anyway");
  });

  it("fires onUseAnyway when the override button is clicked (spec §4)", async () => {
    const onUseAnyway = vi.fn();
    const { getByTestId } = render(RecostDialog, {
      props: {
        downgradedTo: "sonnet",
        originalModel: "opus",
        bucket: "overall",
        usedPct: 0.82,
        onUseAnyway,
      },
    });
    await fireEvent.click(getByTestId("recost-dialog-use-anyway"));
    expect(onUseAnyway).toHaveBeenCalledTimes(1);
  });
});
