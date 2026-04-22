import { render } from "@testing-library/preact";
import { afterEach, describe, expect, test, vi } from "vitest";

import { clearFlight, registerFlight } from "@/features/shared/flightRegistry";
import { useCitationFlight } from "@/features/reader/hooks/useCitationFlight";

function makeRect(x: number, y: number, w: number, h: number): DOMRect {
  return {
    x, y, width: w, height: h,
    top: y, left: x, right: x + w, bottom: y + h,
    toJSON: () => ({}),
  } as DOMRect;
}

function Probe({ docId, chunkId }: { docId: string; chunkId: string | null }) {
  useCitationFlight(docId, chunkId);
  return null;
}

describe("useCitationFlight (SM-2)", () => {
  afterEach(() => {
    clearFlight();
    document.body.innerHTML = "";
  });

  test("spawns a ghost and applies anim-pulseOnce on landing when a matching flight is present", async () => {
    // Install a target chunk element in the DOM with a known rect.
    const chunkRect = makeRect(500, 500, 240, 80);
    const chunk = document.createElement("div");
    chunk.setAttribute("data-chunk-id", "chunk-X");
    document.body.appendChild(chunk);
    vi.spyOn(chunk, "getBoundingClientRect").mockReturnValue(chunkRect);

    registerFlight({
      kind: "citation-chip",
      id: "chunk-X",
      rect: makeRect(20, 20, 120, 30),
      html: '<span class="chip">source</span>',
      docId: "doc-7",
      chunkId: "chunk-X",
    });

    let capturedAnimation: { _finish?: () => void } = {};
    // Intercept element.animate only for ghost divs (not the target chunk).
    const originalAnimate = HTMLElement.prototype.animate;
    HTMLElement.prototype.animate = function (this: HTMLElement) {
      const listeners: Record<string, EventListener[]> = {};
      const anim = {
        addEventListener(event: string, fn: EventListener) {
          listeners[event] = [...(listeners[event] ?? []), fn];
        },
        removeEventListener() {},
        cancel() {
          listeners.cancel?.forEach((fn) => fn(new Event("cancel")));
        },
        finish() {
          listeners.finish?.forEach((fn) => fn(new Event("finish")));
        }
      };
      capturedAnimation = { _finish: () => anim.finish() };
      return anim as unknown as Animation;
    } as unknown as typeof HTMLElement.prototype.animate;

    try {
      render(<Probe docId="doc-7" chunkId="chunk-X" />);
      // Poll for the raf-based flight kickoff. Give it a few ticks.
      for (let i = 0; i < 6; i++) {
        await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
      }
      // The ghost should have been added to the body.
      const ghost = Array.from(document.body.querySelectorAll("div")).find((n) =>
        n.innerHTML.includes('<span class="chip">source</span>'),
      );
      expect(ghost).toBeTruthy();
      // Fire the ghost's finish → target chunk should gain .anim-pulseOnce.
      capturedAnimation._finish?.();
      expect(chunk.classList.contains("anim-pulseOnce")).toBe(true);
    } finally {
      HTMLElement.prototype.animate = originalAnimate;
    }
  });

  test("no-op when flight docId does not match the target doc", async () => {
    const chunk = document.createElement("div");
    chunk.setAttribute("data-chunk-id", "chunk-Y");
    document.body.appendChild(chunk);
    registerFlight({
      kind: "citation-chip",
      id: "chunk-Y",
      rect: makeRect(0, 0, 100, 30),
      html: "<span>cite</span>",
      docId: "doc-OTHER",
      chunkId: "chunk-Y",
    });

    const animateSpy = vi.fn();
    const originalAnimate = HTMLElement.prototype.animate;
    HTMLElement.prototype.animate = animateSpy as unknown as typeof HTMLElement.prototype.animate;
    try {
      render(<Probe docId="doc-SELF" chunkId="chunk-Y" />);
      for (let i = 0; i < 4; i++) {
        await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
      }
      expect(animateSpy).not.toHaveBeenCalled();
    } finally {
      HTMLElement.prototype.animate = originalAnimate;
    }
  });

  test("no-op when chunkId is null", async () => {
    const animateSpy = vi.fn();
    const originalAnimate = HTMLElement.prototype.animate;
    HTMLElement.prototype.animate = animateSpy as unknown as typeof HTMLElement.prototype.animate;
    try {
      render(<Probe docId="doc-1" chunkId={null} />);
      for (let i = 0; i < 2; i++) {
        await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
      }
      expect(animateSpy).not.toHaveBeenCalled();
    } finally {
      HTMLElement.prototype.animate = originalAnimate;
    }
  });
});
