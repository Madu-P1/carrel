import styles from "./StreakRing.module.css";

interface StreakRingProps {
  streakDays: number;
  targetDays: number;
}

/**
 * Circular progress ring rendered with SVG + stroke-dasharray.
 *
 * Three states:
 *   - Zero streak: empty-state copy ("Start a streak") inside a hairline
 *     ring at 0% — avoids the "broken viz" look of a fully empty ring
 *     with no context.
 *   - 1..target-1: partial fill in accent, remainder in hairline.
 *   - ≥ target: full accent ring with the raw number (3-digit overflow OK).
 *
 * Pure SVG, no external deps, no animation. Respects reduced-motion by
 * doing nothing motion-ful.
 */
export function StreakRing({ streakDays, targetDays }: StreakRingProps) {
  const size = 120;
  const strokeWidth = 6;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(streakDays, targetDays));
  const pct = targetDays > 0 ? clamped / targetDays : 0;
  const dashLen = circumference * pct;
  const reached = streakDays >= targetDays;

  if (streakDays === 0) {
    return (
      <div className={styles.wrap} role="img" aria-label={`0 of ${targetDays} day streak`}>
        <svg width={size} height={size} className={styles.svg}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--hairline-strong)"
            strokeWidth={strokeWidth}
          />
        </svg>
        <div className={styles.center}>
          <span className={styles.emptyLabel}>Start a streak</span>
          <span className={styles.emptyHint}>study any day</span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={styles.wrap}
      role="img"
      aria-label={`${streakDays} of ${targetDays} day streak`}
    >
      <svg width={size} height={size} className={styles.svg}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--hairline)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={strokeWidth}
          strokeDasharray={`${dashLen} ${circumference}`}
          strokeLinecap="round"
          // Rotate so the ring starts at 12 o'clock, not 3. Matches the
          // convention users expect from fitness / focus apps.
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className={styles.center}>
        <span className={[styles.value, reached ? styles.valueReached : ""].join(" ")}>
          {streakDays}
        </span>
        <span className={styles.unit}>
          day{streakDays === 1 ? "" : "s"} · of {targetDays}
        </span>
      </div>
    </div>
  );
}
