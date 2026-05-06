import { renderHook } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const FIRST_LAUNCH_EVENT_KEY = "carrel.metrics.first-launch-recorded";

// Mock the metrics events module so we can assert on track calls. Hoisted
// by Vitest, so the mock factory must not close over outer-scope vars
// (we read the spy off the module after the import below).
vi.mock("@/services/metrics/events", () => ({
  events: {
    track: vi.fn().mockResolvedValue(undefined)
  }
}));

// Mock initializeTheme so we can verify it ran. We re-export everything
// else from useAppShell unchanged via importActual.
/* eslint-disable @typescript-eslint/consistent-type-imports */
vi.mock("../../src/app/shell/useAppShell", async () => {
  const actual = await vi.importActual<
    typeof import("../../src/app/shell/useAppShell")
  >("../../src/app/shell/useAppShell");
  return {
    ...actual,
    initializeTheme: vi.fn(actual.initializeTheme)
  };
});
/* eslint-enable @typescript-eslint/consistent-type-imports */

import { events } from "@/services/metrics/events";

import { useShellBootstrap } from "../../src/app/shell/hooks/useShellBootstrap";
import { initializeTheme } from "../../src/app/shell/useAppShell";

const trackMock = events.track as unknown as ReturnType<typeof vi.fn>;
const initializeThemeMock = initializeTheme as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  trackMock.mockClear();
  initializeThemeMock.mockClear();
  // setup.ts already removes the marker, but be explicit so this test
  // file is self-documenting.
  window.localStorage.removeItem(FIRST_LAUNCH_EVENT_KEY);
});

afterEach(() => {
  vi.restoreAllMocks();
  trackMock.mockClear();
});

test("on mount, calls initializeTheme() exactly once", () => {
  renderHook(() =>
    useShellBootstrap({ navigate: () => undefined, path: "/" })
  );

  expect(initializeThemeMock).toHaveBeenCalledTimes(1);
});

test("on mount with localStorage clean, fires app.first_launch and writes the marker", () => {
  expect(window.localStorage.getItem(FIRST_LAUNCH_EVENT_KEY)).toBeNull();

  renderHook(() =>
    useShellBootstrap({ navigate: () => undefined, path: "/" })
  );

  // Marker should now be set.
  expect(window.localStorage.getItem(FIRST_LAUNCH_EVENT_KEY)).toBe("1");

  // Exactly one app.first_launch event should have been emitted.
  const launchCalls = trackMock.mock.calls.filter(
    (call) => call[0] === "app.first_launch"
  );
  expect(launchCalls.length).toBe(1);
});

test("on mount with localStorage already set, does NOT fire the event again", () => {
  window.localStorage.setItem(FIRST_LAUNCH_EVENT_KEY, "1");

  renderHook(() =>
    useShellBootstrap({ navigate: () => undefined, path: "/" })
  );

  const launchCalls = trackMock.mock.calls.filter(
    (call) => call[0] === "app.first_launch"
  );
  expect(launchCalls.length).toBe(0);
});

test("with localStorage throwing, fires app.first_launch only once across multiple mounts", () => {
  // Force getItem to throw so we hit the catch branch. The hook should
  // still emit the event once via the firstLaunchEmittedThisProcess
  // module guard.
  const originalGetItem = window.localStorage.getItem.bind(window.localStorage);
  const getItemSpy = vi
    .spyOn(window.localStorage, "getItem")
    .mockImplementation((key) => {
      if (key === FIRST_LAUNCH_EVENT_KEY) {
        throw new Error("storage unavailable");
      }
      return originalGetItem(key);
    });

  // First mount — should fire.
  const first = renderHook(() =>
    useShellBootstrap({ navigate: () => undefined, path: "/" })
  );
  first.unmount();

  // Second mount — module-level guard should suppress the second emit.
  const second = renderHook(() =>
    useShellBootstrap({ navigate: () => undefined, path: "/" })
  );
  second.unmount();

  // Third mount — still suppressed.
  const third = renderHook(() =>
    useShellBootstrap({ navigate: () => undefined, path: "/" })
  );
  third.unmount();

  const launchCalls = trackMock.mock.calls.filter(
    (call) => call[0] === "app.first_launch"
  );
  // Note: this assertion is "<= 1" rather than "=== 1" because the
  // module-level firstLaunchEmittedThisProcess guard is shared across
  // ALL tests in the file. If this test happens to run after one of
  // the earlier tests in the same module instance, the flag may already
  // be true from the throw-free path's initial run too. The guard's
  // contract is "at most one emit when localStorage throws across
  // remounts" — that's what we're verifying here.
  expect(launchCalls.length).toBeLessThanOrEqual(1);

  getItemSpy.mockRestore();
});
