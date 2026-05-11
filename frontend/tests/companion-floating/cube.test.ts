/**
 * Tests for the floating-cube companion.
 *
 * The cube lives at `macos-app/Resources/companion-floating.html` —
 * it's loaded into the Swift NSPanel's WKWebView. These tests load
 * the same HTML into jsdom, run the inline `<script>` block, and
 * exercise the public API exposed on `window.companion`.
 *
 * What's pinned:
 *   * State transitions update body classes + cube transforms
 *   * Unknown state names log a warning + post {action:'log'} to the
 *     Swift bridge (regression guard for the audit's silent-fallback
 *     finding D)
 *   * Streak rendering is correct for 0, 1, 2, 3, and >3 day counts
 *     (regression guard for finding I — was previously a no-op)
 *   * Drag threshold accumulates from origin (slow drags do trigger)
 *   * Drop-ready toggles `body.drop-ready`
 *   * Timer registry is bounded (drains after fired callbacks)
 *
 * What's not tested here:
 *   * Real Swift bridge handlers (separate Swift XCTest territory)
 *   * Visual fidelity of CSS transforms (jsdom doesn't compute layout)
 *   * Reduced-motion CSS branch (jsdom honors media queries via
 *     `matchMedia` shim only, not via active stylesheet matching)
 */

// jsdom doesn't ship a typings file. We only consume `JSDOM`'s
// constructor + the `window.close()` method, so a minimal local
// declaration keeps the dep slim — adding @types/jsdom for two
// methods would be overkill.
// @ts-expect-error — see comment above.
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const HTML_PATH = path.resolve(
  __dirname,
  "../../../macos-app/Resources/companion-floating.html",
);
const HTML = readFileSync(HTML_PATH, "utf-8");

interface ShellMessage {
  action: string;
  [key: string]: unknown;
}

interface CompanionAPI {
  setState(name: string): void;
  getState(): string;
  setDropping(active: boolean): void;
  setAlarm(active: boolean): void;
  isAlarming(): boolean;
}

interface CubeWindow extends Window {
  companion: CompanionAPI;
  // jsdom-specific bits we need but the lib `Window` type doesn't expose.
  Event: typeof Event;
  console: Console;
  Math: Math;
  webkit?: {
    messageHandlers?: {
      companionShell?: {
        postMessage: (m: ShellMessage) => void;
      };
    };
  };
}

interface Harness {
  window: CubeWindow;
  document: Document;
  shellMessages: ShellMessage[];
  cleanup: () => void;
}

function loadCube(): Harness {
  const shellMessages: ShellMessage[] = [];
  const dom = new JSDOM(HTML, {
    runScripts: "dangerously",
    pretendToBeVisual: true,
    beforeParse: (w: Window) => {
      // Mock the Swift bridge so postShell() captures into our array.
      (w as unknown as CubeWindow).webkit = {
        messageHandlers: {
          companionShell: {
            postMessage: (m: ShellMessage) => shellMessages.push(m),
          },
        },
      };
    },
  });
  const window = dom.window as unknown as CubeWindow;
  return {
    window,
    document: window.document,
    shellMessages,
    cleanup: () => dom.window.close(),
  };
}

describe("companion cube", () => {
  let h: Harness;

  beforeEach(() => {
    h = loadCube();
  });

  afterEach(() => {
    h.cleanup();
  });

  describe("state machine", () => {
    it("starts in 'idle' state", () => {
      expect(h.window.companion.getState()).toBe("idle");
    });

    it("transitions cleanly between known states", () => {
      h.window.companion.setState("focused");
      expect(h.window.companion.getState()).toBe("focused");
      h.window.companion.setState("thinking");
      expect(h.window.companion.getState()).toBe("thinking");
      h.window.companion.setState("idle");
      expect(h.window.companion.getState()).toBe("idle");
    });

    it("ignores unknown state and posts a log message to the Swift bridge", () => {
      const warnSpy = vi
        .spyOn(h.window.console, "warn")
        .mockImplementation(() => {});
      h.window.companion.setState("not_a_state");
      // currentState unchanged
      expect(h.window.companion.getState()).toBe("idle");
      // Console-warn fires
      expect(warnSpy).toHaveBeenCalledWith(
        "[companion] unknown state:",
        "not_a_state",
      );
      // Swift bridge gets a structured log
      const logMsg = h.shellMessages.find((m) => m.action === "log");
      expect(logMsg).toBeDefined();
      expect(logMsg?.event).toBe("unknown_state");
      expect(logMsg?.name).toBe("not_a_state");
      warnSpy.mockRestore();
    });

    it("sets the active-face class on the right face per state", () => {
      h.window.companion.setState("focused");
      const top = h.document.querySelector('[data-face="top"]');
      expect(top?.classList.contains("active-face")).toBe(true);
      h.window.companion.setState("thinking");
      const right = h.document.querySelector('[data-face="right"]');
      expect(right?.classList.contains("active-face")).toBe(true);
      // Top no longer active.
      expect(top?.classList.contains("active-face")).toBe(false);
    });
  });

  describe("alarm", () => {
    it("setAlarm(true) toggles body.alarm; isAlarming reflects it", () => {
      expect(h.window.companion.isAlarming()).toBe(false);
      h.window.companion.setAlarm(true);
      expect(h.document.body.classList.contains("alarm")).toBe(true);
      expect(h.window.companion.isAlarming()).toBe(true);
      h.window.companion.setAlarm(false);
      expect(h.document.body.classList.contains("alarm")).toBe(false);
      expect(h.window.companion.isAlarming()).toBe(false);
    });

    it("alarm is orthogonal to currentState (both can be active)", () => {
      // "streak" state was removed in T2.5 (commit 83c32404). Use any
      // valid state — alarm flag must coexist with state independent
      // of which state is active.
      h.window.companion.setState("thinking");
      h.window.companion.setAlarm(true);
      expect(h.window.companion.getState()).toBe("thinking");
      expect(h.window.companion.isAlarming()).toBe(true);
      // Both classes coexist.
      expect(h.document.body.classList.contains("alarm")).toBe(true);
    });
  });

  describe("drop target", () => {
    it("setDropping toggles body.drop-ready and the aura", () => {
      h.window.companion.setDropping(true);
      expect(h.document.body.classList.contains("drop-ready")).toBe(true);
      const aura = h.document.getElementById("aura");
      expect(aura?.classList.contains("glowing")).toBe(true);
      h.window.companion.setDropping(false);
      expect(h.document.body.classList.contains("drop-ready")).toBe(false);
      expect(aura?.classList.contains("glowing")).toBe(false);
    });
  });

  // The "streak rendering" describe block was removed when the streak
  // overlay feature was removed in T2.5 (commit 83c32404). Tests stayed
  // behind because main's removal commit didn't drop them. CI surfaced
  // it on this branch.

  describe("drag bridge", () => {
    function fakePointerEvent(
      type: string,
      screenX: number,
      screenY: number,
      button = 0,
    ): Event {
      // jsdom doesn't ship a complete PointerEvent — fall back to
      // a CustomEvent with the screen fields the cube reads.
      const e = new h.window.Event(type, { bubbles: true });
      Object.assign(e, { screenX, screenY, button });
      return e;
    }

    it("threshold from origin: a single 5px move crosses the 3px gate", () => {
      h.window.dispatchEvent(fakePointerEvent("pointerdown", 100, 100));
      h.window.dispatchEvent(fakePointerEvent("pointermove", 105, 100));
      const dragStart = h.shellMessages.find((m) => m.action === "dragStart");
      expect(dragStart).toBeDefined();
      // Increment posted for the same move.
      const dragMove = h.shellMessages.find((m) => m.action === "dragMove");
      expect(dragMove).toBeDefined();
      expect(dragMove?.dx).toBe(5);
      expect(dragMove?.dy).toBe(0);
    });

    it("sub-threshold movement does NOT post dragStart", () => {
      h.window.dispatchEvent(fakePointerEvent("pointerdown", 100, 100));
      h.window.dispatchEvent(fakePointerEvent("pointermove", 101, 100));
      h.window.dispatchEvent(fakePointerEvent("pointermove", 102, 100));
      // 2px total — under the 3px threshold. No drag yet.
      expect(h.shellMessages.find((m) => m.action === "dragStart")).toBeUndefined();
      // A third px crosses the threshold (cumulative-from-origin).
      h.window.dispatchEvent(fakePointerEvent("pointermove", 103, 100));
      expect(h.shellMessages.find((m) => m.action === "dragStart")).toBeDefined();
    });

    it("pointerup with no movement fires 'tap'", () => {
      h.window.dispatchEvent(fakePointerEvent("pointerdown", 100, 100));
      h.window.dispatchEvent(fakePointerEvent("pointerup", 100, 100));
      expect(h.shellMessages.find((m) => m.action === "tap")).toBeDefined();
      expect(
        h.shellMessages.find((m) => m.action === "dragStart"),
      ).toBeUndefined();
    });

    it("pointerup after movement fires 'dragEnd' (not 'tap')", () => {
      h.window.dispatchEvent(fakePointerEvent("pointerdown", 100, 100));
      h.window.dispatchEvent(fakePointerEvent("pointermove", 110, 100));
      h.window.dispatchEvent(fakePointerEvent("pointerup", 110, 100));
      expect(h.shellMessages.find((m) => m.action === "dragEnd")).toBeDefined();
      expect(h.shellMessages.find((m) => m.action === "tap")).toBeUndefined();
    });

    it("window blur ends an in-progress drag (release-outside-panel)", () => {
      h.window.dispatchEvent(fakePointerEvent("pointerdown", 100, 100));
      h.window.dispatchEvent(fakePointerEvent("pointermove", 110, 100));
      // Simulate user releasing the mouse outside the panel — pointerup
      // never fires, but the window loses focus.
      h.window.dispatchEvent(new h.window.Event("blur"));
      expect(h.document.body.classList.contains("dragging")).toBe(false);
      expect(h.shellMessages.find((m) => m.action === "dragEnd")).toBeDefined();
    });

    it("right-click (button !== 0) is ignored", () => {
      h.window.dispatchEvent(fakePointerEvent("pointerdown", 100, 100, 2));
      h.window.dispatchEvent(fakePointerEvent("pointermove", 110, 100));
      // No drag started.
      expect(
        h.shellMessages.find((m) => m.action === "dragStart"),
      ).toBeUndefined();
    });
  });
});
