# Forge dogfood queue

## T-DF1 — Add unit-test coverage for frontend/src/lib/time.ts
- Status: done
- Deps: none
- Acceptance: a new `frontend/src/lib/time.test.ts` covers
  - `parseIsoAsUtc`: null/undefined returns NaN; a `Z`-marked string parses as UTC; a
    `+HH:MM` offset string parses correctly; a naive string (no tz) is treated as UTC.
  - `formatRelativeTime`: null/unparseable returns "Never"; under 90s returns "just now";
    minutes, hours, and days branches; a timestamp older than 30 days returns a formatted
    date; a future timestamp is clamped to "just now" (the `Math.max(0, ...)` guard).
  Test passes under vitest. `time.ts` is byte-unchanged.

## T-DF2 — Add unit-test coverage for frontend/src/lib/query.ts (createQuery)
- Status: done
- Deps: none
- Acceptance: a new `frontend/src/lib/query.test.ts` covers `createQuery`:
  - initial state: `data` undefined, `loading` false, `error` null.
  - subscribed refetch success: while in flight `loading` is true; after resolve `data`
    holds the result, `loading` false, `error` null.
  - subscribed refetch error: a rejecting fetcher sets `error`, `loading` false, and leaves
    `data` undefined.
  - stale-response generation guard: with a subscriber, start refetch A, then refetch B before
    A resolves; resolving A after B must NOT overwrite B's result (the `generation` check).
  - reset cancels in-flight: a refetch resolving after `reset()` is dropped, and reset clears
    `data`/`loading`/`error`.
  - unsubscribed drop: a refetch with zero active subscribers leaves `data` undefined.
  Test passes under vitest. `query.ts` is byte-unchanged.
