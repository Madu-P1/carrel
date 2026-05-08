import type { ComponentChildren } from "preact";

import styles from "./FlipCard.module.css";

export interface FlipCardProps {
  /** Whether the card is showing the back (true) or the front (false). */
  flipped: boolean;
  /**
   * Click handler on the card body. Wires the same flip toggle that
   * the spacebar shortcut fires, so users who reach for the mouse get
   * the same behaviour without learning a different gesture.
   */
  onFlip?: () => void;
  front: ComponentChildren;
  back: ComponentChildren;
  /** Optional extra class for the outer wrapper (e.g. focus-mode sizing). */
  className?: string;
}

/**
 * Horizontal 3D flip card for the SRS review session (S-2).
 *
 * Both faces sit in the same DOM at all times — only the parent's
 * transform changes. That keeps the card height stable across flips
 * (back-side content can't bump it short or tall), preserves focus
 * across the flip, and lets `prefers-reduced-motion` collapse the
 * transition cleanly without any layout shift.
 *
 * `aria-live` on the back face announces reveal so screen readers
 * speak the answer; the front face stays silent because the user
 * already knows what they typed.
 */
export function FlipCard({ flipped, onFlip, front, back, className }: FlipCardProps) {
  const wrapClass = [styles.scene, className].filter(Boolean).join(" ");
  const innerClass = [styles.inner, flipped ? styles.flipped : ""]
    .filter(Boolean)
    .join(" ");
  return (
    <div
      className={wrapClass}
      onClick={onFlip}
      onKeyDown={(event) => {
        if (event.key === " " || event.key === "Enter") {
          event.preventDefault();
          onFlip?.();
        }
      }}
      role="button"
      tabIndex={0}
      aria-pressed={flipped}
      aria-label={flipped ? "Card showing answer. Activate to hide." : "Card showing question. Activate to reveal answer."}
    >
      <div className={innerClass}>
        <div className={`${styles.face} ${styles.front}`} aria-hidden={flipped}>
          {front}
        </div>
        <div className={`${styles.face} ${styles.back}`} aria-hidden={!flipped} aria-live="polite">
          {back}
        </div>
      </div>
    </div>
  );
}
