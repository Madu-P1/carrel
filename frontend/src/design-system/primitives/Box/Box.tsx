import { h, type ComponentChildren, type JSX } from "preact";

import styles from "./Box.module.css";

type Space = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16;
type Radius = 0 | 1 | 2 | 3 | 4 | 5 | "full";
type Surface = "none" | "muted" | "elevated" | "overlay";

export interface BoxProps extends JSX.HTMLAttributes<HTMLElement> {
  as?: keyof JSX.IntrinsicElements;
  padding?: Space;
  radius?: Radius;
  surface?: Surface;
  border?: boolean;
  children?: ComponentChildren;
}

export function Box({
  as = "div",
  padding = 0,
  radius = 0,
  surface = "none",
  border = false,
  className,
  children,
  ...rest
}: BoxProps) {
  const classes = [
    styles.box,
    styles[`padding-${padding}`],
    styles[`radius-${radius}`],
    surface !== "none" ? styles[`surface-${surface}`] : "",
    border ? styles.border : "",
    className ?? ""
  ]
    .filter(Boolean)
    .join(" ");

  return h(
    String(as),
    {
      className: classes,
      ...(rest as JSX.HTMLAttributes<HTMLElement>)
    },
    children
  );
}
