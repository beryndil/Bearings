/**
 * Tests for the seamless-reload watcher. We exercise the public state
 * transitions (`pollOnce`, `attemptReload`) directly so we don't have
 * to wait out the 60-s poll interval; production paths fire from the
 * timer + visibility handler set up in `init()`.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VersionWatcher } from "./version_watcher.svelte";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function stubVersionFetch(build: string | null): () => void {
  const calls: number[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      calls.push(Date.now());
      return {
        ok: true,
        async json() {
          return { version: "0.10.0", build };
        },
      } as unknown as Response;
    }),
  );
  return () => calls.length as unknown as () => void;
}

describe("VersionWatcher.wantsReload", () => {
  it("returns false until both pin and server build are known", () => {
    const w = new VersionWatcher();
    expect(w.wantsReload).toBe(false);
    w.myBuild = "abc";
    expect(w.wantsReload).toBe(false);
    w.serverBuild = "abc";
    expect(w.wantsReload).toBe(false);
  });

  it("returns true when myBuild and serverBuild diverge", () => {
    const w = new VersionWatcher();
    w.myBuild = "old";
    w.serverBuild = "new";
    expect(w.wantsReload).toBe(true);
  });

  it("returns false when either side is null (dev mode)", () => {
    const w = new VersionWatcher();
    w.myBuild = null;
    w.serverBuild = "something";
    expect(w.wantsReload).toBe(false);

    w.myBuild = "something";
    w.serverBuild = null;
    expect(w.wantsReload).toBe(false);
  });
});

describe("VersionWatcher.pollOnce", () => {
  it("updates serverBuild on a successful fetch", async () => {
    stubVersionFetch("newbuild");
    const w = new VersionWatcher();
    w.myBuild = "oldbuild";
    w.serverBuild = "oldbuild";
    await w.pollOnce();
    expect(w.serverBuild).toBe("newbuild");
    expect(w.wantsReload).toBe(true);
  });

  it("preserves the last known serverBuild when the fetch throws", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("transport blip");
      }),
    );
    const w = new VersionWatcher();
    w.myBuild = "oldbuild";
    w.serverBuild = "oldbuild";
    await w.pollOnce();
    expect(w.serverBuild).toBe("oldbuild");
    expect(w.wantsReload).toBe(false);
  });
});

describe("VersionWatcher.attemptReload disruption guards", () => {
  it("triggers reload when armed and no guard blocks", () => {
    const w = new VersionWatcher();
    w.myBuild = "old";
    w.serverBuild = "new";
    const reload = vi.fn();
    expect(w.attemptReload(reload)).toBe(true);
    expect(reload).toHaveBeenCalledOnce();
  });

  it("does nothing when not armed", () => {
    const w = new VersionWatcher();
    w.myBuild = "same";
    w.serverBuild = "same";
    const reload = vi.fn();
    expect(w.attemptReload(reload)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  it("blocks while the agent is streaming", () => {
    const w = new VersionWatcher();
    w.configure({ isAgentStreaming: () => true });
    w.myBuild = "old";
    w.serverBuild = "new";
    const reload = vi.fn();
    expect(w.attemptReload(reload)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  it("blocks while a modal is open", () => {
    const w = new VersionWatcher();
    w.configure({ isModalOpen: () => true });
    w.myBuild = "old";
    w.serverBuild = "new";
    const reload = vi.fn();
    expect(w.attemptReload(reload)).toBe(false);
  });

  it("blocks while the composer holds a draft", () => {
    const w = new VersionWatcher();
    w.configure({ hasComposerDraft: () => true });
    w.myBuild = "old";
    w.serverBuild = "new";
    const reload = vi.fn();
    expect(w.attemptReload(reload)).toBe(false);
  });
});

/**
 * The visible-tab idle sweep is the path that catches "user keeps
 * Bearings foreground all day, never tab-switches." It runs on a
 * timer, requires the bundle to actually have changed, and waits for
 * a brief interactivity debounce so an in-flight click stream isn't
 * yanked out from under the user. These tests exercise the timer
 * path end-to-end via `vi.useFakeTimers()`.
 */
describe("VersionWatcher idle sweep", () => {
  function withVisibility(state: "visible" | "hidden", body: () => void): void {
    const original = Object.getOwnPropertyDescriptor(
      Document.prototype,
      "visibilityState",
    );
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => state,
    });
    try {
      body();
    } finally {
      if (original) {
        Object.defineProperty(Document.prototype, "visibilityState", original);
      }
    }
  }

  it("reloads after a brief debounce when the bundle changes and the tab is idle", async () => {
    const reload = vi.fn();
    const w = new VersionWatcher();
    // Stub the public reload hatch so the production timer path is
    // observable without actually reloading the test runner.
    const origAttempt = w.attemptReload.bind(w);
    w.attemptReload = (impl) => origAttempt(impl ?? reload);
    stubVersionFetch("newbuild");
    await w.init(); // pins myBuild, starts timers
    w.myBuild = "oldbuild"; // simulate a build mismatch arriving
    await w.pollOnce(); // serverBuild = 'newbuild' → wantsReload true

    withVisibility("visible", () => {
      // 4 s isn't long enough — debounce is 5 s.
      vi.advanceTimersByTime(4_000);
      expect(reload).not.toHaveBeenCalled();
      // Cross the threshold; the next 1 Hz sweep tick should fire.
      vi.advanceTimersByTime(2_000);
      expect(reload).toHaveBeenCalledTimes(1);
    });

    w.dispose();
  });

  it("does not reload while the user is actively interacting", async () => {
    const reload = vi.fn();
    const w = new VersionWatcher();
    const origAttempt = w.attemptReload.bind(w);
    w.attemptReload = (impl) => origAttempt(impl ?? reload);
    stubVersionFetch("newbuild");
    await w.init();
    w.myBuild = "oldbuild";
    await w.pollOnce();

    withVisibility("visible", () => {
      // Simulate a user actively typing — markActivity every second
      // for 30 s. The debounce should never elapse.
      for (let t = 0; t < 30; t++) {
        vi.advanceTimersByTime(1_000);
        w.markActivity();
      }
      expect(reload).not.toHaveBeenCalled();

      // Now the user pauses. After IDLE_DEBOUNCE_MS the sweep fires.
      vi.advanceTimersByTime(6_000);
      expect(reload).toHaveBeenCalledTimes(1);
    });

    w.dispose();
  });

  it("does not fire while the tab is hidden — the visibility branch owns that path", async () => {
    const reload = vi.fn();
    const w = new VersionWatcher();
    const origAttempt = w.attemptReload.bind(w);
    w.attemptReload = (impl) => origAttempt(impl ?? reload);
    stubVersionFetch("newbuild");
    await w.init();
    w.myBuild = "oldbuild";
    await w.pollOnce();

    withVisibility("hidden", () => {
      vi.advanceTimersByTime(60_000);
      expect(reload).not.toHaveBeenCalled();
    });

    w.dispose();
  });
});
