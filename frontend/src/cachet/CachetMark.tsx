/**
 * The Cachet mark: the truncated C drawn as an open ring, severed in the
 * upper-left. The unfinished impression is the refusal. Ink via currentColor.
 *
 * Path data is the real brand asset (cachet-landing/assets/brand/cachet-mark.svg),
 * not a hand-drawn approximation. viewBox 0 0 240 240, two 16px arcs.
 */
export function CachetMark({
  size = 28,
  className,
  title = "Cachet"
}: {
  size?: number;
  className?: string;
  title?: string;
}) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 240 240"
      role="img"
      aria-label={title}
      fill="none"
      stroke="currentColor"
      strokeLinecap="butt"
    >
      <title>{title}</title>
      <path d="M174.25 86.02 A64 64 0 0 1 80.53 69.56" strokeWidth="16" />
      <path d="M64.53 88.00 A64 64 0 0 0 174.25 153.98" strokeWidth="16" />
    </svg>
  );
}
