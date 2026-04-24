import { useEffect, useRef, useState } from "preact/hooks";

/**
 * useCountUp — animate a number from 0 to `target` over `durationMs`.
 *
 * Used on the dashboard stat strip so the values read as arriving into
 * place rather than blinking in. Paired with the row's staggered
 * entrance animation, the page feels like instruments being turned on
 * one by one instead of a slab of data pasted in.
 *
 * Respects `prefers-reduced-motion` — those users get the final value
 * immediately without any tween. The hook also snaps to target if the
 * component unmounts mid-tween so a late re-render doesn't land on a
 * half-animated value.
 *
 * The interpolation uses ease-out cubic so early frames move fastest
 * (the "arrival" part of the illusion) and the tail slows into place,
 * mirroring how the eye reads natural motion.
 */
export function useCountUp(
  target: number,
  durationMs = 700,
  decimals = 0
): string {
  const [value, setValue] = useState(target);
  const prefersReducedMotion = useRef(
    typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );

  useEffect(() => {
    if (prefersReducedMotion.current || !Number.isFinite(target)) {
      setValue(target);
      return;
    }
    // Guard: if target is 0, nothing to count up. Just render 0 so the
    // empty state doesn't animate (cleaner than "0.0 → 0.0" tween).
    if (target === 0) {
      setValue(0);
      return;
    }

    let rafId = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const elapsed = now - start;
      const t = Math.min(1, elapsed / durationMs);
      // Ease-out cubic — matches the design-system --ease-out Bezier.
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(target * eased);
      if (t < 1) {
        rafId = requestAnimationFrame(tick);
      } else {
        setValue(target);
      }
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [target, durationMs]);

  return value.toFixed(decimals);
}
