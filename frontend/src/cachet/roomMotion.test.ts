import { describe, expect, it, vi } from "vitest";

import { enterPanel, enterRoom } from "./roomMotion";

/**
 * roomMotion is WAAPI, so it consults prefers-reduced-motion at call time and
 * never runs a CSS keyframe (the verify surface bans those in-module). These
 * tests pin the two guarantees that matter: it animates a real element when
 * motion is allowed, and it is a no-op under reduced motion or a null element.
 */

function fakeEl(): { el: HTMLElement; animate: ReturnType<typeof vi.fn> } {
  const animate = vi.fn();
  const el = { animate } as unknown as HTMLElement;
  return { el, animate };
}

function mockReducedMotion(reduce: boolean) {
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: reduce && /reduce/.test(q),
    media: q,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

describe("roomMotion", () => {
  it("animates a room and a panel when motion is allowed", () => {
    mockReducedMotion(false);
    const room = fakeEl();
    enterRoom(room.el);
    expect(room.animate).toHaveBeenCalledTimes(1);
    const panel = fakeEl();
    enterPanel(panel.el);
    expect(panel.animate).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  it("is a no-op under prefers-reduced-motion", () => {
    mockReducedMotion(true);
    const room = fakeEl();
    enterRoom(room.el);
    expect(room.animate).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("is a no-op for a null element", () => {
    mockReducedMotion(false);
    expect(() => enterRoom(null)).not.toThrow();
    expect(() => enterPanel(null)).not.toThrow();
    vi.unstubAllGlobals();
  });
});
