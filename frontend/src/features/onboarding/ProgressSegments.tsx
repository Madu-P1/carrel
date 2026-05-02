import styles from "./FirstRunTour.module.css";

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function ProgressSegments({ current, total }: { current: number; total: number }) {
  return (
    <div
      aria-label={`Step ${current} of ${total}`}
      className={styles.progressSegments}
      role="progressbar"
      aria-valuemax={total}
      aria-valuemin={1}
      aria-valuenow={current}
    >
      {Array.from({ length: total }, (_, index) => {
        const step = index + 1;
        return (
          <span
            className={cx(
              styles.progressSegment,
              step < current && styles.progressSegmentComplete,
              step === current && styles.progressSegmentCurrent,
              step > current && styles.progressSegmentUpcoming
            )}
            key={step}
          />
        );
      })}
    </div>
  );
}
