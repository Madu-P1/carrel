import { render } from "@testing-library/preact";
import { useEffect } from "preact/hooks";
import { afterEach, describe, expect, test, vi } from "vitest";

import { clearFlight, registerFlight } from "@/features/shared/flightRegistry";
import { useCardFlight } from "@/features/reader/hooks/useCardFlight";

function makeRect(x: number, y: number, w: number, h: number): DOMRect {
  return {
    x, y, width: w, height: h,
    top: y, left: x, right: x + w, bottom: y + h,
    toJSON: () => ({}),
  } as DOMRect;
}

function Probe({ docId, targetRect }: { docId: string; targetRect: DOMRect }) {
  const ref = useCardFlight<HTMLDivElement>(docId);
  useEffect(() => {
    if (ref.current) {
      vi.spyOn(ref.current, "getBoundingClientRect").mockReturnValue(targetRect);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <div ref={ref} data-testid="target">reader header</div>;
}

describe("useCardFlight (SM-1)", () => {
  afterEach(() => {
    clearFlight();
  });

  test("runs FLIP on the target when a matching doc-card flight is present", async () => {
    const source = makeRect(100, 200, 300, 50);
    const target = makeRect(50, 30, 800, 80);
    registerFlight({ kind: "doc-card", id: "doc-42", rect: source });

    const animateSpy = vi.fn(() => ({
      addEventListener() {},
      removeEventListener() {},
      cancel() {},
      finish() {}
    } as unknown as Animation));
    const originalAnimate = HTMLElement.prototype.animate;
    HTMLElement.prototype.animate = animateSpy as unknown as typeof HTMLElement.prototype.animate;

    try {
      const spy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(target);
      render(<Probe docId="doc-42" targetRect={target} />);
      await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
      expect(animateSpy).toHaveBeenCalled();
      spy.mockRestore();
    } finally {
      HTMLElement.prototype.animate = originalAnimate;
    }
  });

  test("no-op when the flight's id does not match", async () => {
    registerFlight({ kind: "doc-card", id: "doc-A", rect: makeRect(0, 0, 50, 50) });
    const animateSpy = vi.fn();
    const originalAnimate = HTMLElement.prototype.animate;
    HTMLElement.prototype.animate = animateSpy as unknown as typeof HTMLElement.prototype.animate;
    try {
      render(<Probe docId="doc-B" targetRect={makeRect(0, 0, 800, 80)} />);
      await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
      expect(animateSpy).not.toHaveBeenCalled();
    } finally {
      HTMLElement.prototype.animate = originalAnimate;
    }
  });

  test("no-op when there is no pending flight", async () => {
    const animateSpy = vi.fn();
    const originalAnimate = HTMLElement.prototype.animate;
    HTMLElement.prototype.animate = animateSpy as unknown as typeof HTMLElement.prototype.animate;
    try {
      render(<Probe docId="doc-solo" targetRect={makeRect(0, 0, 800, 80)} />);
      await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
      expect(animateSpy).not.toHaveBeenCalled();
    } finally {
      HTMLElement.prototype.animate = originalAnimate;
    }
  });
});
