import type { ComponentChildren } from "preact";

import { Icon } from "@/design-system";
import type { IconName } from "@/design-system";

import styles from "./SourcePanel.module.css";

interface EmptyStateProps {
  /** 16x16 glyph that sits above the copy. Use a light-weight outline
   *  icon so it reads as "hint", not "alert". */
  icon: IconName;
  /** Primary line — one short sentence. Sentence case, ends with a
   *  period. No "Oops" or exclamation marks. Tone is calm and useful. */
  title: string;
  /** Secondary line — explain *why* it's empty and *how* to make it not
   *  empty. Single sentence. */
  description: string;
  /** Optional primary action. Rendered as a ghost-style button below
   *  the copy. If omitted, the state is purely informational. */
  action?: ComponentChildren;
}

/**
 * EmptyState — shared "nothing here yet" block for the right rail tabs.
 *
 * The critique was specific: empty states are where scripted copy lives
 * or dies. A blank tab with no explanation is a void. This component
 * takes three inputs (icon, title, description) and optionally an
 * action, and renders them on a stable layout so every empty tab in the
 * rail feels like the same family.
 *
 * Intentionally tight spacing (no hero-scale whitespace): the right rail
 * is 320px wide, and a towering empty state in that narrow column looks
 * broken. The glyph + two lines + optional button is enough.
 */
export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyIcon} aria-hidden>
        <Icon name={icon} size={18} />
      </div>
      <p className={styles.emptyTitle}>{title}</p>
      <p className={styles.emptyDescription}>{description}</p>
      {action ? <div className={styles.emptyAction}>{action}</div> : null}
    </div>
  );
}
