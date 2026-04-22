import { useEffect, useId, useRef, useState } from "preact/hooks";
import type { ComponentChildren } from "preact";

import styles from "./Tooltip.module.css";

export interface TooltipProps {
  content: string;
  delay?: number;
  /** Allow the content to wrap across multiple lines. Default single-line. */
  multiline?: boolean;
  children?: ComponentChildren;
}

export function Tooltip({ content, delay = 400, multiline = false, children }: TooltipProps) {
  const [open, setOpen] = useState(false);
  const timerRef = useRef<number | null>(null);
  const tooltipId = useId();

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const show = () => {
    clearTimer();
    timerRef.current = window.setTimeout(() => setOpen(true), delay);
  };

  const hide = () => {
    clearTimer();
    setOpen(false);
  };

  // Hide on click so the tooltip doesn't linger through navigation (e.g., a
  // citation chip kicking off the SM-2 flight has the tooltip dismiss in the
  // same frame the click handler runs).
  const hideOnClick = () => hide();

  return (
    <span
      aria-describedby={open ? tooltipId : undefined}
      className={styles.trigger}
      onBlur={hide}
      onClick={hideOnClick}
      onFocus={show}
      onMouseLeave={hide}
      onMouseOver={show}
    >
      {children}
      {open ? (
        <span
          className={[styles.content, multiline ? styles.multiline : ""]
            .filter(Boolean)
            .join(" ")}
          id={tooltipId}
          role="tooltip"
        >
          {content}
        </span>
      ) : null}
    </span>
  );
}
