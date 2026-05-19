import { useEffect } from "preact/hooks";

import { consumeFlight } from "@/features/shared/flightRegistry";
import { ghostFlight } from "@/lib/flip";

/**
 * SM-2: Citation chip → Reader chunk ghost-flight + target pulse.
 *
 * Consumes a "citation-chip" flight entry (registered by Ask's CitationChip on
 * click) and:
 *   1. Spawns a ghost chip at the captured source rect.
 *   2. Flies the ghost to the target chunk's current bounding rect.
 *   3. On landing, applies `.anim-pulseOnce` to the target chunk.
 *
 * Must run AFTER the deep-link scroll settles (useChunkDeepLink handles the
 * scroll). We wait for a single paint frame after the chunk id shows up in the
 * DOM before measuring the target rect.
 */
export function useCitationFlight(docId: string | null, nodeId: string | null | undefined) {
  useEffect(() => {
    if (!docId || !nodeId) return;

    const flight = consumeFlight("citation-chip", nodeId);
    if (!flight || flight.docId !== docId || !flight.html) return;

    // Poll briefly for the target chunk element — the Reader may still be
    // scrolling to it after useChunkDeepLink updated highlightedChunkId.
    // T06 keeps the DOM target on `data-chunk-id` because the reader still
    // renders chunks pre-Phase-4; on the chunks branch `nodeId` is a chunk
    // UUID and matches. On the nodes branch the int won't match and the
    // ghost-flight degrades silently — `useNodeDeepLink` still navigates.
    const startedAt = performance.now();
    let cancelled = false;
    // jsdom does not expose the global CSS interface. Fall back to a minimal
    // attribute-value escape that covers quotes + backslashes. Our chunk ids
    // are server UUIDs, so this escape is mostly belt-and-braces.
    const escapeAttr = (value: string) =>
      typeof CSS !== "undefined" && typeof CSS.escape === "function"
        ? CSS.escape(value)
        : value.replace(/["\\]/g, "\\$&");
    const poll = () => {
      if (cancelled) return;
      const target = document.querySelector<HTMLElement>(`[data-chunk-id="${escapeAttr(nodeId)}"]`);
      if (target && target.getBoundingClientRect().height > 0) {
        ghostFlight(flight.html!, flight.rect, target, {
          durationMs: 420,
          easing: "cubic-bezier(0.4, 0, 0.2, 1)",
          onFinish: () => {
            // Apply pulseOnce on the landing target.
            target.classList.add("anim-pulseOnce");
            const cleanup = () => target.classList.remove("anim-pulseOnce");
            target.addEventListener("animationend", cleanup, { once: true });
            // Safety: always remove after the pulse duration.
            window.setTimeout(cleanup, 900);
          },
        });
        return;
      }
      if (performance.now() - startedAt < 800) {
        requestAnimationFrame(poll);
      }
    };
    requestAnimationFrame(poll);

    return () => {
      cancelled = true;
    };
  }, [docId, nodeId]);
}
