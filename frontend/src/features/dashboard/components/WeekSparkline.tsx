import styles from "./WeekSparkline.module.css";

interface WeekSparklineProps {
  /** Exactly 7 floats, oldest → newest (minutes per day). */
  minutesByDay: number[];
}

/**
 * Tiny 7-day sparkline. Rendered with pure SVG polyline — no charting lib.
 *
 * Design:
 *   - Baseline always drawn. Shows the zero line for visual grounding.
 *   - All-zero week → baseline only + inline caption ("No activity this
 *     week"). Flat line without context reads as broken.
 *   - Max value of the week scales to full height so the shape is
 *     intelligible even for small absolute minutes. The y-axis is
 *     deliberately unlabeled because trend shape is what matters here,
 *     not absolute numbers (those live in the "X.Xh" stat beside it).
 *   - Accent fill under the line for emphasis, at low opacity so it
 *     reads as tonal, not chart chrome.
 *   - Last day (today) highlighted with a small filled dot.
 */
export function WeekSparkline({ minutesByDay }: WeekSparklineProps) {
  const data = padTo7(minutesByDay);
  const allZero = data.every((d) => d <= 0);
  const width = 140;
  const height = 32;
  const padX = 2;
  const padY = 4;
  const usableW = width - padX * 2;
  const usableH = height - padY * 2;
  const maxVal = Math.max(...data, 1);

  const points = data.map((value, index) => {
    const x = padX + (usableW * index) / (data.length - 1);
    const y = padY + usableH - (usableH * value) / maxVal;
    return { x, y };
  });

  const polyline = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  // points was built from `data` (always 7 elements after normalizeWeekData
  // below), so points[0] and points[length-1] are guaranteed defined.
  const areaPath = `M ${points[0]!.x.toFixed(1)} ${(padY + usableH).toFixed(1)} L ${polyline} L ${points[points.length - 1]!.x.toFixed(1)} ${(padY + usableH).toFixed(1)} Z`;
  const last = points[points.length - 1]!;

  if (allZero) {
    return (
      <div className={styles.wrap} role="img" aria-label="No study activity this week">
        <svg width={width} height={height} className={styles.svg}>
          <line
            x1={padX}
            x2={width - padX}
            y1={height - padY}
            y2={height - padY}
            stroke="var(--hairline-strong)"
            strokeWidth={1}
          />
        </svg>
        <span className={styles.caption}>No activity this week yet</span>
      </div>
    );
  }

  return (
    <div
      className={styles.wrap}
      role="img"
      aria-label={`Study minutes over last 7 days: ${data.map((v) => Math.round(v)).join(", ")}`}
    >
      <svg width={width} height={height} className={styles.svg}>
        <path d={areaPath} fill="var(--accent)" fillOpacity={0.14} />
        <polyline
          points={polyline}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx={last.x} cy={last.y} r={2.5} fill="var(--accent)" />
      </svg>
    </div>
  );
}

/** Defensive: ensure exactly 7 values even if the backend ever drifts. */
function padTo7(input: number[]): number[] {
  if (input.length === 7) return input;
  const arr = input.slice(-7);
  while (arr.length < 7) arr.unshift(0);
  return arr;
}
