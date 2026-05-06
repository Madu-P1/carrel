import { renderHook } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

// Mock reader state action helpers so we can spy on them. We re-export
// the readerState signal bag unchanged so the route-gate logic in
// useShellMenuCommands can still read focusAvailable.value.
/* eslint-disable @typescript-eslint/consistent-type-imports */
vi.mock("@/features/reader/state", async () => {
  const actual = await vi.importActual<
    typeof import("@/features/reader/state")
  >("@/features/reader/state");
  return {
    ...actual,
    requestReaderFind: vi.fn(),
    requestReaderPage: vi.fn(),
    setReaderFocusMode: vi.fn(),
    setReaderScale: vi.fn(),
    zoomReaderBy: vi.fn()
  };
});

// Mock navigateTo so we can verify command -> route mapping without
// touching the real router or window.history. Keep the rest of the
// useAppShell exports actual so currentRoute, pathnameFromRoute, etc.
// still behave normally.
vi.mock("../../src/app/shell/useAppShell", async () => {
  const actual = await vi.importActual<
    typeof import("../../src/app/shell/useAppShell")
  >("../../src/app/shell/useAppShell");
  return {
    ...actual,
    navigateTo: vi.fn()
  };
});
/* eslint-enable @typescript-eslint/consistent-type-imports */

import {
  readerState,
  requestReaderFind,
  setReaderFocusMode,
  zoomReaderBy
} from "@/features/reader/state";
import { dispatchMenuCommand } from "@/services/native/menu";

import { useShellMenuCommands } from "../../src/app/shell/hooks/useShellMenuCommands";
import { appShell, navigateTo } from "../../src/app/shell/useAppShell";

const navigateToMock = navigateTo as unknown as ReturnType<typeof vi.fn>;
const zoomReaderByMock = zoomReaderBy as unknown as ReturnType<typeof vi.fn>;
const requestReaderFindMock = requestReaderFind as unknown as ReturnType<typeof vi.fn>;
const setReaderFocusModeMock = setReaderFocusMode as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  navigateToMock.mockClear();
  zoomReaderByMock.mockClear();
  requestReaderFindMock.mockClear();
  setReaderFocusModeMock.mockClear();
});

afterEach(() => {
  // setup.ts already resets appShell.currentRoute, but reset here too
  // so each test in this file starts from a known route.
  appShell.currentRoute.value = "/library";
  readerState.focusAvailable.value = false;
});

test("nav.dashboard command calls navigateTo(\"/\")", () => {
  renderHook(() => useShellMenuCommands());

  dispatchMenuCommand("nav.dashboard");

  expect(navigateToMock).toHaveBeenCalledTimes(1);
  expect(navigateToMock).toHaveBeenCalledWith("/");
});

test("view.zoomIn calls zoomReaderBy(0.1)", () => {
  renderHook(() => useShellMenuCommands());

  dispatchMenuCommand("view.zoomIn");

  expect(zoomReaderByMock).toHaveBeenCalledTimes(1);
  expect(zoomReaderByMock).toHaveBeenCalledWith(0.1);
});

test("reader.find no-ops when not on /reader", () => {
  appShell.currentRoute.value = "/library";
  readerState.focusAvailable.value = true;

  renderHook(() => useShellMenuCommands());

  dispatchMenuCommand("reader.find");

  expect(requestReaderFindMock).not.toHaveBeenCalled();
});

test("reader.find calls requestReaderFind() when route starts with /reader and focusAvailable is true", () => {
  appShell.currentRoute.value = "/reader/doc-42?chunk=abc";
  readerState.focusAvailable.value = true;

  renderHook(() => useShellMenuCommands());

  dispatchMenuCommand("reader.find");

  expect(requestReaderFindMock).toHaveBeenCalledTimes(1);
});
