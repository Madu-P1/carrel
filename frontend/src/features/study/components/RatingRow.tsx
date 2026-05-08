import type { SrsRating } from "@/services/api/endpoints";

import styles from "./RatingRow.module.css";

export interface RatingDescriptor {
  rating: SrsRating;
  label: string;
  /** 1..4 — both the keyboard shortcut and the visual badge. */
  key: string;
}

export interface RatingRowProps {
  ratings: RatingDescriptor[];
  /** True while a rating request is in flight; disables the row. */
  submitting: boolean;
  onSelect: (rating: SrsRating) => void;
}

/**
 * Confidence-scale rating row for the SRS review session (S-2).
 *
 * The four ratings represent a spectrum from "I forgot completely"
 * to "I knew it instantly", so the row colours grade smoothly red →
 * amber → green → teal. Hover and press states use micro-scale
 * transforms to give a tactile feel without burning attention.
 *
 * Keyboard handling stays in StudyView's effect — the buttons render
 * the number badge for affordance only, they don't bind keys
 * themselves.
 */
export function RatingRow({ ratings, submitting, onSelect }: RatingRowProps) {
  return (
    <div className={styles.row} role="group" aria-label="Rate your recall">
      {ratings.map((descriptor) => (
        <button
          type="button"
          key={descriptor.rating}
          className={`${styles.button} ${styles[`tone_${descriptor.rating}`]}`}
          onClick={() => onSelect(descriptor.rating)}
          disabled={submitting}
          data-rating={descriptor.rating}
          aria-keyshortcuts={descriptor.key}
        >
          <span className={styles.shortcut} aria-hidden="true">
            {descriptor.key}
          </span>
          <span className={styles.label}>{descriptor.label}</span>
        </button>
      ))}
    </div>
  );
}
