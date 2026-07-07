import { useEffect } from "preact/hooks";
import { signal } from "@preact/signals";

import { Icon } from "@/design-system";

import styles from "./ShortcutsOverlay.module.css";

/**
 * Global keyboard shortcuts help overlay.
 *
 * Triggered by `?` (no modifiers) or the native Help > Keyboard Shortcuts
 * menu. Dismisses on `Esc` or by clicking outside. Renders a Raycast-style
 * sheet of every shortcut the app actually listens for, grouped by scope.
 *
 * Why this exists: the app has ~12 real shortcuts wired across views,
 * and exactly zero of them are discoverable. Power-user workflow is a
 * stated product priority. Invisible shortcuts = invisible power.
 *
 * This component only RENDERS the cheat sheet; it does not register the
 * shortcuts themselves. Global key handlers live in AppShell so they
 * work from every route.
 */

/** Module-level signal — toggled from AppShell's global key handler or
 *  from the native menu bridge. Deliberately global so any component can
 *  open the overlay (e.g., a "see all shortcuts" link in a footer). */
export const shortcutsOverlayOpen = signal(false);

export function openShortcutsOverlay(): void {
  shortcutsOverlayOpen.value = true;
}

export function closeShortcutsOverlay(): void {
  shortcutsOverlayOpen.value = false;
}

interface Shortcut {
  keys: string[];
  label: string;
  note?: string;
}

interface ShortcutGroup {
  title: string;
  shortcuts: Shortcut[];
}

const GROUPS: ShortcutGroup[] = [
  {
    title: "Navigation",
    shortcuts: [
      { keys: ["⌘", "1"], label: "Dashboard" },
      { keys: ["⌘", "2"], label: "Session" },
      { keys: ["⌘", "3"], label: "Library" },
      { keys: ["⌘", "4"], label: "Reader" },
      { keys: ["⌘", "5"], label: "Ask" },
      { keys: ["⌘", "6"], label: "Study" },
      { keys: ["⌘", "K"], label: "Command palette" },
      { keys: ["/"], label: "Ask a question", note: "from anywhere" }
    ]
  },
  {
    title: "View",
    shortcuts: [
      { keys: ["⌘", "B"], label: "Toggle left sidebar" },
      { keys: ["⌘", "⌥", "B"], label: "Toggle right panel" },
      { keys: ["⌘", "⇧", "T"], label: "Toggle theme" },
      { keys: ["⌘", "="], label: "Zoom in (Reader)" },
      { keys: ["⌘", "-"], label: "Zoom out (Reader)" },
      { keys: ["⌘", "0"], label: "Actual size (Reader)" },
      { keys: ["⌘", "⇧", "F"], label: "Toggle Reader focus mode" },
      { keys: ["⌘", "F"], label: "Find in document (Reader)", note: "Esc to close" },
      { keys: ["⌘", "/"], label: "Find in document (Reader)", note: "alternate" }
    ]
  },
  {
    title: "Study mode",
    shortcuts: [
      { keys: ["Space"], label: "Reveal answer", note: "during review" },
      { keys: ["1"], label: "Again" },
      { keys: ["2"], label: "Hard" },
      { keys: ["3"], label: "Good" },
      { keys: ["4"], label: "Easy" }
    ]
  },
  {
    title: "Global",
    shortcuts: [
      { keys: ["Esc"], label: "Close overlay / cancel" },
      { keys: ["?"], label: "This shortcuts sheet" },
      { keys: ["⌘", "I"], label: "Import source", note: "drag-drop also works" }
    ]
  }
];

export function ShortcutsOverlay() {
  const isOpen = shortcutsOverlayOpen.value;

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeShortcutsOverlay();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div
      className={styles.backdrop}
      onClick={closeShortcutsOverlay}
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
    >
      <div
        className={styles.sheet}
        onClick={(event) => event.stopPropagation()}
      >
        <header className={styles.header}>
          <div>
            <span className={styles.eyebrow}>Keyboard shortcuts</span>
            <h2 className={styles.title}>Fly through Cachet.</h2>
          </div>
          <button
            type="button"
            className={styles.closeButton}
            onClick={closeShortcutsOverlay}
            aria-label="Close shortcuts"
          >
            <Icon name="x" size={16} />
          </button>
        </header>
        <div className={styles.grid}>
          {GROUPS.map((group) => (
            <section key={group.title} className={styles.group}>
              <h3 className={styles.groupTitle}>{group.title}</h3>
              <ul className={styles.list}>
                {group.shortcuts.map((shortcut) => (
                  <li
                    key={`${group.title}-${shortcut.label}`}
                    className={styles.row}
                  >
                    <span className={styles.label}>{shortcut.label}</span>
                    {shortcut.note && (
                      <span className={styles.note}>{shortcut.note}</span>
                    )}
                    <span className={styles.keys} aria-hidden>
                      {shortcut.keys.map((key, index) => (
                        <kbd key={index} className={styles.kbd}>
                          {key}
                        </kbd>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <footer className={styles.footer}>
          <span>
            Shortcuts work from any view. Press <kbd className={styles.kbd}>?</kbd>
            {" "}again to reopen.
          </span>
        </footer>
      </div>
    </div>
  );
}
