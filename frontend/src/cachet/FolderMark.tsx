/**
 * The handoff's folder mark (README §Assets, geometry verbatim from
 * Cachet.dc.html): a flat layered folder — #FFC93E back panel, white sheets
 * peeking over a 6% black shadow, #FFAA2B front pocket with the lighter
 * #FFA114 inner band, and a 14%-white fold highlight. These are deliberately
 * THE ONLY saturated colors in the product and they are illustration, never a
 * tier signal (oxblood/danger stay reserved for verdicts). Used at 56×42 on
 * vault cards and 34×26 on record rows.
 */
export function FolderMark({
  width = 56,
  className,
  title
}: {
  width?: number;
  className?: string;
  title?: string;
}) {
  const height = Math.round((width * 100) / 132);
  return (
    <svg
      viewBox="0 0 132 100"
      style={{ width: `${width}px`, height: `${height}px` }}
      className={className}
      role={title ? "img" : undefined}
      aria-label={title || undefined}
      aria-hidden={title ? undefined : "true"}
    >
      <rect x="3" y="4" width="126" height="94" rx="7" fill="#FFC93E" />
      <rect x="14" y="12" width="104" height="80" rx="4" fill="#000" fillOpacity="0.06" />
      <rect x="16" y="9" width="104" height="80" rx="4" fill="#FFFFFF" />
      <path
        d="M3 34 h126 v57 a7 7 0 0 1 -7 7 H10 a7 7 0 0 1 -7 -7 Z"
        fill="#000"
        fillOpacity="0.06"
      />
      <path d="M3 30 h126 v61 a7 7 0 0 1 -7 7 H10 a7 7 0 0 1 -7 -7 Z" fill="#FFAA2B" />
      <path d="M3 46 h126 v45 a7 7 0 0 1 -7 7 H10 a7 7 0 0 1 -7 -7 Z" fill="#FFA114" />
      <path d="M96 46 L129 46 L129 79 Z" fill="#FFFFFF" fillOpacity="0.14" />
    </svg>
  );
}
