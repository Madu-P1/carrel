import { navigateTo } from "@/app/shell/useAppShell";
import { CachetMark } from "@/design-system";

import styles from "./cachet.module.css";

/**
 * The thin left rail. Four quiet ink glyphs and the mark. Navigation recedes so
 * the document and its verdict carry the weight ("The Instrument" direction).
 * The active glyph is ink with a 2px left tick; the rest sit in quiet ink.
 */

interface RailItem {
  key: string;
  label: string;
  path: string;
  icon: preact.JSX.Element;
}

// Glyphs are hand-set strokes (currentColor) so they read as ink marks, not a
// borrowed icon set. 22px, 1.4 stroke, butt joins to match the document hand.
const VERIFY_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
    <path d="M6 3.5h8l4 4v9.5" />
    <path d="M6 3.5v17h7" />
    <circle cx="16.5" cy="18.5" r="3" />
  </svg>
);

const SHELF_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
    <path d="M4 18.5h16" />
    <path d="M7.5 18.5V8M11 18.5V6M14.5 18.5V9.5" />
  </svg>
);

const SOURCES_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
    <path d="M9 4.5h7l3 3v9.5H9z" />
    <path d="M5 8v11.5h10" />
  </svg>
);

const SETTINGS_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
    <path d="M4 8.5h16M4 15.5h16" />
    <circle cx="9" cy="8.5" r="2.2" />
    <circle cx="15" cy="15.5" r="2.2" />
  </svg>
);

const MAIN_ITEMS: RailItem[] = [
  { key: "verify", label: "Verify", path: "/verify", icon: VERIFY_ICON },
  { key: "shelf", label: "Shelf", path: "/shelf", icon: SHELF_ICON },
  { key: "sources", label: "Sources", path: "/sources", icon: SOURCES_ICON }
];

const SETTINGS_ITEM: RailItem = {
  key: "settings",
  label: "Settings",
  path: "/settings",
  icon: SETTINGS_ICON
};

function isActive(currentPath: string, itemPath: string): boolean {
  if (itemPath === "/verify") {
    // The lectern ("/") leads into Verify; treat both as the Verify station so
    // the rail never looks orphaned on the landing.
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
        <CachetMark size={26} strokeWidth={19} />
      </button>
      <div className={styles.railGroup}>
        {MAIN_ITEMS.map((item) => (
          <Glyph key={item.key} item={item} currentPath={currentPath} />
        ))}
      </div>
      <div className={styles.railFoot}>
        <Glyph item={SETTINGS_ITEM} currentPath={currentPath} />
      </div>
    </nav>
  );
}
