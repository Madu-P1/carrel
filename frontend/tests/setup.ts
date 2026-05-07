import { act, cleanup } from "@testing-library/preact";
import { afterEach, beforeEach } from "vitest";

import { appShell, SHELL_PANEL_WIDTHS } from "../src/app/shell/useAppShell";
import { resetDocumentsQuery } from "../src/features/library/hooks/useDocumentsQuery";
import { resetReaderDetailQueries } from "../src/features/reader/hooks/useReaderDetail";
import { readerState, READER_OUTLINE_WIDTH, resetReaderState } from "../src/features/reader/state";

import { installFetchMock, resetFetchMock } from "./support/mockFetch";

installFetchMock();

let prefersDark = true;
let prefersReducedMotion = false;

function isKnownPreactUnmountNoise(reason: unknown): boolean {
  return (
    reason instanceof TypeError &&
    reason.message.includes("Cannot read properties of null") &&
    reason.message.includes("'__k'")
  );
}

window.addEventListener("unhandledrejection", (event) => {
  if (isKnownPreactUnmountNoise(event.reason)) {
    event.preventDefault();
  }
});

window.matchMedia = (query: string) =>
  ({
    matches: query.includes("prefers-reduced-motion")
      ? prefersReducedMotion
      : query.includes("dark")
        ? prefersDark
        : false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent() {
      return false;
    }
  }) as MediaQueryList;

export function setReducedMotionPreference(value: boolean): void {
  prefersReducedMotion = value;
}

export function setDarkModePreference(value: boolean): void {
  prefersDark = value;
}

Object.defineProperty(window, "scrollTo", {
  configurable: true,
  value: () => {}
});

Object.defineProperty(HTMLElement.prototype, "scrollTo", {
  configurable: true,
  value: () => {}
});

Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
  configurable: true,
  value: () => ({
    clearRect() {},
    drawImage() {},
    fillRect() {},
    save() {},
    restore() {},
    scale() {},
    setTransform() {}
  })
});

// jsdom does not implement the Web Animations API. Install a minimal shim
// that satisfies our usage in lib/flip.ts and hooks that wrap it. Each
// returned Animation exposes addEventListener, cancel, and finish — enough
// for our onFinish plumbing.
if (!Element.prototype.animate) {
  Object.defineProperty(Element.prototype, "animate", {
    configurable: true,
    writable: true,
    value(this: Element) {
      const listeners: Record<string, EventListener[]> = {};
      const animation = {
        addEventListener(event: string, fn: EventListener) {
          listeners[event] = [...(listeners[event] ?? []), fn];
        },
        removeEventListener(event: string, fn: EventListener) {
          listeners[event] = (listeners[event] ?? []).filter((other) => other !== fn);
        },
        cancel() {
          listeners.cancel?.forEach((fn) => fn(new Event("cancel")));
        },
        finish() {
          listeners.finish?.forEach((fn) => fn(new Event("finish")));
        }
      };
      return animation as unknown as Animation;
    }
  });
}

beforeEach(() => {
  (window as Window & { __CARREL_LOCAL_API_TOKEN?: string }).__CARREL_LOCAL_API_TOKEN = "test-local-token";
  document.documentElement.className = "";
  delete document.body.dataset.appBooted;
  window.localStorage.setItem("carrel.first-run-tour.completed", "1");
  // Keep this in sync with TOUR_VERSION in
  // src/features/onboarding/FirstRunTour.tsx. When the production
  // version bumps (substantive content updates), bump it here too —
  // otherwise tests render the auto-opening tour over the route under
  // test, and "Found multiple elements with the text Carrel" failures
  // start showing up across smoke/feature suites.
  window.localStorage.setItem("carrel.first-run-tour.version", "6");
  prefersDark = true;
  prefersReducedMotion = false;
  act(() => {
    appShell.leftOpen.value = true;
    appShell.rightOpen.value = false;
    appShell.rightPanelContent.value = null;
    appShell.leftRailWidth.value = SHELL_PANEL_WIDTHS.left.default;
    appShell.rightPanelWidth.value = SHELL_PANEL_WIDTHS.right.default;
    appShell.theme.value = "system";
    appShell.currentRoute.value = "/library";
    appShell.lastReaderDocumentId.value = null;
    window.localStorage.removeItem("carrel.metrics.first-ask-recorded");
    window.localStorage.removeItem("carrel.metrics.first-launch-recorded");
    window.localStorage.removeItem("carrel.reader.last-document-id");
    for (let index = window.localStorage.length - 1; index >= 0; index -= 1) {
      const key = window.localStorage.key(index);
      if (key?.startsWith("carrel.reader.restore.")) {
        window.localStorage.removeItem(key);
      }
    }
    resetDocumentsQuery();
    resetReaderDetailQueries();
    resetReaderState();
    readerState.outlineWidth.value = READER_OUTLINE_WIDTH.default;
  });
  window.history.pushState({}, "", "/");
  resetFetchMock();
});

afterEach(async () => {
  await act(async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  });
  cleanup();
  await act(async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  });
});
