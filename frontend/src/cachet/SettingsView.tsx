import { useEffect, useState } from "preact/hooks";

import styles from "./cachet.module.css";

/**
 * Settings (handoff §10): a 640px column. Appearance is a Light/Dark segmented
 * control that sets data-theme on <html> (the dark token set already exists in
 * cachet.module.css) and persists the choice. The Engine card states, in mono,
 * exactly what runs where — the on-device provenance shown, not hidden
 * (invariant 8). The model-key and scope statements stay: they are honesty
 * copy, not chrome.
 */

const THEME_KEY = "cachet.theme";

function readTheme(): "light" | "dark" {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "dark" || stored === "light") return stored;
  } catch {
    /* storage unavailable: default */
  }
  return "light";
}

export function applyStoredTheme(): void {
  document.documentElement.setAttribute("data-theme", readTheme());
}

export function SettingsView() {
  const [theme, setTheme] = useState<"light" | "dark">(readTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* storage unavailable: the choice lives for this session */
    }
  }, [theme]);

  return (
    <section className={styles.settingsCol}>
      <section className={styles.settingsCard}>
        <div className={styles.settingsCardTitle}>Appearance</div>
        <div className={styles.themeSeg} role="group" aria-label="Appearance">
          <button
            type="button"
            className={styles.themeSegBtn}
            data-active={theme === "light" ? "true" : undefined}
            aria-pressed={theme === "light"}
            onClick={() => setTheme("light")}
          >
            Light
          </button>
          <button
            type="button"
            className={styles.themeSegBtn}
            data-active={theme === "dark" ? "true" : undefined}
            aria-pressed={theme === "dark"}
            onClick={() => setTheme("dark")}
          >
            Dark
          </button>
        </div>
      </section>

      <section className={styles.settingsCard}>
        <div className={styles.settingsCardTitle}>Engine</div>
        <div className={styles.engineGrid}>
          <span className={styles.engineKey}>Kernel</span>
          <span className={styles.engineMono}>cachet_verify</span>
          <span className={styles.engineKey}>Case-law store</span>
          <span className={styles.engineMono}>bundled · offline corpus</span>
          <span className={styles.engineKey}>Verify path</span>
          <span>No network I/O. Proven under a socket ban in CI.</span>
          <span className={styles.engineKey}>Case lookup</span>
          <span>Offline bounded corpus. Network lookup: off.</span>
        </div>
      </section>

      <section className={styles.settingsCard}>
        <div className={styles.settingsCardTitle}>Scope</div>
        <div className={styles.engineGrid}>
          <span className={styles.engineKey}>Model key</span>
          <span>
            The deterministic check needs no model key. If you opt into a model, its key stays
            with the local engine on this machine and is never entered or stored in this page.
          </span>
          <span className={styles.engineKey}>What it judges</span>
          <span>
            Cachet confirms grounding in the record. It does not judge legal correctness or
            strategy, and it never drafts a fix.
          </span>
        </div>
      </section>

      <p className={styles.settingsFoot}>
        Cachet reads a draft and its sources and returns a per-claim verdict: verified, altered,
        or could not check. It never rewrites and never picks a winner between conflicting
        sources.
      </p>
    </section>
  );
}
