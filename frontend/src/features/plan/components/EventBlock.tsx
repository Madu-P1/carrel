import { Icon } from "@/design-system";

import type { PlanEvent } from "../api/planApi";
import { isUserStudyBlock } from "../utils/eventClassification";
import { formatTimeRange } from "../utils/timezone";

import styles from "./EventBlock.module.css";

// Manual deadlines are stored with a "Deadline: " prefix so the keyword
// detector regex always hits. The prefix is a backend implementation
// detail, not user-facing copy — strip it before rendering on the grid.
const MANUAL_DEADLINE_PREFIX = "Deadline: ";

function presentSummary(summary: string | null | undefined): string {
  const raw = (summary ?? "").trim();
  if (raw.startsWith(MANUAL_DEADLINE_PREFIX)) {
    return raw.slice(MANUAL_DEADLINE_PREFIX.length);
  }
  return raw;
}

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
  /** Click handler — opens the detail dialog. Optional so the block
   *  remains a pure visual block when consumers don't wire detail. */
  onSelect?: (event: PlanEvent) => void;
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
  onSelect,
}: EventBlockProps) {
  const accent = color ?? "var(--color-accent)";
  const interactive = typeof onSelect === "function";
  // Self-scheduled study blocks ("Study Bio", "Revise calc", etc.) get a
  // distinct visual treatment so the user can tell at a glance which
  // blocks the planner is counting as allocated prep time. Matches the
  // backend's STUDY_ALLOCATION_KEYWORDS regex — keep them in sync.
  const isStudy = isUserStudyBlock(event.summary);
  const presented = presentSummary(event.summary);
  const className = [
    styles.block,
    event.status === "tentative" ? styles.blockTentative : "",
    interactive ? styles.blockInteractive : "",
    isStudy ? styles.blockStudy : "",
  ]
    .filter(Boolean)
    .join(" ");

  const handleClick = interactive ? () => onSelect?.(event) : undefined;
  const handleKey = interactive
    ? (e: KeyboardEvent) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect?.(event);
        }
      }
    : undefined;

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
      title={presented}
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      aria-label={interactive ? `${presented || "Untitled"} — view details` : undefined}
      onClick={handleClick}
      onKeyDown={handleKey}
    >
      {isStudy ? (
        <span
          className={styles.studyBadge}
          aria-label="Allocated study block — counted by the planner"
          title="The planner counts this as allocated prep time."
        >
          <Icon name="study" size={12} />
        </span>
      ) : null}
      <span className={styles.title}>{presented || "(untitled)"}</span>
      <span className={styles.meta}>{formatTimeRange(event.start_at, event.end_at)}</span>
      {event.location ? (
        <span className={styles.meta}>{event.location}</span>
      ) : null}
    </div>
  );
}
