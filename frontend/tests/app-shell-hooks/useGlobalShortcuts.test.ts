import { renderHook } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

// Mock focusAskInput so we can verify the / shortcut wires the focus
// after the timeout fires.
vi.mock("@/features/ask/focusRegistry", () => ({
  focusAskInput: vi.fn().mockReturnValue(true)
}));

// Mock navigateTo so we don't have to render the real router for the
// "/" -> /ask navigation assertion.
/* eslint-disable @typescript-eslint/consistent-type-imports */
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

import { focusAskInput } from "@/features/ask/focusRegistry";

import { useGlobalShortcuts } from "../../src/app/shell/hooks/useGlobalShortcuts";
import { shortcutsOverlayOpen } from "../../src/app/shell/ShortcutsOverlay";
import { navigateTo } from "../../src/app/shell/useAppShell";

const navigateToMock = navigateTo as unknown as ReturnType<typeof vi.fn>;
const focusAskInputMock = focusAskInput as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  navigateToMock.mockClear();
  focusAskInputMock.mockClear();
  shortcutsOverlayOpen.value = false;
});

afterEach(() => {
  shortcutsOverlayOpen.value = false;
});

test("\"?\" key when no overlay open opens the shortcuts overlay", () => {
  renderHook(() => useGlobalShortcuts());

  expect(shortcutsOverlayOpen.value).toBe(false);

  window.dispatchEvent(new KeyboardEvent("keydown", { key: "?" }));

  expect(shortcutsOverlayOpen.value).toBe(true);
});

test("\"?\" key when overlay open closes it", () => {
  renderHook(() => useGlobalShortcuts());

  shortcutsOverlayOpen.value = true;
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "?" }));

  expect(shortcutsOverlayOpen.value).toBe(false);
});

test("\"/\" key navigates to /ask AND focusAskInput is called after the timeout", async () => {
  vi.useFakeTimers();

  renderHook(() => useGlobalShortcuts());

  window.dispatchEvent(new KeyboardEvent("keydown", { key: "/" }));

  // navigateTo runs synchronously.
  expect(navigateToMock).toHaveBeenCalledTimes(1);
  expect(navigateToMock).toHaveBeenCalledWith("/ask");

  // focusAskInput is deferred to a setTimeout(60) so the new view
  // can render before we hand it focus.
  expect(focusAskInputMock).not.toHaveBeenCalled();

  await vi.advanceTimersByTimeAsync(60);

  expect(focusAskInputMock).toHaveBeenCalledTimes(1);

  vi.useRealTimers();
});

test("key with target=INPUT/TEXTAREA is ignored", () => {
  renderHook(() => useGlobalShortcuts());

  // Plant a real input in the DOM and use it as the event target. The
  // hook's isEditableTarget() check uses tagName + instanceof HTMLElement.
  const input = document.createElement("input");
  document.body.appendChild(input);

  // KeyboardEvent doesn't carry a target by default — we have to
  // dispatch on the element itself so target is set.
  const event = new KeyboardEvent("keydown", {
    key: "?",
    bubbles: true
  });
  input.dispatchEvent(event);

  expect(shortcutsOverlayOpen.value).toBe(false);

  // Same for textarea.
  const textarea = document.createElement("textarea");
  document.body.appendChild(textarea);
  const slashEvent = new KeyboardEvent("keydown", {
    key: "/",
    bubbles: true
  });
  textarea.dispatchEvent(slashEvent);

  expect(navigateToMock).not.toHaveBeenCalled();

  document.body.removeChild(input);
  document.body.removeChild(textarea);
});

test("key with metaKey/ctrlKey held is ignored", () => {
  renderHook(() => useGlobalShortcuts());

  // metaKey -> early return.
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "?", metaKey: true }));
  expect(shortcutsOverlayOpen.value).toBe(false);

  // ctrlKey -> early return.
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "/", ctrlKey: true }));
  expect(navigateToMock).not.toHaveBeenCalled();

  // altKey -> early return.
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "?", altKey: true }));
  expect(shortcutsOverlayOpen.value).toBe(false);

  // Sanity: a plain "?" still toggles the overlay, proving the listener
  // is wired and only the modifier path bailed.
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "?" }));
  expect(shortcutsOverlayOpen.value).toBe(true);
});
