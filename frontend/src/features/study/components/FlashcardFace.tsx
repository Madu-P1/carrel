import type { ComponentChildren } from "preact";

import styles from "./FlashcardFace.module.css";

export interface FlashcardFaceProps {
  /**
   * Which side of the flashcard this is. Drives the type scale: the
   * answer is intentionally 4px larger than the question because the
   * thing being learned should win visual weight.
   */
  kind: "question" | "answer";
  /**
   * Mono uppercase eyebrow shown above the body. Typically the
   * concept name. Long strings ellipsis-truncate so card width stays
   * stable across cards.
   */
  eyebrow: string;
  /**
   * Optional secondary eyebrow line — typically the source document
   * name. Rendered smaller + tertiary so `eyebrow` reads as the
   * primary anchor and this is supporting metadata.
   */
  eyebrowSecondary?: string;
  /**
   * The card text — question prompt or revealed answer.
   */
  body: ComponentChildren;
  /**
   * Optional bottom-anchored hint (e.g. "Tap to flip"). Anchored
   * via `margin-top: auto` in the stylesheet so the body always has
   * room to breathe before the hint shows up.
   */
  hint?: string;
}

/**
 * Visual chrome for one face of the SRS flashcard.
 *
 * Sizing model: the parent `<FlipCard>` owns the height (via a
 * `clamp()`-driven `.scene` rule); this face fills it via
 * `height: 100%`. Long answers overflow into a scoped scrollbar on
 * `.face` itself, NOT on the perspective parent — keeping each face
 * a discrete paint layer preserves `backface-visibility: hidden`
 * during the flip transform.
 *
 * The flashcard-scoped type scale (28/32px serif) lives in this
 * component's CSS module rather than design-system tokens because
 * it's the only surface that needs it today. Promote to tokens the
 * moment a second view wants the same scale.
 */
export function FlashcardFace({
  kind,
  eyebrow,
  eyebrowSecondary,
  body,
  hint,
}: FlashcardFaceProps) {
  const bodyClass = [
    styles.body,
    kind === "question" ? styles.question : styles.answer,
  ].join(" ");
  return (
    <div className={styles.face} data-flashcard-face={kind}>
      <span className={styles.eyebrow}>{eyebrow}</span>
      {eyebrowSecondary ? (
        <span className={styles.eyebrowSecondary}>{eyebrowSecondary}</span>
      ) : null}
      <p className={bodyClass}>{body}</p>
      {hint ? <span className={styles.hint}>{hint}</span> : null}
    </div>
  );
}
