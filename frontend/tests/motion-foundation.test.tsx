import { act, render, waitFor } from "@testing-library/preact";
import { useState } from "preact/hooks";
import { expect, test, vi } from "vitest";

import { markAppBootedAfterInteractive } from "../src/app/shell/boot";
import { useAnimation } from "../src/design-system/hooks/useAnimation";
import {
  prefersReducedMotion,
  transition,
  transitions
} from "../src/design-system/motion";
import { setReducedMotionPreference } from "./setup";

function AnimatedHarness() {
  const [tick, setTick] = useState(0);
  const ref = useAnimation<HTMLDivElement>(
    {
      keyframes: [{ opacity: 0 }, { opacity: 1 }],
      options: { duration: 180, easing: "ease-out" }
    },
    [tick]
  );

  return (
    <div>
      <button onClick={() => setTick((value) => value + 1)} type="button">
        Replay
      </button>
      <div ref={ref}>Animated</div>
    </div>
  );
}

test("motion helpers compose transition strings", () => {
  expect(transition("opacity", "fast", "out")).toBe("opacity var(--dur-fast) var(--ease-out)");
  expect(
    transitions([
      ["opacity", "fast", "out"],
      ["transform", "base", "swift"]
    ])
  ).toBe(
    "opacity var(--dur-fast) var(--ease-out), transform var(--dur-base) var(--ease-swift)"
  );
});

test("prefersReducedMotion reflects the media query", () => {
  setReducedMotionPreference(false);
  expect(prefersReducedMotion()).toBe(false);

  setReducedMotionPreference(true);
  expect(prefersReducedMotion()).toBe(true);
});

test("useAnimation collapses WAAPI duration when reduced motion is enabled", async () => {
  const cancel = vi.fn();
  const originalAnimate = HTMLElement.prototype.animate;
  Object.defineProperty(HTMLElement.prototype, "animate", {
    configurable: true,
    value: vi.fn(() => ({ cancel } as unknown as Animation))
  });
  const animate = HTMLElement.prototype.animate as unknown as ReturnType<typeof vi.fn>;

  setReducedMotionPreference(true);
  render(<AnimatedHarness />);

  await waitFor(() => {
    expect(animate).toHaveBeenCalled();
  });

  expect(animate.mock.calls[0]?.[1]).toMatchObject({ duration: 0, easing: "ease-out" });

  Object.defineProperty(HTMLElement.prototype, "animate", {
    configurable: true,
    value: originalAnimate
  });
});

test("markAppBootedAfterInteractive flips the body flag after the boot settle window", async () => {
  vi.useFakeTimers();
  const raf = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
    callback(0);
    return 1;
  });

  expect(document.body.dataset.appBooted).toBeUndefined();

  markAppBootedAfterInteractive();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(260);
  });

  expect(document.body.dataset.appBooted).toBe("true");

  raf.mockRestore();
  vi.useRealTimers();
});
