import type { PlanSuggestion } from "../api/planApi";
import { formatTimeRange } from "../utils/timezone";
import styles from "./SuggestionCard.module.css";

interface SuggestionCardProps {
  suggestion: PlanSuggestion;
  topPercent: number;
  heightPercent: number;
  onAccept: () => void;
  onDismiss: () => void;
}

/**
 * Reason codes that surface as urgent: amber tint, "Catch up" eyebrow,
 * elevated visual weight. Coach Phase 2 first holistic loop currently
 * uses one code here; future Phase 2 rules (deadline_imminent) will
 * join this set as they ship.
 */
const URGENT_REASON_CODES = new Set<PlanSuggestion["reason_code"]>([
  "rebalance_on_miss",
]);

/**
 * Coach suggestion rendered inline in the WeekTimeGrid at the time it
 * proposes. Visually distinct from real events (accent-tint background,
 * dashed border) so the user understands "this is a suggestion, not a
 * thing on my calendar yet."
 *
 * Urgent variant: amber tones from `--color-warning` for reason_codes
 * that signal the user is falling behind (rebalance_on_miss today,
 * deadline_imminent when it ships). The visual shift is the only
 * forcing function on this surface; we don't move the card or surface
 * a notification, just escalate visual weight.
 *
 * Accept → suggestion.status flips to 'accepted', backend records it,
 * frontend can later promote into a real event entry. v1 just records.
 *
 * Dismiss → optimistic local removal, backend records, paired with a
 * 5-second-undo toast in the parent (PlanView). Restore reverses if
 * the user undoes within the window.
 */
export function SuggestionCard({
  suggestion,
  topPercent,
  heightPercent,
  onAccept,
  onDismiss,
}: SuggestionCardProps) {
  const isUrgent = URGENT_REASON_CODES.has(suggestion.reason_code);
  const eyebrowLabel = isUrgent ? "Catch up" : "Coach";
  const ariaLabel = isUrgent
    ? `Urgent catch-up suggestion: ${suggestion.reason_text}`
    : `Coach suggestion: ${suggestion.reason_text}`;

  return (
    <article
      className={isUrgent ? `${styles.card} ${styles.urgent}` : styles.card}
      style={{
        top: `${topPercent}%`,
        height: `${heightPercent}%`,
      }}
      aria-label={ariaLabel}
    >
      <header className={styles.header}>
        <span className={styles.eyebrow}>{eyebrowLabel}</span>
        <span className={styles.timeRange}>
          {formatTimeRange(suggestion.start_at, suggestion.end_at)}
        </span>
      </header>
      <p className={styles.reason}>{suggestion.reason_text}</p>
      <footer className={styles.actions}>
        <button
          type="button"
          className={styles.accept}
          onClick={onAccept}
        >
          Schedule it
        </button>
        <button
          type="button"
          className={styles.dismiss}
          onClick={onDismiss}
        >
          Dismiss
        </button>
      </footer>
    </article>
  );
}
