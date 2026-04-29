import type { PlanEvent } from "../api/planApi";
import { formatTimeRange } from "../utils/timezone";
import styles from "./EventBlock.module.css";

interface EventBlockProps {
  event: PlanEvent;
  /** Hex color for the feed this event came from. The background uses a
   *  low-alpha tint of this; the left edge gets a 2px solid bar of the
   *  saturated color. Lets the user visually distinguish overlapping
   *  feeds at a glance without a legend. */
  color?: string | null;
  /** Hours-from-day-start (0-24, decimal) where the block starts. */
  topPercent: number;
  /** Block height as % of the day grid. */
  heightPercent: number;
}

/**
 * One event positioned absolutely inside a day column of WeekTimeGrid.
 *
 * Tentative events get a dashed border + reduced opacity. Cancelled
 * events are filtered out upstream (repository skips status=cancelled
 * in list_events_in_window) so we never render them here.
 */
export function EventBlock({
  event,
  color,
  topPercent,
  heightPercent,
}: EventBlockProps) {
  const accent = color ?? "var(--color-accent)";
  const className = [
    styles.block,
    event.status === "tentative" ? styles.blockTentative : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={className}
      style={{
        top: `${topPercent}%`,
        height: `${heightPercent}%`,
        // CSS custom prop wins over the design-system default; the
        // EventBlock.module.css uses var(--event-color) for both rail
        // + tint so we only set the variable in one place.
        ["--event-color" as string]: accent,
      }}
      title={event.summary}
    >
      <span className={styles.title}>{event.summary || "(untitled)"}</span>
      <span className={styles.meta}>{formatTimeRange(event.start_at, event.end_at)}</span>
      {event.location ? (
        <span className={styles.meta}>{event.location}</span>
      ) : null}
    </div>
  );
}
