import { Icon, type IconName } from "@/design-system";

import styles from "./ModeCard.module.css";

export interface ModeCardData {
  id: string;
  title: string;
  /** One-line purpose. Reads in --text-body, secondary tone. */
  purpose: string;
  /** Optional metric footer ("Last used 2h ago", "Most used"). Tertiary
   *  tone, --text-label-md. Keeps the card visual rhythm even when no
   *  metric is set — the line stays present but rendered transparent. */
  metric?: string;
  iconName: IconName;
}

interface ModeCardProps {
  mode: ModeCardData;
  selected: boolean;
  onSelect: () => void;
}

/**
 * ModeCard — premium mode selector for the Session cockpit.
 *
 * Replaces the old ModeTile. Spec from docs/roadmap/premium-ui-pass.md
 * Ship 4: 24px icon + h3 semibold title + one-line purpose +
 * optional metric footer. Selected state lifts via translateY(-1px),
 * gains --state-bg-selected fill, --state-border-selected border, and
 * the title color shifts to the accent.
 *
 * Accessibility: each card is a `role="radio"` button. Cards in a group
 * share an outer `role="radiogroup"` (set by the caller) so the four
 * cards form a single control. Keyboard ArrowLeft/Right cycles
 * selection — handled at the group level by the caller's onSelect.
 *
 * Why a card and not a Tabs row: mode selection is a primary
 * commitment ("I'm going to do focused study"), not a tab switch.
 * Cards give each mode room to breathe, room for a metric, and a
 * tactile press target. Tabs would compress them into a strip and
 * lose the cockpit-control feel the page is going for.
 */
export function ModeCard({ mode, selected, onSelect }: ModeCardProps) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      tabIndex={selected ? 0 : -1}
      className={[styles.card, selected ? styles.cardSelected : ""]
        .filter(Boolean)
        .join(" ")}
      onClick={onSelect}
    >
      <span className={styles.iconWrap} aria-hidden>
        <Icon name={mode.iconName} size={24} />
      </span>
      <span className={styles.title}>{mode.title}</span>
      <span className={styles.purpose}>{mode.purpose}</span>
      <span
        className={[
          styles.metric,
          mode.metric ? "" : styles.metricEmpty,
        ]
          .filter(Boolean)
          .join(" ")}
        aria-hidden={!mode.metric}
      >
        {mode.metric ?? "\u00A0"}
      </span>
    </button>
  );
}
