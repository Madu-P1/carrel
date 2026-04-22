import { h, type ComponentChildren, type JSX } from "preact";

import styles from "./Text.module.css";

type Variant = "caption" | "body" | "h3" | "h2" | "h1" | "display";
type Tone =
  | "primary"
  | "secondary"
  | "tertiary"
  | "disabled"
  | "success"
  | "warning"
  | "danger";
type Weight = "regular" | "medium" | "semibold" | "bold";

export interface TextProps extends JSX.HTMLAttributes<HTMLElement> {
  as?: keyof JSX.IntrinsicElements;
  variant?: Variant;
  tone?: Tone;
  weight?: Weight;
  children?: ComponentChildren;
}

export function Text({
  as = "p",
  variant = "body",
  tone = "primary",
  weight = "regular",
  className,
  children,
  ...rest
}: TextProps) {
  const resolvedWeight = variant === "h1" || variant === "display" ? "regular" : weight;
  const classes = [
    styles.text,
    styles[`variant-${variant}`],
    styles[`tone-${tone}`],
    styles[`weight-${resolvedWeight}`],
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
