/**
 * Time utilities — shared across views that display server timestamps.
 *
 * The backend writes some timestamps as naive UTC (SQLite's CURRENT_TIMESTAMP,
 * and until recently, `datetime.utcnow().isoformat()` in the Python code).
 * A naive ISO string like `"2026-04-22T17:46:22"` has NO timezone marker.
 * JavaScript's `Date.parse()` then interprets it as LOCAL time, which is
 * wrong for a server-side UTC value — users outside UTC see timestamps
 * drift by their offset (a user in UTC+2 saw new sessions open at "2h
 * elapsed" and pomodoro timers go straight to OVERTIME).
 *
 * The backend is being converted to emit UTC-marked strings
 * (`datetime.now(timezone.utc).isoformat()`, which produces `+00:00`).
 * This helper bridges both worlds: marked strings parse as-is, naive
 * strings are treated as UTC. Defense-in-depth against old servers,
 * cached responses, and future regressions.
 *
 * Tests: frontend/tests/session/timer-ring-iso-parsing.test.ts
 * Companion backend regression: tests/test_dashboard_session.py
 *   ::test_started_at_includes_utc_timezone_marker
 */
export function parseIsoAsUtc(iso: string | null | undefined): number {
  if (!iso) return Number.NaN;
  // Match Z or Zulu, or a trailing ±HH:MM / ±HHMM offset.
  const hasTimezone = /[Zz]$|[+-]\d{2}:?\d{2}$/.test(iso);
  const normalized = hasTimezone ? iso : `${iso}Z`;
  return Date.parse(normalized);
}

/**
 * Render a relative time string like "2h ago", "3d ago", or a date for
 * older timestamps. Null / unparseable input returns "Never" so the UI
 * always has something to show.
 */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "Never";
  const ts = parseIsoAsUtc(iso);
  if (!Number.isFinite(ts)) return "Never";
  const now = Date.now();
  const deltaSec = Math.max(0, Math.round((now - ts) / 1000));
  if (deltaSec < 90) return "just now";
  if (deltaSec < 60 * 60) return `${Math.round(deltaSec / 60)}m ago`;
  if (deltaSec < 60 * 60 * 24) return `${Math.round(deltaSec / 3600)}h ago`;
  if (deltaSec < 60 * 60 * 24 * 30) {
    return `${Math.round(deltaSec / 86400)}d ago`;
  }
  const date = new Date(ts);
  return date.toLocaleString(undefined, { month: "short", day: "numeric" });
}
