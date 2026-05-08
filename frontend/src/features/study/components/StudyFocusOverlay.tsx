import { useEffect } from "preact/hooks";
import type { ComponentChildren } from "preact";

import styles from "./StudyFocusOverlay.module.css";

export interface StudyFocusOverlayProps {
  open: boolean;
  onClose: () => void;
  children: ComponentChildren;
  /** Optional progress eyebrow rendered top-left, e.g. "Card 3 of 12". */
  progress?: string;
  /** Optional scope label rendered top-left below progress, e.g. "Biology". */
  scope?: string | null;
}

/**
 * Full-viewport focus mode for the SRS review session (S-2).
 *
 * Slightly dims the background (no blur — per the design brief) and
 * floats the card on a "liquid-glass" surface: translucent fill,
 * backdrop-blur ON THE CARD ONLY (so the dim layer behind stays
 * crisp), soft inner highlight, outer shadow with subtle glow.
 *
 * Esc exits focus mode. The overlay traps focus loosely — pressing
 * Tab cycles through the rating row and the close affordance, but
 * we don't actively block focus from leaving (assistive-tech users
 * can shift to the system menu without the overlay fighting).
 */
export function StudyFocusOverlay({
  open,
  onClose,
  children,
  progress,
  scope,
}: StudyFocusOverlayProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-label="Focused review">
      <div className={styles.dim} aria-hidden="true" />
      <div className={styles.chrome}>
        <div className={styles.header}>
          {progress ? <span className={styles.progress}>{progress}</span> : null}
          {scope ? <span className={styles.scope}>{scope}</span> : null}
        </div>
        <button
          type="button"
          className={styles.close}
          onClick={onClose}
          aria-label="Exit focus mode"
        >
          Esc
        </button>
      </div>
      <div className={styles.glassFrame}>{children}</div>
    </div>
  );
}
