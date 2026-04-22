import { afterEach, describe, expect, test, vi } from "vitest";

import { flipFromRect, ghostFlight } from "@/lib/flip";

function makeRect(x: number, y: number, w: number, h: number): DOMRect {
  return {
    x, y, width: w, height: h,
    top: y, left: x, right: x + w, bottom: y + h,
    toJSON: () => ({}),
  } as DOMRect;
}

function makeElement(rect: DOMRect): HTMLElement {
  const el = document.createElement("div");
  vi.spyOn(el, "getBoundingClientRect").mockReturnValue(rect);
  const animateSpy = vi.fn().mockImplementation(() => {
    const listeners: Record<string, EventListener[]> = {};
    return {
      addEventListener: (event: string, fn: EventListener) => {
        listeners[event] = [...(listeners[event] ?? []), fn];
      },
      cancel: () => {},
      _fire: (event: string) => listeners[event]?.forEach((fn) => fn(new Event(event))),
    } as unknown as Animation;
  });
  (el as unknown as { animate: typeof animateSpy }).animate = animateSpy;
  return el;
}

describe("flipFromRect", () => {
  // Note: setup.ts installs window.matchMedia globally. We only spy on it
  // locally; never reassign, so vi.restoreAllMocks() can put it back cleanly
  // without clobbering the shared matchMedia function.

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("invokes element.animate with a from→to transform pair", () => {
    const source = makeRect(0, 0, 200, 40);
    const target = makeRect(400, 200, 600, 60);
    const el = makeElement(target);
    const animation = flipFromRect(el, source);
    expect(animation).not.toBeNull();
    const animateSpy = (el as unknown as { animate: ReturnType<typeof vi.fn> }).animate;
    expect(animateSpy).toHaveBeenCalledTimes(1);
    const [keyframes, options] = animateSpy.mock.calls[0];
    expect(Array.isArray(keyframes)).toBe(true);
    expect((keyframes as Keyframe[])[0].transform).toMatch(/translate/);
    expect((keyframes as Keyframe[])[0].transform).toMatch(/scale/);
    expect((keyframes as Keyframe[])[1].transform).toMatch(/translate\(0, 0\)/);
    expect(options?.duration).toBe(320);
  });

  test("no animation when source and target rects are effectively equal", () => {
    const rect = makeRect(50, 50, 100, 40);
    const el = makeElement(rect);
    const animation = flipFromRect(el, rect);
    expect(animation).toBeNull();
    const animateSpy = (el as unknown as { animate: ReturnType<typeof vi.fn> }).animate;
    expect(animateSpy).not.toHaveBeenCalled();
  });

  test("no animation when target has zero dimensions", () => {
    const source = makeRect(0, 0, 100, 40);
    const target = makeRect(0, 0, 0, 0);
    const el = makeElement(target);
    expect(flipFromRect(el, source)).toBeNull();
  });

  test("collapses to null when reduced motion is preferred", () => {
    // Spy on the existing matchMedia rather than reassigning it — restoreAllMocks
    // will cleanly put it back after the test, without clobbering setup.ts's version.
    const spy = vi.spyOn(window, "matchMedia").mockImplementation(
      (q: string) =>
        ({
          matches: q.includes("reduce"),
          media: q,
          onchange: null,
          addEventListener: () => {},
          removeEventListener: () => {},
          addListener: () => {},
          removeListener: () => {},
          dispatchEvent: () => false,
        }) as MediaQueryList,
    );
    const onFinish = vi.fn();
    const source = makeRect(0, 0, 200, 40);
    const target = makeRect(400, 200, 600, 60);
    const el = makeElement(target);
    const animation = flipFromRect(el, source, { onFinish });
    expect(animation).toBeNull();
    expect(onFinish).toHaveBeenCalledOnce();
    spy.mockRestore();
  });
});

describe("ghostFlight", () => {
  afterEach(() => {
    // Clean up any ghosts that leaked.
    document.querySelectorAll("[data-ghost-test]").forEach((el) => el.remove());
  });

  test("spawns a ghost element at the source rect and removes it after animation", () => {
    const source = makeRect(10, 10, 50, 24);
    const targetRect = makeRect(500, 500, 200, 40);
    const target = makeElement(targetRect);
    document.body.appendChild(target);
    const animateSpy = (target as unknown as { animate: ReturnType<typeof vi.fn> }).animate;

    const html = '<span data-ghost-test>ghost</span>';
    const animation = ghostFlight(html, source, target);
    expect(animation).not.toBeNull();

    // The ghost should exist as a fixed-positioned div attached to body.
    const ghosts = document.body.querySelectorAll("div");
    const ghostNode = Array.from(ghosts).find((n) => n.innerHTML.includes("ghost"));
    expect(ghostNode).toBeTruthy();
    expect(ghostNode?.style.position).toBe("fixed");
    expect(ghostNode?.style.top).toBe("10px");
    expect(ghostNode?.style.left).toBe("10px");

    // Fire finish via the polyfilled Animation → ghost should be removed.
    (animation as unknown as { finish: () => void }).finish();
    const remaining = Array.from(document.body.querySelectorAll("div")).find((n) =>
      n.innerHTML.includes("ghost"),
    );
    expect(remaining).toBeUndefined();
    target.remove();
    // animateSpy was invoked on the target we created via makeElement, but the
    // ghost is a fresh div using the prototype animate polyfill. Ensure target
    // itself wasn't animated.
    expect(animateSpy).not.toHaveBeenCalled();
  });
});
