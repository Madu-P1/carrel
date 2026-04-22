import { expect, test } from "vitest";

import { parseIsoAsUtc } from "../../src/features/session/components/TimerRing";

/**
 * Regression: ISO strings without a timezone marker must be parsed AS UTC,
 * not as local time. The backend had a bug where `datetime.utcnow().isoformat()`
 * dropped the `Z` suffix, which made the frontend compute elapsed time
 * relative to the user's local timezone — a user in UTC+2 saw every new
 * session open at "2 hours elapsed" and the timer went straight to OVERTIME.
 *
 * Even though the backend is fixed, this parser keeps defense-in-depth
 * because: (a) an old/cached server response might still be naive, and
 * (b) a future regression anywhere in the stack shouldn't corrupt user-
 * facing time calculations.
 */

test("parses ISO with Z suffix as UTC", () => {
  const ts = parseIsoAsUtc("2026-04-22T17:00:00Z");
  // 2026-04-22T17:00:00Z expressed as ms since epoch
  expect(ts).toBe(Date.UTC(2026, 3, 22, 17, 0, 0));
});

test("parses ISO with +00:00 offset as UTC", () => {
  const ts = parseIsoAsUtc("2026-04-22T17:00:00+00:00");
  expect(ts).toBe(Date.UTC(2026, 3, 22, 17, 0, 0));
});

test("parses ISO with +02:00 offset correctly (CEST)", () => {
  const ts = parseIsoAsUtc("2026-04-22T19:00:00+02:00");
  // 19:00 CEST is 17:00 UTC
  expect(ts).toBe(Date.UTC(2026, 3, 22, 17, 0, 0));
});

test("naive ISO string (no timezone) is parsed AS UTC", () => {
  // This is the critical case — the old bug. Naive string should NOT
  // drift with the user's local timezone.
  const ts = parseIsoAsUtc("2026-04-22T17:00:00");
  expect(ts).toBe(Date.UTC(2026, 3, 22, 17, 0, 0));
});

test("naive ISO with microseconds is parsed AS UTC", () => {
  // The exact shape Python's `datetime.utcnow().isoformat()` produced.
  const ts = parseIsoAsUtc("2026-04-22T17:46:22.905367");
  expect(ts).toBe(Date.UTC(2026, 3, 22, 17, 46, 22, 905));
});

test("empty string returns NaN (safe fallback)", () => {
  expect(parseIsoAsUtc("")).toBeNaN();
});

test("a naive and a UTC-marked form of the same moment parse identically", () => {
  const naive = parseIsoAsUtc("2026-04-22T17:00:00");
  const marked = parseIsoAsUtc("2026-04-22T17:00:00Z");
  expect(naive).toBe(marked);
});
