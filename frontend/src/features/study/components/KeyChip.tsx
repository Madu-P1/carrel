import styles from "./KeyChip.module.css";

export interface KeyChipProps {
  /**
   * Keys to render as glyphs. Each becomes a single chip:
   *   ["Space"]            → [ Space ]
   *   ["1", "2", "3", "4"] → [ 1 ] [ 2 ] [ 3 ] [ 4 ]
   * Strings render verbatim — capitalization is the caller's call.
   */
  keys: string[];
  /**
   * Optional accompanying label. Renders to the LEFT of the chips,
   * mono tertiary. Use sparingly; chips alone are usually clearer.
   */
  label?: string;
  /**
   * When true, drops opacity so the cue stays visible without
   * pulling the user's eye. PR 3 intent: show full-strength on the
   * first card of a session, dim it after the user has reviewed at
   * least one (the user has already learned the cue).
   */
  dimmed?: boolean;
  /**
   * Optional layout override for callers that need the chip on the
   * left or center (default is `flex-end`).
   */
  align?: "start" | "center" | "end";
}

/**
 * Keyboard-cue chip glyph used as the bottom-anchored hint on the
 * SRS flashcard surface. Mono, low-contrast, monospaced-bracketed.
 *
 * The chip pattern reads as "keypress" without using the heavier
 * outlined `<kbd>`-style glyphs — this surface is meant to be
 * unobtrusive, not instructive.
 */
export function KeyChip({ keys, label, dimmed = false, align = "end" }: KeyChipProps) {
  if (keys.length === 0) return null;
  const wrapClass = [
    styles.wrap,
    dimmed ? styles.dimmed : "",
    align === "start" ? styles.alignStart : "",
    align === "center" ? styles.alignCenter : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <span className={wrapClass} aria-hidden="true">
      {label ? <span className={styles.label}>{label}</span> : null}
      <span className={styles.chips}>
        {keys.map((key) => (
          <span key={key} className={styles.chip}>
            {key}
          </span>
        ))}
      </span>
    </span>
  );
}
