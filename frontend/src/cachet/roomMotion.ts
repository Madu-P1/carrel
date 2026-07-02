/**
 * Room-entry motion for the Cachet shell. One mechanism, used everywhere a
 * surface enters: the route canvas and the command palette.
 *
 * WAAPI on purpose (the seal precedent): the verify surface's near-zero-motion
 * contract bans CSS keyframes in its module, and WAAPI keeps every entrance on
 * one code path that consults prefers-reduced-motion at call time. The motion
 * itself is Tier-1 functional (DESIGN.md): opacity + a small settle on
 * transform, 150-190ms, decelerating. Felt, never watched.
 */

const EASE_OUT = "cubic-bezier(0.22, 1, 0.36, 1)";

function reducedMotion(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/** A room (route content) settling onto the desk: fade + 8px rise. */
export function enterRoom(el: HTMLElement | null): void {
  if (!el || reducedMotion() || typeof el.animate !== "function") return;
  el.animate(
    [
      { opacity: 0, transform: "translateY(8px)" },
      { opacity: 1, transform: "translateY(0)" },
    ],
    { duration: 190, easing: EASE_OUT }
  );
}

/** The palette arriving: fade + a near-imperceptible scale settle (Raycast cadence). */
export function enterPanel(el: HTMLElement | null): void {
  if (!el || reducedMotion() || typeof el.animate !== "function") return;
  el.animate(
    [
      { opacity: 0, transform: "scale(0.985) translateY(-4px)" },
      { opacity: 1, transform: "scale(1) translateY(0)" },
    ],
    { duration: 150, easing: EASE_OUT }
  );
}
