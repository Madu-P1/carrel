import styles from "./Divider.module.css";

type Orientation = "horizontal" | "vertical";

export interface DividerProps {
  orientation?: Orientation;
}

export function Divider({ orientation = "horizontal" }: DividerProps) {
  return (
    <div
      aria-orientation={orientation}
      className={[styles.divider, styles[orientation]].join(" ")}
      role="separator"
    />
  );
}
