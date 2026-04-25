import { Icon, type IconName } from "@/design-system";
import { navigateTo } from "@/app/shell/useAppShell";

import styles from "./QuickActionGrid.module.css";

interface QuickTile {
  icon: IconName;
  title: string;
  meta: string;
  path: string;
}

interface QuickActionGridProps {
  /** Number of cards currently due for review. Drives the "Review cards"
   *  tile's meta line — "Nothing due" vs "N cards due". */
  dueCards: number;
}

/**
 * QuickActionGrid — four compact tiles, not cards.
 *
 * Premium UI ship 6: the previous version rendered four full Card
 * primitives at ~140px tall each, which made the dashboard feel like a
 * grid of widgets all asking for equal attention. This rewrite drops to
 * 80px tiles with a tighter horizontal layout (icon | title + meta), so
 * they read as "shortcuts" in service of the page's two anchors (Hero
 * composer + Next best action), not as competing destinations.
 *
 * Layout:
 *   - icon (18px) on the left in a 36×36 chip
 *   - title (14px semibold) and meta (--text-label-md tertiary) stacked on the right
 *   - 80px height, --space-4 padding
 *   - Hover: --state-bg-hover + translateY(-1px)
 */
export function QuickActionGrid({ dueCards }: QuickActionGridProps) {
  const tiles: QuickTile[] = [
    {
      icon: "study",
      title: "Start session",
      meta: "Focused deep work",
      path: "/session",
    },
    {
      icon: "ask",
      title: "Ask tutor",
      meta: "Grounded in sources",
      path: "/ask",
    },
    {
      icon: "doc",
      title: "Review cards",
      meta:
        dueCards > 0
          ? `${dueCards} card${dueCards === 1 ? "" : "s"} due`
          : "Nothing due",
      path: "/study",
    },
    {
      icon: "sparkle",
      title: "Generate artifact",
      meta: "Summary, flashcards, quiz",
      path: "/library",
    },
  ];

  return (
    <section className={styles.grid} aria-label="Quick actions">
      {tiles.map((tile) => (
        <button
          key={tile.title}
          type="button"
          className={styles.tile}
          onClick={() => navigateTo(tile.path)}
        >
          <span className={styles.icon} aria-hidden>
            <Icon name={tile.icon} size={18} />
          </span>
          <span className={styles.body}>
            <span className={styles.title}>{tile.title}</span>
            <span className={styles.meta}>{tile.meta}</span>
          </span>
        </button>
      ))}
    </section>
  );
}
