import { navigateTo } from "@/app/shell/useAppShell";
import { Icon } from "@/design-system";
import type { DashboardPayload } from "@/services/api/endpoints";

import styles from "./NextBestAction.module.css";

interface NextBestActionProps {
  next: DashboardPayload["next_best_action"];
}

/**
 * NextBestAction — single contextual recommendation.
 *
 * Premium UI ship 6 reshaped this surface. The previous version used a
 * `--state-warn` (amber) wash + amber-fill primary button, which the
 * critique flagged as "semantically accidental" — warn is for problems,
 * not for nudges. The new system has no "default warning tint," and
 * the right move on a recommendation is the accent.
 *
 * Layout:
 *   - One card. --state-bg-selected wash, accent left rail.
 *   - Eyebrow (`Recommended next` or whatever the server sends).
 *   - Title — decisive, ≤ 8 words.
 *   - Reason — one sentence.
 *   - Two actions: primary accept, secondary dismiss.
 *
 * The card never carries multiple recommendations. If the server returns
 * a different next-best-action between fetches, it replaces this card —
 * stacking is rejected on purpose so the user sees ONE clear next move.
 */
export function NextBestAction({ next }: NextBestActionProps) {
  return (
    <section className={styles.card} aria-label="Next best action">
      <span className={styles.eyebrow}>{next.eyebrow.toUpperCase()}</span>
      <h2 className={styles.title}>{next.title}</h2>
      <p className={styles.reason}>{next.reason}</p>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.primaryAction}
          onClick={() => navigateTo(next.primary.path)}
        >
          {next.primary.label}
          <Icon name="arrow-right" size={14} />
        </button>
        {next.secondary ? (
          <button
            type="button"
            className={styles.secondaryAction}
            onClick={() => navigateTo(next.secondary!.path)}
          >
            {next.secondary.label}
          </button>
        ) : null}
      </div>
    </section>
  );
}
