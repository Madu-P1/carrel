import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import type { CalendarFeed } from "../api/calendarApi";
import type { PlanEvent, PlanSuggestion } from "../api/planApi";
import {
  formatDayHeader,
  hourOfDay,
  isSameLocalDay,
  isToday,
  nextNDays,
  todayMidnightLocal,
} from "../utils/timezone";
import { EventBlock } from "./EventBlock";
import { SuggestionCard } from "./SuggestionCard";
import styles from "./WeekTimeGrid.module.css";

/**
 * 7-day timeline view. Day = vertical column. Hours = horizontal rows.
 * Events placed absolutely at their start_at, sized by their duration.
 *
 * Why this over a flat list: the user's job here is finding free time
 * to study. A flat "Mon: class 9-11, class 1-3" list hides the gap
 * between them. The timeline makes "I have a free 2-hour block 11-1"
 * visually obvious — which is exactly what the coach is suggesting.
 *
 * Day window: 7 days starting today (00:00 local). Hour window: full
 * 24 hours, scrollable. On mount we auto-scroll to one hour before
 * the current time so the user lands on a useful default.
 */

// Full 24-hour window so events at any hour (early-morning labs,
// late-night sessions, off-shift study blocks) render at their real
// time of day. The grid is vertically scrollable; on mount we scroll
// to roughly the current hour so most users land on a useful default.
const HOUR_START = 0;
const HOUR_END = 24;
const HOUR_SPAN = HOUR_END - HOUR_START;
/** Pixels per hour. Must match WeekTimeGrid.module.css `--hour-row-h`. */
const HOUR_ROW_HEIGHT_PX = 56;
/** Minimum width per day column, in pixels. Combined with `dayCount`
 *  this determines the rendered width of the grid — when it exceeds
 *  the viewport, the .grid container scrolls horizontally. Keep in
 *  sync with the lower bound in WeekTimeGrid.module.css. */
const DAY_COL_MIN_WIDTH_PX = 180;

interface WeekTimeGridProps {
  events: PlanEvent[];
  suggestions: PlanSuggestion[];
  feeds: CalendarFeed[];
  onAcceptSuggestion: (id: string) => void;
  onDismissSuggestion: (id: string) => void;
  /** Click handler for event blocks; usually opens the detail dialog.
   *  Optional: when omitted, blocks render as static (Phase 1 behavior). */
  onSelectEvent?: (event: PlanEvent) => void;
  /** First day of the rendered week, midnight-local. Default: today.
   *  Drives the rendered window plus the today-highlight comparison. */
  weekStart?: Date;
  /** How many day columns to render. Default 7 (one week). Pass a
   *  larger value (e.g. 14, 28) to enable horizontal panning across
   *  more of the calendar. */
  dayCount?: number;
}

export function WeekTimeGrid({
  events,
  suggestions,
  feeds,
  onAcceptSuggestion,
  onDismissSuggestion,
  onSelectEvent,
  weekStart,
  dayCount = 7,
}: WeekTimeGridProps) {
  const anchor = weekStart ?? todayMidnightLocal();
  // Stable primitive key: Date objects are reference-typed so we key
  // on the epoch ms to avoid triggering memos on every render.
  const anchorMs = anchor.getTime();
  const days = useMemo(() => nextNDays(dayCount, anchor), [anchorMs, dayCount]); // eslint-disable-line react-hooks/exhaustive-deps
  const feedColor = useMemo(() => {
    const map: Record<string, string> = {};
    feeds.forEach((feed, index) => {
      map[feed.id] = feed.color ?? FALLBACK_COLORS[index % FALLBACK_COLORS.length];
    });
    return map;
  }, [feeds]);

  // Auto-scroll the grid so (a) the current hour lands near the top
  // of the visible area and (b) today's column lands near the left
  // edge of the visible area on first paint. Without this, the user
  // sees 12 AM + day-1 of the rendered range by default and has to
  // manually scroll into "now". Re-runs when the window changes so
  // navigating resets to a sensible viewport.
  const gridRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = gridRef.current;
    if (!node) return;
    const targetHour = Math.max(0, new Date().getHours() - 1);
    node.scrollTop = targetHour * HOUR_ROW_HEIGHT_PX;
    // Horizontal: land on today's column if it's within the rendered
    // range. Day-column width is `DAY_COL_MIN_WIDTH_PX` at the floor
    // and may stretch wider via `1fr` — using the floor under-shoots
    // on wide viewports, which is the safer error (user lands a bit
    // before today rather than past it).
    const todayIdx = days.findIndex((iso) => isToday(iso));
    if (todayIdx >= 0) {
      node.scrollLeft = todayIdx * DAY_COL_MIN_WIDTH_PX;
    }
  }, [anchorMs, dayCount]); // eslint-disable-line react-hooks/exhaustive-deps

  // Inline the column template so `dayCount` drives the grid width
  // dynamically. CSS custom properties can't be used as the count
  // argument to `repeat()`, so we build the value here and let the
  // inline style override the module rule. The hour-gutter column
  // (56px) is fixed; each day column gets DAY_COL_MIN_WIDTH_PX as a
  // floor so the grid overflows its container and the user can pan.
  const gridStyle = {
    gridTemplateColumns: `56px repeat(${dayCount}, minmax(${DAY_COL_MIN_WIDTH_PX}px, 1fr))`,
  };

  return (
    <div className={styles.grid} ref={gridRef} style={gridStyle}>
      <div className={styles.hourGutter} aria-hidden>
        {Array.from({ length: HOUR_SPAN + 1 }, (_, i) => (
          <div key={i} className={styles.hourLabel}>
            {formatHourLabel(HOUR_START + i)}
          </div>
        ))}
      </div>
      {days.map((day) => {
        const dayEvents = events.filter(
          (event) => !event.all_day && isSameLocalDay(event.start_at, day)
        );
        const daySuggestions = suggestions.filter((s) => isSameLocalDay(s.start_at, day));

        return (
          <div
            className={[
              styles.dayColumn,
              isToday(day) ? styles.dayColumnToday : "",
            ]
              .filter(Boolean)
              .join(" ")}
            key={day}
          >
            <header className={styles.dayHeader}>{formatDayHeader(day)}</header>
            <div className={styles.dayBody} aria-label={`Events for ${formatDayHeader(day)}`}>
              {Array.from({ length: HOUR_SPAN }, (_, i) => (
                <div className={styles.hourRow} key={i} />
              ))}
              {isToday(day) ? <NowIndicator /> : null}
              {dayEvents.map((event) => {
                const placement = computePlacement(event.start_at, event.end_at);
                if (placement === null) return null;
                return (
                  <EventBlock
                    key={event.id}
                    event={event}
                    color={feedColor[event.feed_id]}
                    topPercent={placement.topPercent}
                    heightPercent={placement.heightPercent}
                    onSelect={onSelectEvent}
                  />
                );
              })}
              {daySuggestions.map((suggestion) => {
                const placement = computePlacement(
                  suggestion.start_at,
                  suggestion.end_at
                );
                if (placement === null) return null;
                return (
                  <SuggestionCard
                    key={suggestion.id}
                    suggestion={suggestion}
                    topPercent={placement.topPercent}
                    heightPercent={placement.heightPercent}
                    onAccept={() => onAcceptSuggestion(suggestion.id)}
                    onDismiss={() => onDismissSuggestion(suggestion.id)}
                  />
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Map an event's [start, end] into top%/height% within the day body.
 * Returns null if the event falls entirely outside the visible
 * window (e.g., a 3 AM lab — we just don't render it; the user can
 * scroll the page if Phase 2 surfaces one).
 */
function computePlacement(
  startIso: string,
  endIso: string
): { topPercent: number; heightPercent: number } | null {
  const startHour = hourOfDay(startIso);
  const endHour = hourOfDay(endIso);

  // Clip to visible window
  const top = Math.max(startHour, HOUR_START);
  const bottom = Math.min(endHour, HOUR_END);
  if (bottom <= top) return null;

  const topPercent = ((top - HOUR_START) / HOUR_SPAN) * 100;
  const heightPercent = ((bottom - top) / HOUR_SPAN) * 100;
  return { topPercent, heightPercent };
}

/**
 * "Now" line — a thin horizontal indicator placed at the current
 * minute within today's column. Updates every 30s so the line never
 * sits more than that off the actual time. Does not render outside
 * today's column (parent gates on `isToday(day)`).
 */
function NowIndicator() {
  const [topPct, setTopPct] = useState(() => currentDayPercent());
  useEffect(() => {
    const tick = () => setTopPct(currentDayPercent());
    // Tick on focus + every 30s so a sleeping laptop catches up
    // immediately on wake.
    const id = window.setInterval(tick, 30_000);
    const onFocus = () => tick();
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("focus", onFocus);
    };
  }, []);
  // Day window is full 24h, so `topPct` is just minutes-since-midnight
  // / 1440. Clamp into [0, 100] just in case of a clock skew.
  const top = Math.max(0, Math.min(100, topPct));
  return <div className={styles.nowLine} style={{ top: `${top}%` }} aria-hidden />;
}

function currentDayPercent(): number {
  const now = new Date();
  const minutes = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
  return (minutes / (24 * 60)) * 100;
}

function formatHourLabel(hour: number): string {
  // 12-hour locale-friendly "9 AM" / "1 PM" format. Locale-aware
  // formatting via Intl would be nicer but the labels need to be
  // tight enough to fit the gutter width — this keeps it bounded.
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  const suffix = hour < 12 ? "AM" : "PM";
  return `${h12} ${suffix}`;
}

// Deterministic per-feed fallback palette (used when the feed has no
// user-set color). Colors are picked to be distinguishable on both
// light and dark themes, so the grid stays readable without a legend.
const FALLBACK_COLORS = [
  "oklch(0.74 0.13 200)",  // teal
  "oklch(0.74 0.14 30)",   // amber
  "oklch(0.70 0.18 320)",  // magenta
  "oklch(0.74 0.16 140)",  // green
  "oklch(0.72 0.15 60)",   // gold
  "oklch(0.70 0.18 280)",  // violet
];
