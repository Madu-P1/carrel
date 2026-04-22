import { useEffect, useState } from "preact/hooks";

import { AnswerSkeleton } from "./AnswerSkeleton";
import styles from "./ColdLoadIndicator.module.css";

interface ColdLoadIndicatorProps {
  /** When true, an Ask request is currently in flight. */
  pending: boolean;
  /** Which provider the last successful call used, if any. Drives the
   *  heuristic — we only warm-load the display for Ollama-style local
   *  models. When unknown, we show the normal skeleton. */
  lastProvider?: string;
  /** Unix millis of the last successful tutor response. Used to decide
   *  whether the model is likely cold. `null` means no calls yet this
   *  session, which we treat as cold. */
  lastSuccessAt: number | null;
  /** Ollama's keep-alive window in minutes. Default 30 mirrors
   *  `.env.example::OLLAMA_KEEP_ALIVE` — anything older than this is a
   *  safe bet for a cold load. */
  keepAliveMinutes?: number;
  /** How long the request must be pending before we swap to the warming
   *  state. A fast local response should never hit this — the user
   *  should just see the normal skeleton flash and then the answer. */
  coldThresholdMs?: number;
}

/**
 * Transitional skeleton for Ask. Renders the generic shimmer until we
 * suspect the local model is cold-loading, then swaps to an explicit
 * "Warming local model" state so the user knows the 20-60 second wait
 * is expected, not broken.
 *
 * Why client-side: the backend doesn't stream today and doesn't emit
 * per-request progress events. A client-side heuristic based on
 * elapsed-in-pending + last-success-timestamp is less accurate than a
 * server signal, but strictly better than what we shipped initially
 * (no indication at all).
 *
 * The heuristic:
 *   - If NO previous successful Ollama call in this session → cold
 *   - If last successful call > keep-alive ago → cold
 *   - Otherwise → warm (keep the plain skeleton)
 *   - Anything other than Ollama → assume cloud, never show warming
 *
 * Fallthrough is always the normal skeleton. Worst case we flash the
 * skeleton for 3s before swapping — not broken, just slightly generic.
 */
export function ColdLoadIndicator({
  pending,
  lastProvider,
  lastSuccessAt,
  keepAliveMinutes = 30,
  coldThresholdMs = 3_000
}: ColdLoadIndicatorProps) {
  const [exceededThreshold, setExceededThreshold] = useState(false);

  // Reset + start a timer whenever pending transitions to true.
  useEffect(() => {
    if (!pending) {
      setExceededThreshold(false);
      return;
    }
    const handle = window.setTimeout(
      () => setExceededThreshold(true),
      coldThresholdMs
    );
    return () => window.clearTimeout(handle);
  }, [pending, coldThresholdMs]);

  if (!pending) return null;

  const providerLooksLocal =
    !lastProvider ||
    lastProvider.toLowerCase().startsWith("llama") ||
    lastProvider.toLowerCase().includes("ollama");

  const now = Date.now();
  const keepAliveMs = keepAliveMinutes * 60_000;
  const isLikelyCold =
    exceededThreshold &&
    providerLooksLocal &&
    (lastSuccessAt === null || now - lastSuccessAt > keepAliveMs);

  if (!isLikelyCold) {
    return <AnswerSkeleton />;
  }

  return (
    <div className={styles.wrap} role="status" aria-live="polite" data-testid="ask-cold-load">
      <div className={styles.inner}>
        <span className={styles.pulse} aria-hidden />
        <div className={styles.body}>
          <span className={styles.headline}>Warming local model</span>
          <span className={styles.sub}>
            First run after a quiet period loads the model into memory.
            This usually takes 20–60 seconds.
          </span>
        </div>
      </div>
    </div>
  );
}
