import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import {
  _currentFlight,
  clearFlight,
  consumeFlight,
  peekFlight,
  registerFlight,
} from "@/features/shared/flightRegistry";

function makeRect(x = 0, y = 0, w = 10, h = 10): DOMRect {
  return { x, y, width: w, height: h, top: y, left: x, right: x + w, bottom: y + h, toJSON: () => ({}) } as DOMRect;
}

describe("flightRegistry", () => {
  beforeEach(() => {
    clearFlight();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  test("register + peek returns the same entry without consuming", () => {
    const rect = makeRect(5, 5, 40, 20);
    registerFlight({ kind: "doc-card", id: "doc-1", rect });
    expect(peekFlight("doc-card", "doc-1")).not.toBeNull();
    // Peek twice — still there (not consumed).
    expect(peekFlight("doc-card", "doc-1")).not.toBeNull();
    expect(_currentFlight()).not.toBeNull();
  });

  test("consume returns the entry and clears it", () => {
    const rect = makeRect();
    registerFlight({ kind: "doc-card", id: "doc-1", rect });
    const flight = consumeFlight("doc-card", "doc-1");
    expect(flight).not.toBeNull();
    expect(flight?.kind).toBe("doc-card");
    expect(_currentFlight()).toBeNull();
    // Second consume is null.
    expect(consumeFlight("doc-card", "doc-1")).toBeNull();
  });

  test("wrong kind / id does not match", () => {
    registerFlight({ kind: "doc-card", id: "doc-1", rect: makeRect() });
    expect(peekFlight("citation-chip", "doc-1")).toBeNull();
    expect(peekFlight("doc-card", "doc-2")).toBeNull();
    // Original entry is still there untouched.
    expect(_currentFlight()).not.toBeNull();
  });

  test("stale entries (> 2000 ms) are rejected and cleared", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(0));
    registerFlight({ kind: "doc-card", id: "doc-1", rect: makeRect() });
    // 1900 ms later — still fresh.
    vi.setSystemTime(new Date(1900));
    expect(peekFlight("doc-card", "doc-1")).not.toBeNull();
    // 2100 ms later — stale.
    vi.setSystemTime(new Date(2100));
    expect(peekFlight("doc-card", "doc-1")).toBeNull();
    // And the stale check clears it.
    expect(_currentFlight()).toBeNull();
  });

  test("re-registering overwrites the previous entry", () => {
    const rectA = makeRect(0, 0, 10, 10);
    const rectB = makeRect(100, 100, 20, 20);
    registerFlight({ kind: "doc-card", id: "doc-1", rect: rectA });
    registerFlight({ kind: "doc-card", id: "doc-2", rect: rectB });
    expect(peekFlight("doc-card", "doc-1")).toBeNull();
    expect(peekFlight("doc-card", "doc-2")?.rect.left).toBe(100);
  });

  test("citation-chip entries carry html + docId + chunkId", () => {
    registerFlight({
      kind: "citation-chip",
      id: "chunk-9",
      rect: makeRect(),
      html: "<button>cite</button>",
      docId: "doc-3",
      chunkId: "chunk-9",
    });
    const flight = peekFlight("citation-chip", "chunk-9");
    expect(flight?.html).toBe("<button>cite</button>");
    expect(flight?.docId).toBe("doc-3");
    expect(flight?.chunkId).toBe("chunk-9");
  });
});
