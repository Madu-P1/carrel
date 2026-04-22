import { Icon, type IconName } from "@/design-system";

import styles from "./ModeTile.module.css";

export interface ModeTileData {
  id: string;
  label: string;
  description: string;
  icon: IconName;
}

interface ModeTileProps {
  mode: ModeTileData;
  selected: boolean;
  onSelect: () => void;
}

/**
 * Single mode option for the session setup grid. Three states:
 *   - idle      — hairline border, tertiary icon
 *   - hover     — accent-muted border, primary icon
 *   - selected  — accent border + faint accent surface + accent icon
 */
export function ModeTile({ mode, selected, onSelect }: ModeTileProps) {
  return (
    <button
      type="button"
      className={[styles.tile, selected ? styles.tileSelected : ""].join(" ")}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <span className={styles.iconWrap} aria-hidden>
        <Icon name={mode.icon} size={18} />
      </span>
      <span className={styles.label}>{mode.label}</span>
      <span className={styles.description}>{mode.description}</span>
    </button>
  );
}
