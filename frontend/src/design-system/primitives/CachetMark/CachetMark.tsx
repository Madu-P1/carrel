import styles from "./CachetMark.module.css";

/**
 * The Cachet brand mark, animated.
 *
 * The logo is the truncated C drawn as an open ring, severed in the upper-left
 * (the unfinished impression is the refusal). It moves with transforms or a
 * path-draw, so the mark's shape is never altered.
 *
 * Path data is the real brand asset (cachet-landing/assets/brand/cachet-mark.svg),
 * viewBox 0 0 240 240. `strokeWidth` is in viewBox units; the default 20 is the
 * weight used on the landing page.
 *
 * States:
 * - `idle`    a near-imperceptible breath. The resting state.
 * - `wriggle` a small organic tilt back and forth.
 * - `reveal`  the ring draws itself along its own path (one-shot).
 *
 * Ink is `currentColor`, so the mark reverses on paper or the dark desk by setting
 * `color` on an ancestor. Honors `prefers-reduced-motion`.
 */

export type CachetMarkState = "idle" | "wriggle" | "reveal";

export interface CachetMarkProps {
  /** Animation state. Defaults to `idle`. */
  state?: CachetMarkState;
  /** Rendered square size in px. Defaults to 40. */
  size?: number;
  /** Stroke weight in viewBox units. Defaults to 20 (the landing-page weight). */
  strokeWidth?: number;
  /** Accessible label. Defaults to "Cachet". */
  title?: string;
  /** Fires once when the `reveal` one-shot finishes. */
  onRevealEnd?: () => void;
  /** Extra class names on the root element. */
  className?: string;
}

export function CachetMark({
  state = "idle",
  size = 40,
  strokeWidth = 20,
  title = "Cachet",
  onRevealEnd,
  className
}: CachetMarkProps) {
  return (
    <span
      aria-label={title}
      className={[styles.root, className].filter(Boolean).join(" ")}
      data-state={state}
      role="img"
      style={{ width: `${size}px`, height: `${size}px` }}
    >
      <svg aria-hidden={true} className={styles.svg} fill="none" viewBox="0 0 240 240">
        <g className={styles.mark}>
          <g className={styles.cwrap}>
            <path
              className={styles.c}
              stroke-width={strokeWidth}
              pathLength={100}
              d="M174.25 86.02 A64 64 0 0 1 80.53 69.56"
            />
            <path
              className={styles.c}
              stroke-width={strokeWidth}
              pathLength={100}
              d="M64.53 88.00 A64 64 0 0 0 174.25 153.98"
              onAnimationEnd={() => {
                if (state === "reveal") onRevealEnd?.();
              }}
            />
          </g>
        </g>
      </svg>
    </span>
  );
}
