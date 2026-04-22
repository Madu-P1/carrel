export const duration = {
  instant: "var(--dur-instant)",
  fast: "var(--dur-fast)",
  base: "var(--dur-base)",
  medium: "var(--dur-medium)",
  slow: "var(--dur-slow)",
  long: "var(--dur-long)"
} as const;

export const easing = {
  out: "var(--ease-out)",
  in: "var(--ease-in)",
  swift: "var(--ease-swift)",
  soft: "var(--ease-soft)",
  spring: "var(--ease-spring)"
} as const;

export type DurationKey = keyof typeof duration;
export type EasingKey = keyof typeof easing;

export const motion = {
  fast: duration.fast,
  base: duration.base,
  slow: duration.slow,
  easeOut: easing.out,
  easeInOut: easing.soft
} as const;

export function transition(
  property: string,
  durationKey: DurationKey = "base",
  easingKey: EasingKey = "out"
): string {
  return `${property} ${duration[durationKey]} ${easing[easingKey]}`;
}

export function transitions(specs: Array<[string, DurationKey?, EasingKey?]>): string {
  return specs
    .map(([property, durationSpec, easingSpec]) =>
      transition(property, durationSpec ?? "base", easingSpec ?? "out")
    )
    .join(", ");
}

export function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
}
