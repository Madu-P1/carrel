/**
 * FLIP (First, Last, Invert, Play) utility for signature motion moments.
 *
 * Use case: a source element is about to disappear (or has disappeared), and
 * a target element is about to appear. We want the appearance to look like the
 * source morphed into the target, not like it popped in from nowhere.
 *
 * Approach:
 *   1. Capture the source element's rect BEFORE navigation (in the caller).
 *   2. After the target element mounts, call `flipFromRect(target, sourceRect)`.
 *   3. The target animates from the source's position/size to its natural
 *      position/size using transform (no layout thrash, GPU-compositor lane).
 *
 * Respects prefers-reduced-motion by collapsing the animation to duration:0.
 * No layout-triggering properties; transforms and opacity only.
 *
 * Signature moments using this utility, per DESIGN.md:
 *   - SM-1: Document card (Library) → Reader title bar
 *   - SM-2: Citation chip (Ask) → Reader chunk (ghost variant, see ghostFlight)
 */

export interface FlipOptions {
  /** Animation duration in ms. Defaults to 320 (matches DESIGN.md SM-1 budget). */
  durationMs?: number;
  /** CSS easing. Defaults to --ease-swift per DESIGN.md Tier 3. */
  easing?: string;
  /** Skip opacity fade (default true — source and target are visible). */
  fadeOpacity?: boolean;
  /** Called when the animation finishes (natural end or cancel). */
  onFinish?: () => void;
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

/**
 * Animate `target` from `sourceRect` to its current bounding rect using FLIP.
 * Returns the Animation object so the caller can cancel or await it.
 *
 * The target element must already be mounted and laid out at its final position.
 * This function only applies a transient transform override — it does not move
 * the element in the DOM.
 */
export function flipFromRect(
  target: HTMLElement,
  sourceRect: DOMRect,
  options: FlipOptions = {},
): Animation | null {
  const {
    durationMs = 320,
    easing = "cubic-bezier(0.4, 0, 0.2, 1)",
    fadeOpacity = false,
    onFinish,
  } = options;

  if (prefersReducedMotion()) {
    onFinish?.();
    return null;
  }

  const targetRect = target.getBoundingClientRect();
  if (targetRect.width === 0 || targetRect.height === 0) {
    onFinish?.();
    return null;
  }

  const dx = sourceRect.left - targetRect.left;
  const dy = sourceRect.top - targetRect.top;
  const sx = sourceRect.width === 0 ? 1 : sourceRect.width / targetRect.width;
  const sy = sourceRect.height === 0 ? 1 : sourceRect.height / targetRect.height;

  // If source and target are effectively the same rect, no animation needed.
  const tolerancePx = 2;
  if (
    Math.abs(dx) < tolerancePx
    && Math.abs(dy) < tolerancePx
    && Math.abs(sx - 1) < 0.02
    && Math.abs(sy - 1) < 0.02
  ) {
    onFinish?.();
    return null;
  }

  const keyframes: Keyframe[] = [
    {
      transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`,
      transformOrigin: "top left",
      ...(fadeOpacity ? { opacity: 0.7 } : {}),
    },
    {
      transform: "translate(0, 0) scale(1, 1)",
      transformOrigin: "top left",
      ...(fadeOpacity ? { opacity: 1 } : {}),
    },
  ];

  const animation = target.animate(keyframes, {
    duration: durationMs,
    easing,
    fill: "none",
  });

  animation.addEventListener("finish", () => onFinish?.(), { once: true });
  animation.addEventListener("cancel", () => onFinish?.(), { once: true });
  return animation;
}

/**
 * Spawn a ghost copy of a source element at its captured rect, animate it to
 * land on a target element, then remove the ghost.
 *
 * Used for SM-2 (citation chip → reader chunk): the source chip is not the
 * element that survives the navigation — it's being left behind in a route
 * that's unmounting. So we clone it and fly the clone to the target's rect.
 *
 * The ghost is position:fixed on document.body. It does not participate in
 * Preact's render tree.
 */
export interface GhostFlightOptions extends FlipOptions {
  /** Optional CSS class list applied to the ghost node. */
  ghostClassName?: string;
}

export function ghostFlight(
  sourceHtml: string,
  sourceRect: DOMRect,
  target: HTMLElement,
  options: GhostFlightOptions = {},
): Animation | null {
  const {
    durationMs = 420,
    easing = "cubic-bezier(0.4, 0, 0.2, 1)",
    ghostClassName,
    onFinish,
  } = options;

  if (prefersReducedMotion()) {
    onFinish?.();
    return null;
  }

  const targetRect = target.getBoundingClientRect();
  if (targetRect.width === 0 || targetRect.height === 0) {
    onFinish?.();
    return null;
  }

  const ghost = document.createElement("div");
  ghost.innerHTML = sourceHtml;
  if (ghostClassName) {
    ghost.className = ghostClassName;
  }

  // Hard-set position to the source rect in viewport coordinates.
  Object.assign(ghost.style, {
    position: "fixed",
    top: `${sourceRect.top}px`,
    left: `${sourceRect.left}px`,
    width: `${sourceRect.width}px`,
    height: `${sourceRect.height}px`,
    margin: "0",
    pointerEvents: "none",
    zIndex: "9999",
    transformOrigin: "top left",
  } as CSSStyleDeclaration);

  document.body.appendChild(ghost);

  const dx = targetRect.left - sourceRect.left;
  const dy = targetRect.top - sourceRect.top;
  const sx = targetRect.width / sourceRect.width;
  const sy = targetRect.height / sourceRect.height;

  const keyframes: Keyframe[] = [
    { transform: "translate(0, 0) scale(1, 1)", opacity: 1 },
    {
      transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`,
      opacity: 0.15,
    },
  ];

  const animation = ghost.animate(keyframes, {
    duration: durationMs,
    easing,
    fill: "forwards",
  });

  const cleanup = () => {
    ghost.remove();
    onFinish?.();
  };
  animation.addEventListener("finish", cleanup, { once: true });
  animation.addEventListener("cancel", cleanup, { once: true });
  return animation;
}
