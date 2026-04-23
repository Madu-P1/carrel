import type { JSX } from "preact";

import styles from "./Skeleton.module.css";

export interface SkeletonProps extends JSX.HTMLAttributes<HTMLDivElement> {
  /** One of the layout presets. Pass `custom` and use `width` / `height`
   *  props directly for bespoke shapes. */
  shape?: "text" | "text-lg" | "text-sm" | "circle" | "card" | "row" | "custom";
  /** CSS width. String or number (number → px). Overrides the shape's
   *  default width. */
  width?: string | number;
  /** CSS height. Same rules as width. */
  height?: string | number;
  /** Hide the shimmer animation. Useful for dense test screenshots; do
   *  not disable in production — the shimmer is the affordance that tells
   *  the user the app is alive. */
  static?: boolean;
}

/**
 * Skeleton primitive.
 *
 * Loading-state building block. Renders an accessible placeholder
 * rectangle with the existing `shimmer` keyframe. Callers compose these
 * into shape-mimicking layouts: a SkeletonRow with a circle + two stacked
 * text bars is "a list-row that hasn't loaded yet."
 *
 * Accessibility:
 *   - role=status + aria-live=polite: screen readers announce "loading"
 *     once per region, not per skeleton.
 *   - aria-hidden on decorative individual skeletons INSIDE a status
 *     wrapper — covered by the wrapper announcement.
 *
 * Motion:
 *   - Uses --dur-narrative on the shimmer for a calm rhythm (1.4s).
 *   - Respects prefers-reduced-motion via the shared media query.
 *
 * Styling contract:
 *   - Surface color comes from --color-bg-muted + --state-bg-hover
 *     gradient stops so skeletons feel elevated above the surface they
 *     sit on, not flat.
 *   - Shape presets exist so the 80% common case doesn't need inline CSS.
 */
export function Skeleton({
  shape = "text",
  width,
  height,
  className,
  static: isStatic = false,
  ...rest
}: SkeletonProps) {
  const classes = [
    styles.skeleton,
    styles[`shape-${shape}`],
    isStatic ? styles.static : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");
  const style = {
    ...(width !== undefined ? { width: typeof width === "number" ? `${width}px` : width } : {}),
    ...(height !== undefined ? { height: typeof height === "number" ? `${height}px` : height } : {}),
    ...((rest.style as Record<string, string | number> | undefined) ?? {}),
  };
  return (
    <div
      aria-hidden
      className={classes}
      {...rest}
      style={style}
    />
  );
}

export interface SkeletonGroupProps {
  children?: JSX.Element | JSX.Element[];
  /** Visible label announced by screen readers. Ships per-surface so
   *  "Loading the Reader" beats the generic "loading". */
  label?: string;
}

/**
 * Wrapper that gives a cluster of Skeleton elements one ARIA status
 * announcement. Use this around any skeleton layout instead of
 * repeating role=status on each.
 */
export function SkeletonGroup({ children, label = "Loading" }: SkeletonGroupProps) {
  return (
    <div aria-live="polite" role="status">
      <span className={styles.srOnly}>{label}</span>
      {children}
    </div>
  );
}
