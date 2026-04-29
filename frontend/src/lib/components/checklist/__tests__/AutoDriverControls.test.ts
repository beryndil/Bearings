/**
 * Component tests for :class:`AutoDriverControls`.
 *
 * Done-when criteria covered:
 *
 * - Start / Stop / Pause / Resume / Skip buttons fire the right
 *   run-control helper for the matching state.
 * - Failure-policy + visit-existing toggles flow into the start call.
 * - Status line formatting (the pure :func:`formatStatusLine`) covers
 *   idle / running / paused / outcome-frozen.
 */
import { fireEvent, render, waitFor } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import AutoDriverControls, {
  currentItemIndex,
  formatStatusLine,
} from "../AutoDriverControls.svelte";
import type { AutoDriverRunOut } from "../../../api/checklists";

function fakeRun(overrides: Partial<AutoDriverRunOut> = {}): AutoDriverRunOut {
  return {
    id: 1,
    checklist_id: "cl_a",
    state: "running",
    failure_policy: "halt",
    visit_existing: false,
    items_completed: 0,
    items_failed: 0,
    items_blocked: 0,
    items_skipped: 0,
    items_attempted: 0,
    legs_spawned: 0,
    current_item_id: null,
    outcome: null,
    outcome_reason: null,
    started_at: "2026-04-29T00:00:00Z",
    updated_at: "2026-04-29T00:00:00Z",
    finished_at: null,
    ...overrides,
  };
}

describe("formatStatusLine (helper)", () => {
  it("returns the idle copy when no run row is present", () => {
    const line = formatStatusLine(null, 5, 0);
    expect(line).toContain("Idle");
  });

  it("substitutes counters into the running template", () => {
    const run = fakeRun({
      state: "running",
      items_completed: 1,
      items_failed: 0,
      legs_spawned: 2,
      current_item_id: 7,
    });
    const line = formatStatusLine(run, 12, 3);
    expect(line).toBe("Running — item 3 of 12, leg 2, 0 failures");
  });

  it("renders the outcome string when the run is finished", () => {
    const run = fakeRun({
      state: "finished",
      items_completed: 5,
      items_failed: 1,
      outcome: "Halted: failure on item 3",
    });
    const line = formatStatusLine(run, 5, 0);
    expect(line).toContain("Halted: failure on item 3");
    expect(line).toContain("5/5");
  });
});

describe("currentItemIndex (helper)", () => {
  it("returns 0 when there is no current item", () => {
    expect(currentItemIndex(null, [1, 2, 3])).toBe(0);
  });
  it("returns the 1-based index of the current item id", () => {
    const run = fakeRun({ current_item_id: 2 });
    expect(currentItemIndex(run, [1, 2, 3])).toBe(2);
  });
});

describe("AutoDriverControls — buttons", () => {
  it("renders the Start button when no run is active and fires startRun on click", async () => {
    const startRun = vi.fn().mockResolvedValue(fakeRun());
    const { getByTestId, queryByTestId } = render(AutoDriverControls, {
      props: {
        checklistId: "cl_a",
        activeRun: null,
        totalItems: 3,
        sortedItemIds: [1, 2, 3],
        startRun,
      },
    });
    expect(getByTestId("auto-driver-start")).toBeInTheDocument();
    expect(queryByTestId("auto-driver-stop")).toBeNull();
    await fireEvent.click(getByTestId("auto-driver-start"));
    await waitFor(() =>
      expect(startRun).toHaveBeenCalledWith("cl_a", {
        failure_policy: "halt",
        visit_existing: false,
      }),
    );
  });

  it("passes the failure_policy + visit_existing toggles into Start", async () => {
    const startRun = vi.fn().mockResolvedValue(fakeRun());
    const { getByTestId } = render(AutoDriverControls, {
      props: {
        checklistId: "cl_a",
        activeRun: null,
        totalItems: 3,
        sortedItemIds: [1, 2, 3],
        startRun,
      },
    });
    const policy = getByTestId("auto-driver-failure-policy") as HTMLSelectElement;
    await fireEvent.change(policy, { target: { value: "skip" } });
    const visit = getByTestId("auto-driver-visit-existing") as HTMLInputElement;
    await fireEvent.click(visit);
    await fireEvent.click(getByTestId("auto-driver-start"));
    await waitFor(() =>
      expect(startRun).toHaveBeenCalledWith("cl_a", {
        failure_policy: "skip",
        visit_existing: true,
      }),
    );
  });

  it("renders Stop / Pause / Skip buttons when state is running", async () => {
    const stopRun = vi.fn().mockResolvedValue(fakeRun({ state: "paused" }));
    const skipRun = vi.fn().mockResolvedValue(fakeRun({ state: "running" }));
    const { getByTestId } = render(AutoDriverControls, {
      props: {
        checklistId: "cl_a",
        activeRun: fakeRun({ state: "running" }),
        totalItems: 3,
        sortedItemIds: [1, 2, 3],
        stopRun,
        skipRun,
      },
    });
    expect(getByTestId("auto-driver-stop")).toBeInTheDocument();
    expect(getByTestId("auto-driver-pause")).toBeInTheDocument();
    expect(getByTestId("auto-driver-skip")).toBeInTheDocument();
    await fireEvent.click(getByTestId("auto-driver-stop"));
    await waitFor(() => expect(stopRun).toHaveBeenCalledWith("cl_a"));
    await fireEvent.click(getByTestId("auto-driver-skip"));
    await waitFor(() => expect(skipRun).toHaveBeenCalledWith("cl_a"));
  });

  it("renders Resume button when state is paused", async () => {
    const resumeRun = vi.fn().mockResolvedValue(fakeRun({ state: "running" }));
    const { getByTestId, queryByTestId } = render(AutoDriverControls, {
      props: {
        checklistId: "cl_a",
        activeRun: fakeRun({ state: "paused" }),
        totalItems: 3,
        sortedItemIds: [1, 2, 3],
        resumeRun,
      },
    });
    expect(getByTestId("auto-driver-resume")).toBeInTheDocument();
    expect(queryByTestId("auto-driver-stop")).toBeNull();
    await fireEvent.click(getByTestId("auto-driver-resume"));
    await waitFor(() => expect(resumeRun).toHaveBeenCalledWith("cl_a"));
  });

  it("status line ticks the running template with current index", () => {
    const run = fakeRun({
      state: "running",
      legs_spawned: 4,
      items_failed: 1,
      current_item_id: 2,
    });
    const { getByTestId } = render(AutoDriverControls, {
      props: {
        checklistId: "cl_a",
        activeRun: run,
        totalItems: 5,
        sortedItemIds: [1, 2, 3, 4, 5],
      },
    });
    expect(getByTestId("auto-driver-status")).toHaveTextContent(
      "Running — item 2 of 5, leg 4, 1 failures",
    );
  });
});
