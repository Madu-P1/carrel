import styles from "./Spinner.module.css";

type SpinnerSize = 16 | 20 | 24;

export interface SpinnerProps {
  size?: SpinnerSize;
  label?: string;
}

export function Spinner({ size = 16, label = "Loading" }: SpinnerProps) {
  return (
    <span
      aria-label={label}
      className={[styles.spinner, styles[`size-${size}`]].join(" ")}
      role="status"
    />
  );
}
