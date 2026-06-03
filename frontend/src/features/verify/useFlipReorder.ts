import { useLayoutEffect, useRef } from "preact/hooks";

/**
 * SM-V2 The Read: FLIP reorder for the streaming verdict list.
 *
 * As each citation check lands the list re-sorts (flags rise toward the top).
 * This animates the position change so the eye follows real work down the page,
 * the way a clerk works through a document. Transform only, 120ms, via WAAPI so
 * no CSS keyframe is added and the verifyScope motion guard still holds.
 *
 * Children must carry a stable `data-flip-key` so the same node is tracked
 * across reorders (the parent must key by a stable id, not the array index).
 * Skipped under prefers-reduced-motion and where layout/animate are unavailable
 * (jsdom), so it is inert and safe in tests.
 *
 * Returns a ref to attach to the list container.
 */
export function useFlipReorder<T extends HTMLElement>() {
  const containerRef = useRef<T | null>(null);
  const previousRects = useRef<Map<string, DOMRect>>(new Map());

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const nodes = Array.from(container.querySelectorAll<HTMLElement>("[data-flip-key]"));
    const nextRects = new Map<string, DOMRect>();

    for (const node of nodes) {
      const key = node.dataset.flipKey;
      if (!key) continue;
      const rect = node.getBoundingClientRect();
      nextRects.set(key, rect);

      const previous = previousRects.current.get(key);
      if (!previous || reduce || typeof node.animate !== "function") continue;
      const dx = previous.left - rect.left;
      const dy = previous.top - rect.top;
      if (dx === 0 && dy === 0) continue;

      node.animate(
        [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "translate(0, 0)" }],
        { duration: 120, easing: "ease-out" }
      );
    }

    previousRects.current = nextRects;
  });

  return containerRef;
}
