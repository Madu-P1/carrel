import { describe, expect, test } from "vitest";

import {
  formatTimeRange,
  hourOfDay,
  isSameLocalDay,
  isToday,
  nextSevenDays,
} from "../../src/features/plan/utils/timezone";

/**
 * The Plan view leans on these helpers for grid placement (hourOfDay)
 * and date column grouping (isSameLocalDay, isToday). Pin them so the
 * grid math doesn't drift.
 */

describe("nextSevenDays", () => {
  test("returns exactly 7 ISO strings", () => {
    const days = nextSevenDays();
    expect(days).toHaveLength(7);
    days.forEach((iso) => {
      expect(typeof iso).toBe("string");
      expect(() => new Date(iso)).not.toThrow();
    });
  });

  test("first entry is today's local-day at 00:00", () => {
    const [first] = nextSevenDays();
    const d = new Date(first!);
    expect(d.getHours()).toBe(0);
    expect(d.getMinutes()).toBe(0);
    expect(d.getSeconds()).toBe(0);
  });
});

describe("hourOfDay", () => {
  test("returns decimal hour-of-day in local TZ", () => {
    // 13:30 local → 13.5
    const localNoonThirty = new Date();
    localNoonThirty.setHours(13, 30, 0, 0);
    const result = hourOfDay(localNoonThirty.toISOString());
    expect(result).toBeCloseTo(13.5, 5);
  });
});

describe("isSameLocalDay", () => {
  test("true when both ISO strings fall on the same local-day", () => {
    const morning = new Date();
    morning.setHours(9, 0, 0, 0);
    const evening = new Date();
    evening.setHours(20, 0, 0, 0);
    expect(isSameLocalDay(morning.toISOString(), evening.toISOString())).toBe(true);
  });

  test("false across day boundary", () => {
    const today = new Date();
    today.setHours(12, 0, 0, 0);
    const tomorrow = new Date(today);
    tomorrow.setDate(today.getDate() + 1);
    expect(isSameLocalDay(today.toISOString(), tomorrow.toISOString())).toBe(false);
  });
});

describe("isToday", () => {
  test("true for the current local-day", () => {
    expect(isToday(new Date().toISOString())).toBe(true);
  });

  test("false for tomorrow", () => {
    const t = new Date();
    t.setDate(t.getDate() + 1);
    expect(isToday(t.toISOString())).toBe(false);
  });
});

describe("formatTimeRange", () => {
  test("returns a non-empty string with both bounds", () => {
    const start = new Date();
    start.setHours(9, 0, 0, 0);
    const end = new Date(start);
    end.setHours(10, 30);
    const result = formatTimeRange(start.toISOString(), end.toISOString());
    expect(result.length).toBeGreaterThan(0);
    // Locale-dependent format; just check the en-dash is present.
    expect(result).toContain("–");
  });
});
