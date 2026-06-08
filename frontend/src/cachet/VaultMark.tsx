/**
 * The vault's emblem: a folder rendered as a solid object, not a flat icon.
 * Solidity comes from a light model, not decoration:
 *
 *  - a lit FRONT FACE (a near-vertical gradient, light from above);
 *  - real THICKNESS (a darker copy of the body offset down, so the folder has a
 *    visible bottom edge, the biggest "not flat" cue) — reads at larger sizes;
 *  - a CATCHING HIGHLIGHT on the top lip where light grazes the edge;
 *  - the TAB held as a separate, darker, recessed plane.
 *
 * Two tones. `ink` is the default and clads the furniture: a folder beside every
 * vault name, calm and sober so a long list scans cleanly. `oxblood` is spent
 * ONCE, as the page emblem by the "Vault" title. Oxblood is the product's
 * reserved danger/refusal accent, so it never paints ordinary furniture or a
 * neutral empty state (per the Harvey review, 2026-06-08): the only red elsewhere
 * is a refusal. Geometry is the supplied folder path, unchanged.
 */
const BODY =
  "M 2205.8 547.4 L 332.2 547.4 C 203.39 547.4 98 652.79 98 781.6 L 98 1952.6 " +
  "C 98 2081.41 203.39 2186.8 332.2 2186.8 L 2205.8 2186.8 C 2334.61 2186.8 2440 2081.41 " +
  "2440 1952.6 L 2440 781.6 C 2440 652.79 2334.61 547.4 2205.8 547.4 Z";
const TAB =
  "M 2205.8 547.4 L 1151.9 547.4 L 917.7 313.2 L 332.2 313.2 C 203.39 313.2 98 418.59 " +
  "98 547.4 L 98 1015.8 L 2440 1015.8 L 2440 781.6 C 2440 652.79 2334.61 547.4 2205.8 547.4 Z";

type Tone = "ink" | "oxblood";

interface Palette {
  faceTop: string;
  faceMid: string;
  faceDeep: string;
  tabTop: string;
  tabDeep: string;
  thickness: string;
  lip: string;
  lipOpacity: number;
  sheenOpacity: number;
}

const PALETTES: Record<Tone, Palette> = {
  // Near-black ink, value-modulated for form. The calm furniture tone.
  ink: {
    faceTop: "#33291f",
    faceMid: "#1f1813",
    faceDeep: "#0d0a07",
    tabTop: "#191109",
    tabDeep: "#0b0805",
    thickness: "#070504",
    lip: "#5b5043",
    lipOpacity: 0.5,
    sheenOpacity: 0.1
  },
  // The reserved oxblood, in its heaviest, most solid treatment. Spent once.
  oxblood: {
    faceTop: "#93313f",
    faceMid: "#7a2230",
    faceDeep: "#561522",
    tabTop: "#581622",
    tabDeep: "#3a0e18",
    thickness: "#2c0a11",
    lip: "#b14552",
    lipOpacity: 0.62,
    sheenOpacity: 0.16
  }
};

let markSeq = 0;

export function VaultMark({
  size = 28,
  tone = "ink",
  className,
  title = "Vault"
}: {
  size?: number;
  tone?: Tone;
  className?: string;
  title?: string;
}) {
  const p = PALETTES[tone];
  const uid = `vault-${(markSeq += 1)}`;
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 2500 2500"
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      <defs>
        <linearGradient id={`${uid}-face`} x1="0.12" y1="0" x2="0.4" y2="1">
          <stop offset="0" stop-color={p.faceTop} />
          <stop offset="0.5" stop-color={p.faceMid} />
          <stop offset="1" stop-color={p.faceDeep} />
        </linearGradient>
        <linearGradient id={`${uid}-tab`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color={p.tabTop} />
          <stop offset="1" stop-color={p.tabDeep} />
        </linearGradient>
        <linearGradient id={`${uid}-sheen`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#ffffff" stop-opacity={p.sheenOpacity} />
          <stop offset="1" stop-color="#ffffff" stop-opacity="0" />
        </linearGradient>
        <clipPath id={`${uid}-clip`}>
          <path d={BODY} />
        </clipPath>
      </defs>

      {/* Thickness: a darker copy of the body dropped down (heavier extrude). The
          single strongest cue that this is a solid object, not a flat shape. */}
      <path d={BODY} transform="translate(0 66)" fill={p.thickness} />
      {/* The recessed back tab, a separate darker plane. */}
      <path d={TAB} fill={`url(#${uid}-tab)`} />
      {/* The lit front face. */}
      <path d={BODY} fill={`url(#${uid}-face)`} />
      {/* Surface light + a darker contact where the face meets its own thickness. */}
      <g clip-path={`url(#${uid}-clip)`}>
        <rect x="98" y="547" width="2342" height="560" fill={`url(#${uid}-sheen)`} />
        <rect x="98" y="2050" width="2342" height="137" fill={p.thickness} opacity="0.55" />
      </g>
      {/* The top lip catching the light. */}
      <path
        d="M 360 553 L 2178 553"
        fill="none"
        stroke={p.lip}
        stroke-width="8"
        stroke-opacity={p.lipOpacity}
        stroke-linecap="round"
      />
    </svg>
  );
}
