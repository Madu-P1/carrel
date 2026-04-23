import { useCallback, useId } from "preact/hooks";
import type { ComponentChildren, JSX } from "preact";

import styles from "./Tabs.module.css";

export interface TabItem {
  /** Stable id — also used as the selected-value when this tab is the
   *  active one. */
  id: string;
  /** Visible label. */
  label: string;
  /** Optional number/count to render as a trailing meta chip ("Chunks · 12"). */
  count?: number | string;
  /** Optional disabled state. Disabled tabs still render but block pointer
   *  and keyboard activation. */
  disabled?: boolean;
}

export interface TabsProps extends Omit<JSX.HTMLAttributes<HTMLDivElement>, "onChange"> {
  items: TabItem[];
  /** Currently active tab id. Parent is the source of truth. */
  value: string;
  /** Fired when the user activates a different tab. */
  onChange: (id: string) => void;
  /** Layout variant. `segmented` = full-width buttons on one row,
   *  `inline` = natural-width buttons left-aligned with hairline. */
  variant?: "segmented" | "inline";
  /** Optional aria-label for the tablist. */
  ariaLabel?: string;
  children?: ComponentChildren;
}

/**
 * Tabs primitive.
 *
 * Minimal, accessible tablist. WAI-ARIA pattern: each tab is a button with
 * role=tab, wrapped in role=tablist. Arrow-left/right cycles the focus.
 * Space/Enter activates. The caller owns the `value` state (controlled
 * component) and re-renders the associated tabpanel — this primitive is
 * structural only; it does not show or hide content itself.
 *
 * Two variants:
 *   - segmented: equal-width buttons in a single row with a soft
 *     background band. Use for top-level mode switching (Reader right
 *     rail, Dashboard sections).
 *   - inline: natural-width buttons left-aligned with a 1px bottom
 *     hairline under the bar. Use for secondary grouping within a panel.
 */
export function Tabs({
  items,
  value,
  onChange,
  variant = "segmented",
  ariaLabel,
  className,
  ...rest
}: TabsProps) {
  const listId = useId();

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      const key = event.key;
      if (key !== "ArrowRight" && key !== "ArrowLeft" && key !== "Home" && key !== "End") {
        return;
      }
      event.preventDefault();
      const enabled = items.filter((item) => !item.disabled);
      if (enabled.length === 0) return;
      const currentIndex = enabled.findIndex((item) => item.id === value);
      let nextIndex = currentIndex;
      if (key === "ArrowRight") nextIndex = (currentIndex + 1) % enabled.length;
      else if (key === "ArrowLeft") nextIndex = (currentIndex - 1 + enabled.length) % enabled.length;
      else if (key === "Home") nextIndex = 0;
      else if (key === "End") nextIndex = enabled.length - 1;
      const next = enabled[nextIndex];
      if (next) onChange(next.id);
    },
    [items, value, onChange]
  );

  const classes = [styles.tablist, styles[`variant-${variant}`], className ?? ""]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      aria-label={ariaLabel}
      className={classes}
      id={listId}
      onKeyDown={handleKeyDown}
      role="tablist"
      {...rest}
    >
      {items.map((item) => {
        const isActive = item.id === value;
        const tabClasses = [
          styles.tab,
          isActive ? styles.tabActive : "",
          item.disabled ? styles.tabDisabled : "",
        ]
          .filter(Boolean)
          .join(" ");
        return (
          <button
            aria-selected={isActive}
            className={tabClasses}
            disabled={item.disabled}
            id={`${listId}-tab-${item.id}`}
            key={item.id}
            onClick={() => {
              if (!item.disabled) onChange(item.id);
            }}
            role="tab"
            tabIndex={isActive ? 0 : -1}
            type="button"
          >
            <span className={styles.tabLabel}>{item.label}</span>
            {item.count !== undefined ? (
              <span aria-hidden className={styles.tabCount}>
                {item.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
