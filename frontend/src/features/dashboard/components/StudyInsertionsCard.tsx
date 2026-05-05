import { useStudyInsertions } from "../hooks/useStudyInsertions";

import styles from "./StudyInsertionsCard.module.css";

/**
 * Live "best time to study" card.
 *
 * Shows up to 3 ranked study-session insertions. Each row carries:
 *   - Why this slot (deadline name + days-out, OR "open block")
 *   - When (day, local time, duration)
 *   - Score bar (top suggestion fills 100%)
 *
 * The list re-renders automatically on every Apple Calendar change
 * via the SSE stream the `useStudyInsertions` hook subscribes to —
 * the user moves a meeting in Calendar.app and this card updates
 * within ~1-2 seconds without any manual refresh.
 *
 * Does NOT support accept/dismiss in this iteration. Insertions are
 * advice; committing happens through the existing Plan view's
 * suggestion accept flow. A future iteration could add an inline
 * "Add to Calendar" that POSTs an EKEvent through the macOS bridge,
 * but that needs a write-side EventKit path that doesn't exist yet.
 */
export function StudyInsertionsCard() {
  const { insertions, loading, error, streamState } = useStudyInsertions();

  return (
    <section className={styles.card} aria-label="Suggested study sessions">
      <header className={styles.header}>
        <span className={styles.eyebrow}>Best time to study</span>
        <span
          className={`${styles.livePill} ${streamState === "open" ? "" : styles.offline}`}
          aria-label={streamState === "open" ? "Live updates connected" : "Live updates offline"}
        >
          {streamState === "open" ? "Live" : "Reconnecting…"}
        </span>
      </header>

      {loading && insertions.length === 0 ? (
        <div className={styles.skeleton}>
          <div className={styles.skeletonRow} />
          <div className={styles.skeletonRow} />
          <div className={styles.skeletonRow} />
        </div>
      ) : error ? (
        <p className={styles.empty}>
          Couldn't load suggestions. {streamState === "open" ? "Updates resume on the next calendar change." : ""}
        </p>
      ) : insertions.length === 0 ? (
        <p className={styles.empty}>
          No open blocks in the next two weeks. Free up some time and
          this panel fills in automatically.
        </p>
      ) : (
        <ul className={styles.list}>
          {insertions.map((ins) => (
            <li key={`${ins.start_at}-${ins.reason_code}`} className={styles.row}>
              <div className={styles.rowText}>
                <span className={styles.rowTitle}>
                  {ins.deadline_label ?? "Open study block"}
                </span>
                <span className={styles.rowSub}>{ins.reason_text}</span>
              </div>
              <div
                className={styles.scoreBar}
                aria-label={`Confidence ${Math.round(ins.score * 100)} percent`}
              >
                <div
                  className={styles.scoreFill}
                  style={{ width: `${Math.max(8, ins.score * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
