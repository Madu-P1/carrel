import type { JSX } from "preact";

import {
  appShell,
  setLeftRailWidth,
  setRightPanelWidth,
  SHELL_PANEL_WIDTHS
} from "../useAppShell";

export type ResizablePanel = "left" | "right";

function panelWidthFor(panel: ResizablePanel): number {
  return panel === "left"
    ? appShell.leftRailWidth.value
    : appShell.rightPanelWidth.value;
}

function setPanelWidth(panel: ResizablePanel, width: number): void {
  if (panel === "left") {
    setLeftRailWidth(width);
  } else {
    setRightPanelWidth(width);
  }
}

function resizeLimits(panel: ResizablePanel) {
  return panel === "left" ? SHELL_PANEL_WIDTHS.left : SHELL_PANEL_WIDTHS.right;
}

interface PanelResizeHandlers {
  startPanelResize: (
    panel: ResizablePanel,
    event: JSX.TargetedPointerEvent<HTMLDivElement>
  ) => void;
  resizePanelFromKeyboard: (
    panel: ResizablePanel,
    event: JSX.TargetedKeyboardEvent<HTMLDivElement>
  ) => void;
}

/**
 * Pointer + keyboard handlers for the left/right panel resize separators.
 *
 * Pointer: capture-phase pointermove on window so the drag tracks even when
 * the cursor leaves the handle. Body cursor + user-select are restored on
 * release. Width clamping happens inside `setLeftRailWidth` /
 * `setRightPanelWidth` so we don't duplicate it here.
 *
 * Keyboard: ArrowLeft/ArrowRight nudge by 16px (32 with Shift). Home/End
 * snap to min/max. The "left vs right" semantics flip for the right panel
 * because growing it means dragging the handle to the LEFT, not right.
 */
export function usePanelResize(): PanelResizeHandlers {
  const startPanelResize: PanelResizeHandlers["startPanelResize"] = (
    panel,
    event
  ) => {
    if (event.button !== 0) return;
    event.preventDefault();

    const startX = event.clientX;
    const startWidth = panelWidthFor(panel);
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onPointerMove = (moveEvent: PointerEvent) => {
      const delta = moveEvent.clientX - startX;
      const nextWidth = panel === "left"
        ? startWidth + delta
        : startWidth - delta;
      setPanelWidth(panel, nextWidth);
    };

    const stopResize = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopResize);
      window.removeEventListener("pointercancel", stopResize);
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopResize);
    window.addEventListener("pointercancel", stopResize);
  };

  const resizePanelFromKeyboard: PanelResizeHandlers["resizePanelFromKeyboard"] = (
    panel,
    event
  ) => {
    const limits = resizeLimits(panel);
    const step = event.shiftKey ? 32 : 16;
    let nextWidth: number | null = null;

    switch (event.key) {
      case "ArrowLeft":
        nextWidth = panel === "left"
          ? panelWidthFor(panel) - step
          : panelWidthFor(panel) + step;
        break;
      case "ArrowRight":
        nextWidth = panel === "left"
          ? panelWidthFor(panel) + step
          : panelWidthFor(panel) - step;
        break;
      case "Home":
        nextWidth = limits.min;
        break;
      case "End":
        nextWidth = limits.max;
        break;
      default:
        return;
    }

    event.preventDefault();
    setPanelWidth(panel, nextWidth);
  };

  return { startPanelResize, resizePanelFromKeyboard };
}
