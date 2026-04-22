import type { ComponentChildren, JSX } from "preact";

import styles from "./Stack.module.css";

type Space = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16;
type Align = "start" | "center" | "end" | "stretch";
type Justify = "start" | "center" | "end" | "between";
type Direction = "vertical" | "horizontal";

export interface StackProps extends JSX.HTMLAttributes<HTMLDivElement> {
  direction?: Direction;
  gap?: Space;
  align?: Align;
  justify?: Justify;
  wrap?: boolean;
  children?: ComponentChildren;
}

export function Stack({
  direction = "vertical",
  gap = 4,
  align = "stretch",
  justify = "start",
  wrap = false,
  className,
  children,
  ...rest
}: StackProps) {
  const classes = [
    styles.stack,
    styles[`direction-${direction}`],
    styles[`gap-${gap}`],
    styles[`align-${align}`],
    styles[`justify-${justify}`],
    wrap ? styles.wrap : "",
    className ?? ""
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes} {...rest}>
      {children}
    </div>
  );
}
