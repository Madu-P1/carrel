import { useEffect, useRef } from "preact/hooks";

import styles from "./DurationChips.module.css";

interface DurationChipsProps {
  value: number;
  options?: number[];
  onChange: (minutes: number) => void;
  ariaLabel?: string;
  disabled?: boolean;
}

const DEFAULT_OPTIONS = [15, 25, 45, 60];

/**
 * DurationChips — segmented-control duration picker.
 *
 * One value, several options, exclusive selection. That's a radiogroup,
 * not a tablist (no panels are toggled). Each chip is a `role="radio"`
 * with `aria-checked` mirroring the value.
 *
 * Roving tabindex: only the selected chip is in the tab sequence.
 * ArrowLeft / ArrowRight cycle focus & selection. Home / End jump to
 * the ends. This matches WAI-ARIA's Radio Group keyboard pattern and
 * means a keyboard user can pick a duration without ever leaving the
 * group.
 *
 * The chip itself is 28px tall (matches --control-height-sm) but the
 * hit target extends to 40×40 via a transparent ::before pseudo —
 * the visible chip stays compact, fingers find it on touch.
 */
export function DurationChips({
  value,
  options = DEFAULT_OPTIONS,
  onChange,
  ariaLabel = "Focus duration",
  disabled = false,
}: DurationChipsProps) {
  const groupRef = useRef<HTMLDivElement | null>(null);

  // Roving tabindex cycle on arrow keys. Implemented at the group level
  // so each chip stays a simple stateless button.
  const handleKeyDown = (event: KeyboardEvent) => {
    if (disabled) return;
    const key = event.key;
    if (
      key !== "ArrowRight" &&
      key !== "ArrowLeft" &&
      key !== "Home" &&
      key !== "End"
    ) {
      return;
    }
    event.preventDefault();
    const idx = options.indexOf(value);
    if (idx < 0) return;
    let next = idx;
    if (key === "ArrowRight") next = (idx + 1) % options.length;
    else if (key === "ArrowLeft") next = (idx - 1 + options.length) % options.length;
    else if (key === "Home") next = 0;
    else if (key === "End") next = options.length - 1;
    onChange(options[next]);
    // Move focus to the newly selected chip so the ring tracks the value.
    const buttons = groupRef.current?.querySelectorAll<HTMLButtonElement>(
      "[role=\"radio\"]"
    );
    buttons?.[next]?.focus();
  };

  // If the value lands outside the options list (e.g., a recommendation
  // sets 30 but options are 15/25/45/60), don't crash — let the parent
  // see the new value but render no chip as selected.
  useEffect(() => {
    // Intentional no-op; just here as a hook anchor for future telemetry.
  }, [value]);

  return (
    <div
      ref={groupRef}
      role="radiogroup"
      aria-label={ariaLabel}
      className={styles.group}
      onKeyDown={handleKeyDown}
    >
      {options.map((minutes) => {
        const isSelected = minutes === value;
        return (
          <button
            key={minutes}
            type="button"
            role="radio"
            aria-checked={isSelected}
            tabIndex={isSelected ? 0 : -1}
            disabled={disabled}
            onClick={() => !disabled && onChange(minutes)}
            className={[styles.chip, isSelected ? styles.chipSelected : ""]
              .filter(Boolean)
              .join(" ")}
          >
            <span className={styles.chipValue}>{minutes}</span>
            <span className={styles.chipUnit}>m</span>
          </button>
        );
      })}
    </div>
  );
}
