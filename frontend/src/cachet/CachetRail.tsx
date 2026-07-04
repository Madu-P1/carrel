import { navigateTo } from "@/app/shell/useAppShell";

import { CachetMark } from "./CachetMark";
import styles from "./cachet.module.css";

/**
 * The left rail (handoff §2): 88px, the open-ring mark in oxblood at the top,
 * icon-plus-label nav items 68px wide, Settings pinned to the bottom, and the
 * always-visible LOCAL provenance badge below it (invariant 8 — on-device
 * provenance is a feature, shown, not hidden). Active item wears the
 * accent-subtle fill with accent text.
 */

interface RailItem {
  key: string;
  label: string;
  path: string;
  icon: preact.JSX.Element;
}

// Outline glyphs per the handoff prototype: 19px, 1.75 stroke, round joins.
const LECTERN_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
  </svg>
);

const SHELF_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="4" width="18" height="4" rx="1" />
    <path d="M5 8v12h14V8" />
    <path d="M10 12h4" />
  </svg>
);

const VAULT_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <circle cx="12" cy="12" r="4.5" />
    <path d="M12 9.5v2.5l1.8 1.8" />
  </svg>
);

const BENCH_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 21h14" />
    <path d="M6 17h12l-1.5-4h-9Z" />
    <path d="M12 13V8" />
    <path d="M8.5 5.5a3.5 3.5 0 0 1 7 0V8h-7Z" />
  </svg>
);

const SETTINGS_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <line x1="4" y1="7" x2="20" y2="7" />
    <circle cx="9" cy="7" r="2" />
    <line x1="4" y1="17" x2="20" y2="17" />
    <circle cx="15" cy="17" r="2" />
  </svg>
);

const MAIN_ITEMS: RailItem[] = [
  { key: "lectern", label: "Lectern", path: "/", icon: LECTERN_ICON },
  { key: "shelf", label: "Shelf", path: "/shelf", icon: SHELF_ICON },
  { key: "vault", label: "Vault", path: "/vault", icon: VAULT_ICON },
  { key: "bench", label: "Bench", path: "/bench", icon: BENCH_ICON }
];

const SETTINGS_ITEM: RailItem = {
  key: "settings",
  label: "Settings",
  path: "/settings",
  icon: SETTINGS_ICON
};

function isActive(currentPath: string, itemPath: string): boolean {
  if (itemPath === "/") {
    // The lectern ("/") is the verify surface. Match it exactly (plus any
    // /verify sub-route) so the root never swallows every other route via
    // startsWith("/") and lights two items at once.
    return currentPath === "/" || currentPath.startsWith("/verify");
  }
  return currentPath.startsWith(itemPath);
}

function Glyph({ item, currentPath }: { item: RailItem; currentPath: string }) {
  const active = isActive(currentPath, item.path);
  return (
    <button
      type="button"
      className={`${styles.glyph} ${active ? styles.glyphActive : ""}`}
      aria-label={item.label}
      aria-current={active ? "page" : undefined}
      title={item.label}
      onClick={() => navigateTo(item.path)}
    >
      {item.icon}
      <span>{item.label}</span>
    </button>
  );
}

export function CachetRail({ currentPath }: { currentPath: string }) {
  return (
    <nav className={styles.rail} aria-label="Primary">
      <button
        type="button"
        className={styles.railMark}
        aria-label="Cachet home"
        title="Cachet"
        onClick={() => navigateTo("/")}
      >
        <CachetMark size={30} strokeWidth={19} />
      </button>
      <div className={styles.railGroup}>
        {MAIN_ITEMS.map((item) => (
          <Glyph key={item.key} item={item} currentPath={currentPath} />
        ))}
      </div>
      <div className={styles.railFoot}>
        <Glyph item={SETTINGS_ITEM} currentPath={currentPath} />
        <div
          className={styles.localBadge}
          title="No network connection is used on the verify path"
        >
          <span className={styles.localDot} />
          <span className={styles.localLabel}>LOCAL</span>
        </div>
      </div>
    </nav>
  );
}
