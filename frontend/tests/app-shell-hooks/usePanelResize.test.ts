import { act, renderHook } from "@testing-library/preact";
import { afterEach, expect, test } from "vitest";

import { usePanelResize } from "../../src/app/shell/hooks/usePanelResize";
import {
  appShell,
  SHELL_PANEL_WIDTHS
} from "../../src/app/shell/useAppShell";

/**
 * usePanelResize wires keyboard + pointer handlers for the shell's left
 * and right resize handles. Width clamping happens inside the
 * setLeftRailWidth / setRightPanelWidth helpers, so we don't need to
 * exercise clamp logic here — we want to verify the directional
 * semantics, especially the right-panel "left arrow grows the panel"
 * flip.
 */

afterEach(() => {
  // Belt + suspenders: setup.ts also resets these in beforeEach.
  act(() => {
    appShell.leftRailWidth.value = SHELL_PANEL_WIDTHS.left.default;
    appShell.rightPanelWidth.value = SHELL_PANEL_WIDTHS.right.default;
  });
});

function makeKeyboardEvent(
  key: string,
  init: { shiftKey?: boolean } = {}
): {
  event: KeyboardEvent & { preventDefault: () => void };
  preventDefault: () => boolean;
} {
  let prevented = false;
  const event = {
    key,
    shiftKey: init.shiftKey ?? false,
    preventDefault: () => {
      prevented = true;
    }
  } as unknown as KeyboardEvent & { preventDefault: () => void };
  return { event, preventDefault: () => prevented };
}

test("ArrowRight on left panel grows it by 16px (32 with shift)", () => {
  const { result } = renderHook(() => usePanelResize());

  const startWidth = appShell.leftRailWidth.value;

  // Plain ArrowRight nudges by 16.
  const { event } = makeKeyboardEvent("ArrowRight");
  act(() => {
    result.current.resizePanelFromKeyboard(
      "left",
      // The hook signature uses Preact's TargetedKeyboardEvent, but the
      // event object only needs `key`, `shiftKey`, and `preventDefault`
      // for this code path.
      event as never
    );
  });
  expect(appShell.leftRailWidth.value).toBe(startWidth + 16);

  // Shift doubles the step to 32.
  const { event: shiftEvent } = makeKeyboardEvent("ArrowRight", {
    shiftKey: true
  });
  act(() => {
    result.current.resizePanelFromKeyboard("left", shiftEvent as never);
  });
  expect(appShell.leftRailWidth.value).toBe(startWidth + 16 + 32);
});

test("ArrowLeft on right panel grows it by 16px (semantics flip)", () => {
  const { result } = renderHook(() => usePanelResize());

  const startWidth = appShell.rightPanelWidth.value;

  // For the right panel, ArrowLeft is the "grow" key because dragging
  // the handle leftward expands the panel toward the center.
  const { event } = makeKeyboardEvent("ArrowLeft");
  act(() => {
    result.current.resizePanelFromKeyboard("right", event as never);
  });
  expect(appShell.rightPanelWidth.value).toBe(startWidth + 16);

  // ArrowRight on the right panel SHRINKS it.
  const { event: rightEvent } = makeKeyboardEvent("ArrowRight");
  act(() => {
    result.current.resizePanelFromKeyboard("right", rightEvent as never);
  });
  expect(appShell.rightPanelWidth.value).toBe(startWidth);
});

test("Home/End snap to the panel's min/max from SHELL_PANEL_WIDTHS", () => {
  const { result } = renderHook(() => usePanelResize());

  // Left panel — Home -> min, End -> max.
  const { event: homeLeft } = makeKeyboardEvent("Home");
  act(() => {
    result.current.resizePanelFromKeyboard("left", homeLeft as never);
  });
  expect(appShell.leftRailWidth.value).toBe(SHELL_PANEL_WIDTHS.left.min);

  const { event: endLeft } = makeKeyboardEvent("End");
  act(() => {
    result.current.resizePanelFromKeyboard("left", endLeft as never);
  });
  expect(appShell.leftRailWidth.value).toBe(SHELL_PANEL_WIDTHS.left.max);

  // Right panel snaps independently to its own limits.
  const { event: homeRight } = makeKeyboardEvent("Home");
  act(() => {
    result.current.resizePanelFromKeyboard("right", homeRight as never);
  });
  expect(appShell.rightPanelWidth.value).toBe(SHELL_PANEL_WIDTHS.right.min);

  const { event: endRight } = makeKeyboardEvent("End");
  act(() => {
    result.current.resizePanelFromKeyboard("right", endRight as never);
  });
  expect(appShell.rightPanelWidth.value).toBe(SHELL_PANEL_WIDTHS.right.max);
});

test("pointerdown with non-left button (event.button !== 0) is a no-op", () => {
  const { result } = renderHook(() => usePanelResize());

  const startWidth = appShell.leftRailWidth.value;
  const startCursor = document.body.style.cursor;
  const startUserSelect = document.body.style.userSelect;

  let prevented = false;
  const pointerEvent = {
    button: 2, // right-click
    clientX: 100,
    preventDefault: () => {
      prevented = true;
    }
  } as unknown as PointerEvent;

  act(() => {
    result.current.startPanelResize("left", pointerEvent as never);
  });

  // Width should not have moved, body cursor should not have flipped to
  // col-resize, and preventDefault should NOT have been called (the early
  // return happens before any of that).
  expect(appShell.leftRailWidth.value).toBe(startWidth);
  expect(document.body.style.cursor).toBe(startCursor);
  expect(document.body.style.userSelect).toBe(startUserSelect);
  expect(prevented).toBe(false);

  // Now fire a pointermove to make sure the listeners weren't actually
  // attached — the width should still not change.
  const moveEvent = new Event("pointermove") as PointerEvent;
  Object.defineProperty(moveEvent, "clientX", { value: 200 });
  window.dispatchEvent(moveEvent);
  expect(appShell.leftRailWidth.value).toBe(startWidth);
});
