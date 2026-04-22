import styles from "../AskView.module.css";

interface AnswerMetaBarProps {
  cacheHit: boolean;
  latencyMs: number;
  model: string;
}

/**
 * Quiet metadata beneath an answer. Mono voice, tertiary colour, right-aligned.
 *
 * Per the Einstein brief §9 "Provider / latency badge": no fill, no border.
 * Just the provider model id + latency. The cold-load pulse is rendered by a
 * separate component (`ColdLoadIndicator`) that lives in the evidence row
 * during generation; this bar shows only after the answer lands.
 */
export function AnswerMetaBar({ cacheHit, latencyMs, model }: AnswerMetaBarProps) {
  const modelToken = (model || "no-model").toLowerCase();
  const latencyToken =
    latencyMs > 0 ? `${(latencyMs / 1000).toFixed(1)}s` : "0.0s";
  const cacheToken = cacheHit ? "cache hit" : "cold call";

  return (
    <div className={styles.metaBar} role="status" aria-label="Answer metadata">
      <span className={[styles.metaToken, styles.metaModel].join(" ")}>
        {modelToken}
      </span>
      <span className={styles.metaSeparator} aria-hidden>·</span>
      <span className={styles.metaToken}>{latencyToken}</span>
      <span className={styles.metaSeparator} aria-hidden>·</span>
      <span className={styles.metaToken}>{cacheToken}</span>
    </div>
  );
}
