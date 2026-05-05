import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import { parseIsoAsUtc } from "@/lib/time";

import styles from "./TimerRing.module.css";

// Re-export for tests that import from here historically.
export { parseIsoAsUtc };

export type TimerMode = "countdown" | "countup";

interface TimerRingProps {
  /** ISO timestamp when the session began (server truth). */
  startedAt: string;
  /** Planned duration in minutes. Only meaningful in countdown mode;
   *  ignored in countup (the ring fills relative to this target anyway
   *  so a user can see they've gone past their planned duration). */
  targetMinutes: number;
  mode: TimerMode;
  /** Optional label rendered inside the ring under the numeric time.
   *  Mode-specific copy ("focus", "flow", "overtime"). */
  modeLabel: string;
  /** Fires once when a countdown reaches its target. Count-up sessions
   *  never complete automatically. */
  onComplete?: () => void;
}

/**
 * Large circular timer — the centerpiece of the Session view.
 *
 * One SVG ring, anchored to the server's `started_at` so refreshing the
 * page doesn't reset the clock. Client ticks every second (or every
 * minute under `prefers-reduced-motion`). When the target is reached in
 * countdown mode the numeric display flips to 0:00 and the label reads
 * "done"; the user can still end the session manually.
 *
 * Design: ring stroke is the accent; reached/overtime state swaps the
 * stroke to state-warn so the user visually knows they're past plan.
 */
export function TimerRing({ startedAt, targetMinutes, mode, modeLabel, onComplete }: TimerRingProps) {
  const [now, setNow] = useState(() => Date.now());
  const startedMs = useMemo(() => parseIsoAsUtc(startedAt), [startedAt]);
  const completedRef = useRef(false);
  const prefersReducedMotion =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
  const targetSec = Math.max(60, targetMinutes * 60);

  useEffect(() => {
    const interval = prefersReducedMotion ? 60_000 : 1_000;
    const timer = window.setInterval(() => setNow(Date.now()), interval);
    return () => window.clearInterval(timer);
  }, [prefersReducedMotion]);

  useEffect(() => {
    completedRef.current = false;
  }, [mode, startedAt, targetSec]);

  useEffect(() => {
    if (mode !== "countdown" || !Number.isFinite(startedMs)) return;
    const remainingMs = targetSec * 1000 - Math.max(0, Date.now() - startedMs);
    const complete = () => {
      if (completedRef.current) return;
      completedRef.current = true;
      setNow(Date.now());
      onComplete?.();
    };
    if (remainingMs <= 0) {
      complete();
      return;
    }
    const timeout = window.setTimeout(complete, remainingMs);
    return () => window.clearTimeout(timeout);
  }, [mode, onComplete, startedMs, targetSec]);

  const size = 240;
  const strokeWidth = 10;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  // Elapsed in whole seconds, defending against clock skew / bad input.
  const elapsedSec = Number.isFinite(startedMs)
    ? Math.max(0, Math.floor((now - startedMs) / 1000))
    : 0;
  let displaySec: number;
  let progress: number; // 0..1 — fraction of ring filled
  let overtime = false;

  if (mode === "countdown") {
    const remaining = Math.max(0, targetSec - elapsedSec);
    displaySec = remaining;
    overtime = elapsedSec > targetSec;
    // Countdown ring EMPTIES as time passes.
    progress = Math.min(1, Math.max(0, remaining / targetSec));
  } else {
    displaySec = elapsedSec;
    overtime = elapsedSec > targetSec;
    // Countup ring FILLS as time passes, capped at full then stays full.
    progress = Math.min(1, elapsedSec / targetSec);
  }

  const dashLen = circumference * progress;
  const stroke = overtime ? "var(--state-warn)" : "var(--accent)";

  return (
    <div
      className={[styles.wrap, overtime ? styles.wrapOver : ""].join(" ")}
      role="timer"
      aria-label={`${modeLabel} timer, ${formatElapsed(displaySec)}`}
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
          stroke={stroke}
          strokeWidth={strokeWidth}
          strokeDasharray={`${dashLen} ${circumference}`}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{
            transition: prefersReducedMotion
              ? "none"
              : "stroke-dasharray 0.25s linear, stroke 0.2s var(--ease-out)"
          }}
        />
      </svg>
      <div className={styles.center}>
        <span className={styles.time}>{formatElapsed(displaySec)}</span>
        <span className={styles.label}>
          {overtime && mode === "countdown" ? "overtime" : modeLabel}
        </span>
      </div>
    </div>
  );
}

function formatElapsed(totalSec: number): string {
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
