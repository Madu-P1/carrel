import type { ComponentChildren } from "preact";

import styles from "./Badge.module.css";

type Tone = "neutral" | "success" | "warning" | "danger" | "info";

export interface BadgeProps {
  tone?: Tone;
  children?: ComponentChildren;
  className?: string;
}

export function Badge({ tone = "neutral", children, className }: BadgeProps) {
  return (
    <span
      className={[styles.badge, styles[`tone-${tone}`], className ?? ""]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </span>
  );
}
