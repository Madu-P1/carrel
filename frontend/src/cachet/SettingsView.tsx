import styles from "./cachet.module.css";

/**
 * Settings scaffold. The model key entry belongs here, but the secure target is
 * the macOS Keychain via the native shell (Xcode/GUI-gated, tracked separately),
 * so this view describes where the key lives rather than holding a plaintext
 * field. Appearance is fixed paper by design (the Instrument has no dark mode).
 */
export function SettingsView() {
  return (
    <section className={styles.plainView}>
      <div className={styles.plainHead}>
        <h2 className={styles.plainTitle}>Settings</h2>
        <p className={styles.plainLede}>
          Cachet runs locally. Nothing leaves this machine without your say.
        </p>
      </div>

      <dl className={styles.settingsList}>
        <div className={styles.settingsRow}>
          <dt className={styles.settingsKey}>Model key</dt>
          <dd className={styles.settingsVal}>
            Stored in the macOS Keychain by the app, never in the page or a file.
            The secure entry is wired in the native shell.
          </dd>
        </div>
        <div className={styles.settingsRow}>
          <dt className={styles.settingsKey}>Appearance</dt>
          <dd className={styles.settingsVal}>
            Paper, always. The document and its verdict carry the weight, so there
            is no dark mode and near-zero motion.
          </dd>
        </div>
        <div className={styles.settingsRow}>
          <dt className={styles.settingsKey}>Scope</dt>
          <dd className={styles.settingsVal}>
            Cachet confirms grounding in the record. It does not judge legal
            correctness or strategy, and it never drafts a fix.
          </dd>
        </div>
      </dl>
    </section>
  );
}
