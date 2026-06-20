/**
 * Regression test for the N-14 auto-reload baseline bug.
 *
 * The watcher must reload when a LATER poll reports a bundle mtime greater
 * than the mtime the page LOADED with (captured from the first poll) — not
 * compared against the browser wall-clock (`Date.now()`), which created a
 * dead zone where a genuinely newer bundle never triggered a reload and the
 * user had to hard-refresh.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/client", () => ({ getJson: vi.fn() }));

import { getJson } from "../../api/client";
import { API_VERSION_ENDPOINT } from "../../config";
import { _checkBundleMtimeForTests, _resetVersionWatcherForTests } from "../versionWatcher.svelte";

const mockGetJson = vi.mocked(getJson);

/** Route the /api/version mock to a given bundle mtime. */
function bundleMtime(mtime: number): void {
  mockGetJson.mockImplementation((endpoint: string) => {
    if (endpoint === API_VERSION_ENDPOINT) {
      return Promise.resolve({ bundle_mtime: mtime } as never);
    }
    return Promise.resolve({ version: "1.4.0" } as never);
  });
}

describe("versionWatcher — auto-reload baseline (N-14 regression)", () => {
  let reload: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    _resetVersionWatcherForTests();
    vi.useFakeTimers();
    reload = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { reload },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("reloads when a later poll reports a bundle newer than the loaded baseline", async () => {
    bundleMtime(1000); // first poll → baseline, no reload
    await _checkBundleMtimeForTests();
    expect(reload).not.toHaveBeenCalled();

    bundleMtime(2000); // newer bundle shipped
    await _checkBundleMtimeForTests();
    await vi.advanceTimersByTimeAsync(600); // flush the 500ms reload debounce
    expect(reload).toHaveBeenCalledOnce();
  });

  it("does NOT reload while the bundle mtime is unchanged", async () => {
    bundleMtime(1000);
    await _checkBundleMtimeForTests(); // baseline
    await _checkBundleMtimeForTests(); // same mtime
    await vi.advanceTimersByTimeAsync(600);
    expect(reload).not.toHaveBeenCalled();
  });

  it("uses the first poll as the baseline, not the client clock (the bug)", async () => {
    // A bundle mtime far BELOW Date.now()/1000 (seconds) must still NOT
    // reload on its own — proving the comparison is server-mtime vs the
    // loaded server-mtime, not against the browser wall-clock.
    bundleMtime(1000);
    await _checkBundleMtimeForTests(); // baseline = 1000
    await _checkBundleMtimeForTests(); // still 1000
    await vi.advanceTimersByTimeAsync(600);
    expect(reload).not.toHaveBeenCalled();
  });
});
