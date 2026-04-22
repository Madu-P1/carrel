import type { ComponentChildren, JSX } from "preact";

import styles from "./Card.module.css";

type Padding = "sm" | "md" | "lg";

export interface CardProps extends JSX.HTMLAttributes<HTMLElement> {
  padding?: Padding;
  children?: ComponentChildren;
}

export function Card({
  padding = "md",
  className,
  children,
  ...rest
}: CardProps) {
  return (
    <section
      className={[styles.card, styles[`padding-${padding}`], className ?? ""]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children}
    </section>
  );
}
