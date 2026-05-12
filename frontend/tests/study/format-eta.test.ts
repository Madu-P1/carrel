import { describe, expect, test } from "vitest";

import { formatEta } from "@/features/study/StudyView";

/*
 * PR 6.1 — format-eta unit tests.
 *
 * The estimator drives the focus-mode "~Nm left" chip. The contract:
 *   - Hidden (returns null) until at least 3 sample cards are rated.
 *   - Hidden when no cards remain.
 *   - Sub-minute renders as "~Ns left" with a 5s floor so the chip
 *     never reads "~0s left" right before the session ends.
 *   - Minute-or-more renders as "~Nm left" rounded UP, so the chip
 *     never under-promises a finish line that hasn't arrived.
 *   - Median, not mean — one anomalous slow card doesn't wreck the
 *     estimate. Two fast cards plus one outlier should still read as
 *     "fast" remaining time.
 */

describe("formatEta (PR 6.1)", () => {
  test("returns null with fewer than 3 samples", () => {
    expect(formatEta([], 5)).toBeNull();
    expect(formatEta([10], 5)).toBeNull();
    expect(formatEta([10, 12], 5)).toBeNull();
  });

  test("returns null when no cards remain", () => {
    expect(formatEta([10, 11, 12], 0)).toBeNull();
    expect(formatEta([10, 11, 12], -1)).toBeNull();
  });

  test("renders sub-minute totals in seconds with a 5s floor", () => {
    // Median 10s × 1 remaining = 10s.
    expect(formatEta([10, 10, 10], 1)).toBe("~10s left");
    // Median 1s × 1 remaining = 1s; floors to 5s for visibility.
    expect(formatEta([1, 1, 1], 1)).toBe("~5s left");
  });

  test("renders >=60s totals in minutes, rounded up", () => {
    // Median 30s × 4 remaining = 120s = 2m exact.
    expect(formatEta([30, 30, 30], 4)).toBe("~2m left");
    // Median 30s × 5 remaining = 150s = 2.5m → rounds UP to 3m.
    expect(formatEta([30, 30, 30], 5)).toBe("~3m left");
    // Median 1s × 60 remaining = 60s = 1m exact, displayed in minutes.
    expect(formatEta([1, 1, 1], 60)).toBe("~1m left");
  });

  test("uses median, not mean, so one outlier doesn't dominate", () => {
    // [5, 5, 60] — median 5, mean ~23. Median × 4 = 20s, not 92s.
    expect(formatEta([5, 5, 60], 4)).toBe("~20s left");
  });

  test("median over even sample counts averages the middle two", () => {
    // Sorted: [10, 20, 30, 40] → median (20+30)/2 = 25.
    // 25 × 4 = 100s → ceil(100/60) = 2 minutes.
    expect(formatEta([40, 10, 30, 20], 4)).toBe("~2m left");
  });
});
