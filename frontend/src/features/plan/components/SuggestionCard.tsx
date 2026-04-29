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
 * Coach suggestion rendered inline in the WeekTimeGrid at the time it
 * proposes. Visually distinct from real events — accent-tint
 * background, dashed border, sparkle glyph — so the user understands
 * "this is a suggestion, not a thing on my calendar yet."
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
  return (
    <article
      className={styles.card}
      style={{
        top: `${topPercent}%`,
        height: `${heightPercent}%`,
      }}
      aria-label={`Coach suggestion: ${suggestion.reason_text}`}
    >
      <header className={styles.header}>
        <span className={styles.eyebrow}>Coach</span>
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
