import type { ComponentChildren, JSX } from "preact";

import { Spinner } from "../Spinner";

import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

export interface ButtonProps
  extends Omit<JSX.ButtonHTMLAttributes<HTMLButtonElement>, "size"> {
  variant?: Variant;
  size?: Size;
  isLoading?: boolean;
  leadingIcon?: ComponentChildren;
  /**
   * Keyboard shortcut hint rendered as a trailing `<kbd>` chip inside the
   * button, Linear/Raycast-style. Pass the rendered label ("⌘N", "↵",
   * "⌘⇧P") — the button does not bind the shortcut. Global key handling
   * stays in AppShell and per-feature effects.
   */
  keyHint?: string;
  children?: ComponentChildren;
}

export function Button({
  variant = "primary",
  size = "md",
  isLoading = false,
  leadingIcon,
  keyHint,
  className,
  disabled,
  children,
  ...rest
}: ButtonProps) {
  const classes = [
    styles.btn,
    styles[`variant-${variant}`],
    styles[`size-${size}`],
    isLoading ? styles.loading : "",
    className ?? ""
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      aria-busy={isLoading || undefined}
      className={classes}
      disabled={disabled || isLoading}
      {...rest}
    >
      {isLoading ? <Spinner label="Loading button" size={16} /> : null}
      {!isLoading && leadingIcon ? (
        <span className={styles.leading}>{leadingIcon}</span>
      ) : null}
      <span className={styles.label}>{children}</span>
      {!isLoading && keyHint ? (
        <kbd aria-hidden className={styles.keyHint}>
          {keyHint}
        </kbd>
      ) : null}
    </button>
  );
}
