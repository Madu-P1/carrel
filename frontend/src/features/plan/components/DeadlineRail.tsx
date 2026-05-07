import { useState } from "preact/hooks";

import { Stack, Text, toast } from "@/design-system";

import { planApi } from "../api/planApi";
import { usePlanDeadlines } from "../hooks/usePlanDeadlines";

import { AddDeadlineDialog } from "./AddDeadlineDialog";
import styles from "./DeadlineRail.module.css";

// The backend prefixes manual deadlines with "Deadline: " so the
// keyword detector regex always hits regardless of user wording.
// Strip the prefix here so the display matches what the user typed.
const DISPLAY_PREFIX = "Deadline: ";

function displayLabel(rawLabel: string): string {
  if (rawLabel.startsWith(DISPLAY_PREFIX)) {
    return rawLabel.slice(DISPLAY_PREFIX.length);
  }
  return rawLabel;
}

/**
 * Horizontal rail of upcoming deadlines, rendered above the WeekTimeGrid.
 *
 * Why it exists: the pitch's wedge is "the deadline is the unit of work."
 * The Plan view needs to make those deadlines visible without scrolling
 * or guessing. Each card shows the label, the absolute date, the
 * relative urgency in days, and a severity color (high = accent, normal
 * = neutral, low = muted).
 *
 * The rail self-fetches on mount and on a 60s timer. It does not block
 * the rest of the Plan view; if the request errors, the rail simply
 * collapses (rather than rendering an error chip on top of the grid).
 */

interface DeadlineRailProps {
  // No props for now — the rail decides its own data shape. If the
  // user wants per-week filtering we can pass `weekStart` later.
}

function formatRelativeDays(daysUntil: number): string {
  const rounded = Math.round(daysUntil);
  if (rounded <= 0) return "today";
  if (rounded === 1) return "tomorrow";
  if (rounded < 7) return `in ${rounded} days`;
  if (rounded < 14) return `in ${Math.round(rounded / 7)} week`;
  return `in ${Math.round(rounded / 7)} weeks`;
}

function formatAbsolute(deadlineAt: string): string {
  try {
    return new Date(deadlineAt).toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
  } catch {
    return deadlineAt;
  }
}

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
export function DeadlineRail(_: DeadlineRailProps) {
  const [addOpen, setAddOpen] = useState(false);
  const { deadlines, refresh } = usePlanDeadlines();

  return (
    <div className={styles.rail} aria-label="Upcoming deadlines">
      <div className={styles.headerRow}>
        <Text variant="caption" tone="tertiary" className={styles.eyebrow}>
          Working toward
        </Text>
        <button
          type="button"
          className={styles.addButton}
          onClick={() => setAddOpen(true)}
          aria-label="Add a deadline"
        >
          + Add
        </button>
      </div>
      {deadlines.length > 0 ? (
        <div role="list" className={styles.listWrap}>
          <Stack direction="horizontal" gap={2} className={styles.cards}>
            {deadlines.map((d) => {
            const visibleLabel = displayLabel(d.label);
            // Color carries severity for sighted users; the aria-label
            // carries it for screen readers. Without this the card
            // sounds identical at any urgency.
            const severityWord =
              d.severity === "high"
                ? "urgent"
                : d.severity === "low"
                  ? "later"
                  : "upcoming";
            const ariaLabel = `${severityWord}: ${visibleLabel}, ${formatRelativeDays(d.days_until)}, ${formatAbsolute(d.deadline_at)}`;
            const isManual = d.feed_kind === "manual" && d.event_id !== null;
            const handleRemove = async (event: Event) => {
              event.stopPropagation();
              if (!d.event_id) return;
              try {
                await planApi.deleteManualDeadline(d.event_id);
                toast.info("Deadline removed", visibleLabel);
                await refresh();
              } catch (caught) {
                toast.error("Could not remove", (caught as Error).message);
              }
            };
            return (
              <div
                key={`${d.source}:${d.event_id ?? d.deadline_at}`}
                className={[
                  styles.card,
                  d.severity === "high"
                    ? styles.high
                    : d.severity === "low"
                      ? styles.low
                      : styles.normal,
                ].join(" ")}
                data-source={d.source}
                role="listitem"
                aria-label={ariaLabel}
              >
                <div className={styles.label}>{visibleLabel}</div>
                <div className={styles.metaRow}>
                  <span className={styles.relative}>
                    {formatRelativeDays(d.days_until)}
                  </span>
                  <span className={styles.dot} aria-hidden>
                    ·
                  </span>
                  <span className={styles.absolute}>
                    {formatAbsolute(d.deadline_at)}
                  </span>
                </div>
                {isManual ? (
                  <button
                    type="button"
                    className={styles.removeButton}
                    onClick={handleRemove}
                    aria-label={`Remove ${visibleLabel}`}
                  >
                    ×
                  </button>
                ) : null}
              </div>
            );
          })}
          </Stack>
        </div>
      ) : (
        <Text tone="tertiary" variant="caption">
          No deadlines yet. Add one to start the coach planning toward it.
        </Text>
      )}
      <AddDeadlineDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onAdded={() => void refresh()}
      />
    </div>
  );
}
