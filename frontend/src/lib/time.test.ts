import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { formatRelativeTime, parseIsoAsUtc } from "./time";

/**
 * Direct coverage for the shared `lib/time.ts` helpers. The existing
 * `tests/session/timer-ring-iso-parsing.test.ts` exercises a parser via the
 * TimerRing component; this file covers the `lib/time.ts` exports themselves,
 * and is the only coverage for `formatRelativeTime` and its branch table.
 */

const NOW = Date.UTC(2026, 5, 1, 12, 0, 0); // fixed "now" for deterministic relative-time

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

// --- parseIsoAsUtc ---

test("parseIsoAsUtc: null and undefined return NaN", () => {
  expect(parseIsoAsUtc(null)).toBeNaN();
  expect(parseIsoAsUtc(undefined)).toBeNaN();
});

test("parseIsoAsUtc: Z-marked and +offset strings parse to the same UTC instant", () => {
  expect(parseIsoAsUtc("2026-04-22T17:00:00Z")).toBe(Date.UTC(2026, 3, 22, 17, 0, 0));
  expect(parseIsoAsUtc("2026-04-22T19:00:00+02:00")).toBe(Date.UTC(2026, 3, 22, 17, 0, 0));
});

test("parseIsoAsUtc: a naive string (no timezone) is treated as UTC", () => {
  // Caveat: distinguishing UTC-interpretation from local-interpretation requires the
  // test process not to run in UTC; under TZ=UTC the two coincide. A full guard would
  // pin vitest's TZ in config, which is out of scope for this util test.
  expect(parseIsoAsUtc("2026-04-22T17:00:00")).toBe(Date.UTC(2026, 3, 22, 17, 0, 0));
});

// --- formatRelativeTime ---

const isoAgo = (ms: number) => new Date(NOW - ms).toISOString();

test("formatRelativeTime: null / undefined / unparseable return 'Never'", () => {
  expect(formatRelativeTime(null)).toBe("Never");
  expect(formatRelativeTime(undefined)).toBe("Never");
  expect(formatRelativeTime("not a date")).toBe("Never");
});

test("formatRelativeTime: under 90 seconds is 'just now'", () => {
  expect(formatRelativeTime(isoAgo(30_000))).toBe("just now");
});

test("formatRelativeTime: minutes, hours, and days branches", () => {
  expect(formatRelativeTime(isoAgo(5 * 60_000))).toBe("5m ago");
  expect(formatRelativeTime(isoAgo(3 * 60 * 60_000))).toBe("3h ago");
  expect(formatRelativeTime(isoAgo(2 * 24 * 60 * 60_000))).toBe("2d ago");
});

test("formatRelativeTime: threshold boundaries", () => {
  expect(formatRelativeTime(isoAgo(89_000))).toBe("just now"); // just under 90s
  expect(formatRelativeTime(isoAgo(23 * 60 * 60_000))).toBe("23h ago"); // just under a day
  expect(formatRelativeTime(isoAgo(25 * 60 * 60_000))).toBe("1d ago"); // just over a day
});

test("formatRelativeTime: older than 30 days returns a formatted date, not a relative string", () => {
  // Fixed Z-marked input (40 days before NOW) and a fixed Date.UTC oracle, so this
  // does not route its expected value through parseIsoAsUtc; a consistently-wrong
  // parser cannot pass here.
  const out = formatRelativeTime("2026-03-22T12:00:00Z");
  expect(out).not.toContain("ago");
  expect(out).toBe(new Date(Date.UTC(2026, 2, 22, 12, 0, 0)).toLocaleString(undefined, { month: "short", day: "numeric" }));
});

test("formatRelativeTime: a future timestamp is clamped to 'just now'", () => {
  expect(formatRelativeTime(new Date(NOW + 60 * 60_000).toISOString())).toBe("just now");
});
