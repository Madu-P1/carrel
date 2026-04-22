import { useEffect, useId, useRef, useState } from "preact/hooks";
import type { ComponentChildren } from "preact";

import styles from "./Tooltip.module.css";

export interface TooltipProps {
  content: string;
  delay?: number;
  children?: ComponentChildren;
}

export function Tooltip({ content, delay = 400, children }: TooltipProps) {
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

  return (
    <span
      aria-describedby={open ? tooltipId : undefined}
      className={styles.trigger}
      onBlur={hide}
      onFocus={show}
      onMouseLeave={hide}
      onMouseOver={show}
    >
      {children}
      {open ? (
        <span className={styles.content} id={tooltipId} role="tooltip">
          {content}
        </span>
      ) : null}
    </span>
  );
}
