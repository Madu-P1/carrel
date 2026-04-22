import { useEffect, useRef } from "preact/hooks";

import { consumeFlight } from "@/features/shared/flightRegistry";
import { flipFromRect } from "@/lib/flip";

/**
 * SM-1: Document card → Reader title bar morph.
 *
 * Consumes a "doc-card" flight entry (registered by Library's DocumentRow on
 * click) and runs FLIP on the Reader header element so the new route appears
 * to morph from where the user clicked.
 *
 * Returns a ref to attach to the target header. No-op if no flight was
 * registered, if the entry is stale, or if prefers-reduced-motion is set.
 */
export function useCardFlight<T extends HTMLElement>(docId: string) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const target = ref.current;
    if (!target) return;

    const flight = consumeFlight("doc-card", docId);
    if (!flight) return;

    // Defer to the next frame so the target has laid out at its final rect.
    const raf = requestAnimationFrame(() => {
      flipFromRect(target, flight.rect, {
        durationMs: 320,
        easing: "cubic-bezier(0.4, 0, 0.2, 1)",
        fadeOpacity: true,
      });
    });

    return () => cancelAnimationFrame(raf);
  }, [docId]);

  return ref;
}
