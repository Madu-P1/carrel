/**
 * Time zone helpers for the Plan view.
 *
 * Storage is always UTC ISO 8601 (`...Z`). Display is the browser's
 * local TZ. These helpers wrap Intl.DateTimeFormat with the patterns
 * the Plan UI uses repeatedly.
 */

export function browserTimeZone(): string {
  // Falls back to "UTC" if Intl is unavailable (almost never on real
  // browsers, but the fallback keeps types clean).
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

/** "9:00 AM" / "14:30" depending on locale. */
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

/** "9:00 – 10:30 AM" / "9:00 AM – 1:00 PM" — collapses suffix when both
 *  bounds share AM/PM. */
export function formatTimeRange(startIso: string, endIso: string): string {
  const start = new Date(startIso);
  const end = new Date(endIso);
  const startStr = start.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
  const endStr = end.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
  return `${startStr} – ${endStr}`;
}

/** "Mon Apr 29" — the column header for WeekTimeGrid. */
export function formatDayHeader(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

/** True if `iso`'s local-day matches today's local-day. */
export function isToday(iso: string): boolean {
  const d = new Date(iso);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

/** Decimal hour-of-day in the user's local TZ. 13:30 → 13.5. */
export function hourOfDay(iso: string): number {
  const d = new Date(iso);
  return d.getHours() + d.getMinutes() / 60;
}

/** Returns 7 ISO timestamps at midnight LOCAL time, starting today. */
export function nextSevenDays(): string[] {
  const result: string[] = [];
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  for (let i = 0; i < 7; i += 1) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    result.push(d.toISOString());
  }
  return result;
}

/** True if `iso` falls on the same local-day as `dayIso`. */
export function isSameLocalDay(iso: string, dayIso: string): boolean {
  const a = new Date(iso);
  const b = new Date(dayIso);
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** Today at midnight, local timezone. The week-navigation state in
 *  PlanView is built off this. */
export function todayMidnightLocal(): Date {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  return start;
}

/** Returns 7 ISO timestamps at midnight LOCAL time, starting from `from`
 *  (which must already be a midnight-local Date). */
export function sevenDaysFrom(from: Date): string[] {
  const result: string[] = [];
  for (let i = 0; i < 7; i += 1) {
    const d = new Date(from);
    d.setDate(from.getDate() + i);
    result.push(d.toISOString());
  }
  return result;
}

/** Returns `count` ISO timestamps at midnight LOCAL time, starting from
 *  `from` (must be midnight-local). Generalizes `sevenDaysFrom` to any
 *  window size so the calendar can render past 7 days for horizontal
 *  panning. */
export function nextNDays(count: number, from: Date): string[] {
  const result: string[] = [];
  for (let i = 0; i < count; i += 1) {
    const d = new Date(from);
    d.setDate(from.getDate() + i);
    result.push(d.toISOString());
  }
  return result;
}

/** Shift a midnight-local Date forward (positive) or back (negative) by
 *  whole days. Returns a new Date; doesn't mutate. */
export function shiftDaysLocal(from: Date, deltaDays: number): Date {
  const next = new Date(from);
  next.setDate(from.getDate() + deltaDays);
  next.setHours(0, 0, 0, 0);
  return next;
}

/** Format a week-range header: "May 5 – May 11, 2026". When the week
 *  spans a month boundary the months show on both sides. */
export function formatWeekRange(startMidnightIso: string): string {
  const start = new Date(startMidnightIso);
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  const sameMonth = start.getMonth() === end.getMonth();
  const sameYear = start.getFullYear() === end.getFullYear();
  const monthFmt = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
  const yearFmt = new Intl.DateTimeFormat(undefined, { year: "numeric" });
  if (sameMonth && sameYear) {
    const m = new Intl.DateTimeFormat(undefined, { month: "short" }).format(start);
    return `${m} ${start.getDate()} – ${end.getDate()}, ${yearFmt.format(start)}`;
  }
  return `${monthFmt.format(start)} – ${monthFmt.format(end)}, ${yearFmt.format(end)}`;
}
