import { useMemo } from "preact/hooks";

import type { CalendarFeed } from "../api/calendarApi";
import type { PlanEvent, PlanSuggestion } from "../api/planApi";
import {
  formatDayHeader,
  hourOfDay,
  isSameLocalDay,
  isToday,
  nextSevenDays,
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
 * Day window: 7 days starting today (00:00 local). Hour window: 7am
 * to 10pm — covers waking-life events without wasting screen on the
 * graveyard hours. All-day events are dropped from the grid (would
 * blanket the whole column); the toolbar gets an "All-day" strip in
 * Phase 2 if it earns its keep.
 */

const HOUR_START = 7;   // 7 AM
const HOUR_END = 22;    // 10 PM
const HOUR_SPAN = HOUR_END - HOUR_START;

interface WeekTimeGridProps {
  events: PlanEvent[];
  suggestions: PlanSuggestion[];
  feeds: CalendarFeed[];
  onAcceptSuggestion: (id: string) => void;
  onDismissSuggestion: (id: string) => void;
}

export function WeekTimeGrid({
  events,
  suggestions,
  feeds,
  onAcceptSuggestion,
  onDismissSuggestion,
}: WeekTimeGridProps) {
  const days = useMemo(() => nextSevenDays(), []);
  const feedColor = useMemo(() => {
    const map: Record<string, string> = {};
    feeds.forEach((feed, index) => {
      map[feed.id] = feed.color ?? FALLBACK_COLORS[index % FALLBACK_COLORS.length];
    });
    return map;
  }, [feeds]);

  return (
    <div className={styles.grid}>
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
