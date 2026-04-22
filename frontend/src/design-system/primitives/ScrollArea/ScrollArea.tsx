import type { ComponentChildren, JSX } from "preact";

import styles from "./ScrollArea.module.css";

export interface ScrollAreaProps extends JSX.HTMLAttributes<HTMLDivElement> {
  children?: ComponentChildren;
}

export function ScrollArea({
  className,
  children,
  ...rest
}: ScrollAreaProps) {
  return (
    <div
      className={[styles.scrollArea, className ?? ""].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}
