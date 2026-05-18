import type { JSX } from "preact";

/**
 * Inline SVG icon set for the Stillwater /notes page.
 *
 * These are NOT a substitute for the design-system Icon primitive —
 * they exist only because Stillwater's design canvas uses a specific
 * outline-weight + corner-radius set that the global icon catalog
 * doesn't carry yet. When the design system absorbs them, callers
 * can swap to <Icon name="..." /> and this file goes away.
 *
 * Contract:
 *   - viewBox "0 0 16 16"
 *   - stroke="currentColor", fill="none", stroke-width 1.5 (except
 *     the filled star and dot)
 *   - All paths use the parent color via currentColor so a single
 *     <span style={{ color: "..." }}> drives the whole icon
 */

type IconProps = JSX.SVGAttributes<SVGSVGElement>;

const base: IconProps = {
  viewBox: "0 0 16 16",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round"
};

const baseThin: IconProps = { ...base, strokeWidth: 1.4 };

const baseFilled: IconProps = {
  viewBox: "0 0 16 16",
  fill: "currentColor"
};

export const Ic = {
  search: (p: IconProps = {}) => (
    <svg {...base} {...p}>
      <circle cx={7} cy={7} r={4.5} />
      <path d="m10.5 10.5 3 3" />
    </svg>
  ),

  plus: (p: IconProps = {}) => (
    <svg {...base} {...p}>
      <path d="M8 3v10M3 8h10" />
    </svg>
  ),

  star: (p: IconProps = {}) => (
    <svg {...baseFilled} {...p}>
      <path d="M8 1.5l1.9 4 4.4.5-3.3 3 .9 4.4L8 11.3 4.1 13.4l.9-4.4-3.3-3 4.4-.5z" />
    </svg>
  ),

  chevron: (p: IconProps = {}) => (
    <svg {...base} {...p}>
      <path d="m4 6 4 4 4-4" />
    </svg>
  ),

  chevronR: (p: IconProps = {}) => (
    <svg {...base} {...p}>
      <path d="m6 4 4 4-4 4" />
    </svg>
  ),

  folder: (p: IconProps = {}) => (
    <svg {...baseThin} {...p}>
      <path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h2.7l1.3 1.5h5A1.5 1.5 0 0 1 14 6v5.5A1.5 1.5 0 0 1 12.5 13h-9A1.5 1.5 0 0 1 2 11.5z" />
    </svg>
  ),

  note: (p: IconProps = {}) => (
    <svg {...baseThin} {...p}>
      <path d="M3.5 2h6L13 5.5v8a.5.5 0 0 1-.5.5h-9a.5.5 0 0 1-.5-.5v-11A.5.5 0 0 1 3.5 2z" />
      <path d="M9 2v3.5h4" />
    </svg>
  ),

  inbox: (p: IconProps = {}) => (
    <svg {...baseThin} {...p}>
      <path d="M2 9.5 4 4h8l2 5.5V13a.5.5 0 0 1-.5.5h-11A.5.5 0 0 1 2 13z" />
      <path d="M2 9.5h3.5l1 2h3l1-2H14" />
    </svg>
  ),

  clock: (p: IconProps = {}) => (
    <svg {...baseThin} {...p}>
      <circle cx={8} cy={8} r={6} />
      <path d="M8 5v3l2 1.5" />
    </svg>
  ),

  arrowR: (p: IconProps = {}) => (
    <svg {...base} strokeWidth={1.6} {...p}>
      <path d="M3 8h10m-4-4 4 4-4 4" />
    </svg>
  ),

  edit: (p: IconProps = {}) => (
    <svg {...base} {...p}>
      <path d="M11.5 2.5 13.5 4.5 5.5 12.5 3.5 12.5 3.5 10.5z" />
      <path d="M10 4l2 2" />
    </svg>
  ),

  trash: (p: IconProps = {}) => (
    <svg {...base} {...p}>
      <path d="M3 4.5h10" />
      <path d="M6 4.5V3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1.5" />
      <path d="M4.5 4.5l0.8 8.3a1 1 0 0 0 1 0.9h3.4a1 1 0 0 0 1-0.9l0.8-8.3" />
    </svg>
  )
};
