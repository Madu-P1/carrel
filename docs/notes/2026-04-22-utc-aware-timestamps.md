# Serialize timestamps as UTC-aware ISO strings

**Date:** 2026-04-22
**Scope:** every Python call site that returns a timestamp to the frontend.
**Rule:** use `datetime.now(timezone.utc).isoformat()`, never `datetime.utcnow().isoformat()`.

## The bug this prevents

A pomodoro timer that renders `00:00 OVERTIME` the moment a session starts.

## Why

`datetime.utcnow()` returns a naive `datetime` (no `tzinfo`). Its
`.isoformat()` output looks like `2026-04-22T17:46:22.905367` — no `Z`,
no `+00:00`.

JavaScript's `Date.parse()` reads a naive ISO string as **local time**,
not UTC. So:

- Backend records a session `started_at = "2026-04-22T17:46:22"` (meant to
  be UTC)
- User in UTC+2 opens `/session`; browser parses `"2026-04-22T17:46:22"`
  as local time → 15:46 UTC → 2 hours before actual wall clock
- Pomodoro timer computes `(now - startedMs) / 1000` ≈ 2 hours elapsed
  → `00:00 OVERTIME` on a 60-minute session

The fix is boring and total: always emit explicit UTC offsets.

## The pattern

**Don't do this:**
```python
from datetime import datetime
datetime.utcnow().isoformat()  # naive — Date.parse() breaks
```

**Do this:**
```python
from datetime import datetime, timezone
datetime.now(timezone.utc).isoformat()  # "2026-04-22T17:46:22+00:00"
```

## Defense in depth on the client

`frontend/src/lib/time.ts::parseIsoAsUtc` exists as a belt-and-braces
guard — any ISO string without a timezone marker gets `Z` appended before
parsing. This means an old server, a cached response, or a future
regression can't silently corrupt the timer. Consumers: `TimerRing`,
`ActiveSessionCard`, `SubjectCardGrid` via `formatRelativeTime`.

If you add a component that parses a server timestamp, import from
`@/lib/time` instead of calling `Date.parse` directly.

## Tests guarding this

- **Backend regression:** `tests/test_dashboard_session.py`
  `::test_started_at_includes_utc_timezone_marker` — asserts `started_at`
  matches the `[+-]\d{2}:\d{2}$` regex.
- **Frontend regression:** `frontend/tests/session/timer-ring-iso-parsing.test.ts`
  — seven cases covering `Z`, `+HH:MM`, naive strings, and empty input.

Both must pass on every release. If either starts failing, the timer UX
is already broken for any non-UTC user.
