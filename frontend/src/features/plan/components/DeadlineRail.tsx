import { useEffect, useState } from "preact/hooks";
import { signal } from "@preact/signals";

import { Stack, Text } from "@/design-system";

import { planApi, type PlanDeadline } from "../api/planApi";

import { AddDeadlineDialog } from "./AddDeadlineDialog";
import styles from "./DeadlineRail.module.css";

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

const deadlinesSignal = signal<PlanDeadline[]>([]);
let lastFetchTs = 0;
const FETCH_TTL_MS = 60_000;

async function fetchDeadlines(force = false): Promise<void> {
  const now = Date.now();
  if (!force && now - lastFetchTs < FETCH_TTL_MS) return;
  lastFetchTs = now;
  try {
    const response = await planApi.deadlines();
    deadlinesSignal.value = response.deadlines;
  } catch {
    // Silent fail: rail collapses, the rest of the Plan view stays
    // working. The next /api/plan poll will retry on its own cadence.
    deadlinesSignal.value = [];
  }
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

  useEffect(() => {
    void fetchDeadlines();
    const id = setInterval(() => void fetchDeadlines(), FETCH_TTL_MS);
    return () => clearInterval(id);
  }, []);

  const deadlines = deadlinesSignal.value;

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
        <Stack direction="horizontal" gap={2} className={styles.cards}>
          {deadlines.map((d) => (
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
            >
              <div className={styles.label}>{d.label}</div>
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
            </div>
          ))}
        </Stack>
      ) : (
        <Text tone="tertiary" variant="caption">
          No deadlines yet. Add one to start the coach planning toward it.
        </Text>
      )}
      <AddDeadlineDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onAdded={() => void fetchDeadlines(true)}
      />
    </div>
  );
}
