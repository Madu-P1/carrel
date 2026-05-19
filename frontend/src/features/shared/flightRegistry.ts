/**
 * Cross-feature rect handoff for signature motion moments.
 *
 * Feature A captures an element's bounding rect before navigating away.
 * Feature B (after navigation) consumes the rect and runs FLIP from it.
 *
 * Used for:
 *   - SM-1 (DocumentRow click → Reader title bar morph)
 *   - SM-2 (CitationChip click → Reader chunk ghost-flight)
 *
 * Entries auto-expire after FRESHNESS_MS to avoid stale flights playing on
 * later navigation. If the target mounts too slowly (slow network), the
 * flight is silently skipped rather than playing against outdated geometry.
 *
 * This is a module-level singleton. There's never more than one pending
 * flight per kind+id, and the registry clears on consume.
 */

export type FlightKind = "doc-card" | "citation-chip";

export interface FlightEntry {
  kind: FlightKind;
  id: string;
  rect: DOMRect;
  /** For citation chips: outerHTML of the source chip so we can ghost it. */
  html?: string;
  /** For citation chips: the target doc's id, to scope SM-2 to the right reader. */
  docId?: string;
  /** For citation chips: the target node id inside the doc (str-coerced;
   *  on the chunks branch it carries the legacy chunk UUID). */
  nodeId?: string;
  timestamp: number;
}

const FRESHNESS_MS = 2000;

let current: FlightEntry | null = null;

export function registerFlight(entry: Omit<FlightEntry, "timestamp">): void {
  current = { ...entry, timestamp: Date.now() };
}

export function peekFlight(kind: FlightKind, id: string): FlightEntry | null {
  if (!current) return null;
  if (current.kind !== kind || current.id !== id) return null;
  if (Date.now() - current.timestamp > FRESHNESS_MS) {
    current = null;
    return null;
  }
  return current;
}

export function consumeFlight(kind: FlightKind, id: string): FlightEntry | null {
  const entry = peekFlight(kind, id);
  if (entry) {
    current = null;
  }
  return entry;
}

export function clearFlight(): void {
  current = null;
}

/** Test-only helper. Do not use in production code paths. */
export function _currentFlight(): FlightEntry | null {
  return current;
}
