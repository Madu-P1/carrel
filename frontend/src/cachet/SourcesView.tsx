import styles from "./cachet.module.css";

/**
 * Sources: the record Cachet checks a draft against. This is the scaffold empty
 * state; ingest (PDF/opinion text, the verification material) lands next. Built
 * as a composed empty state, not a "coming soon" placeholder.
 */
export function SourcesView() {
  return (
    <section className={styles.plainView}>
      <div className={styles.plainHead}>
        <h2 className={styles.plainTitle}>Sources</h2>
        <p className={styles.plainLede}>
          The record a draft is checked against. Cachet verifies a quote or a
          citation only against material you have added here, and refuses what it
          cannot trace to it.
        </p>
      </div>
      <div className={styles.plainNote}>
        No sources added yet. Adding opinions and exhibits is the next step in the
        build.
      </div>
    </section>
  );
}
