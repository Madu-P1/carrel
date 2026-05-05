import { useCallback, useEffect, useState } from "preact/hooks";

import { Button, Icon } from "@/design-system";
import { formatRelativeTime } from "@/lib/time";
import { library, type SubjectSummary } from "@/services/api/endpoints";

import styles from "./SubjectCardGrid.module.css";

/**
 * Subject dashboard. Grid of cards, one per subject, showing flashcard
 * count, source count, last-studied date, and an inline error state when
 * a document in the subject failed to parse.
 *
 * Designed as the Library home view: the user lands here and sees their
 * active study territories at a glance. Clicking a card drills into that
 * subject's file list via `onSubjectOpen`. Explicit subject folders are
 * shown even when empty so users can create a subject before importing.
 *
 * Data contract comes from `GET /api/library/subjects`. This component
 * re-fetches on mount and exposes a `refresh()` callback the parent can
 * call after mutations (upload, delete, duplicate cleanup).
 */

interface SubjectCardGridProps {
  onSubjectOpen: (subject: string) => void;
  /** When set, the header of the section is suppressed (used when parent
   * renders its own eyebrow). */
  headless?: boolean;
  /** Nonce bumped by the parent after a mutation so the grid refetches. */
  refreshKey?: unknown;
}

export function SubjectCardGrid({
  onSubjectOpen,
  headless = false,
  refreshKey
}: SubjectCardGridProps) {
  const [subjects, setSubjects] = useState<SubjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchSubjects = useCallback(async () => {
    try {
      const data = await library.subjects();
      setSubjects(data.subjects);
      setError(null);
    } catch (caught) {
      setError((caught as Error).message);
    }
  }, []);

  useEffect(() => {
    void fetchSubjects();
  }, [fetchSubjects, refreshKey]);

  if (error) {
    return (
      <div className={styles.errorState}>
        Could not load subjects: {error}
      </div>
    );
  }

  if (!subjects) {
    return (
      <div className={styles.gridSkeleton}>
        <div className={styles.cardSkeleton} />
        <div className={styles.cardSkeleton} />
        <div className={styles.cardSkeleton} />
      </div>
    );
  }

  if (subjects.length === 0) {
    return null;
  }

  return (
    <section className={styles.section} aria-label="Active subjects">
      {!headless && <h3 className={styles.sectionHeader}>Active Subjects</h3>}
      <div className={styles.grid}>
        {subjects.map((subject) => (
          <SubjectCard
            key={subject.subject_name}
            subject={subject}
            onOpen={() => onSubjectOpen(subject.subject_name)}
          />
        ))}
      </div>
    </section>
  );
}

interface SubjectCardProps {
  subject: SubjectSummary;
  onOpen: () => void;
}

function SubjectCard({ subject, onOpen }: SubjectCardProps) {
  const lastStudied = formatLastStudied(subject.last_studied_at);
  const hasFailure = Boolean(subject.first_failed_doc);
  const empty = subject.source_count === 0;

  return (
    <button type="button" className={styles.card} onClick={onOpen}>
      <div className={styles.cardHeader}>
        <div className={styles.cardGlyph} aria-hidden>
          <Icon name="library" size={18} />
        </div>
        {hasFailure && (
          <span className={styles.statusPill}>Indexing Failed</span>
        )}
        {empty && !hasFailure ? (
          <span className={styles.emptyPill}>Empty folder</span>
        ) : null}
      </div>

      <h4 className={styles.cardTitle}>{subject.subject_name}</h4>

      {hasFailure && subject.first_failed_doc && (
        <div className={styles.errorBlock} role="status">
          <span className={styles.errorHeader}>
            <Icon name="x" size={12} />
            <span>Failed to parse:</span>
          </span>
          <span className={styles.errorFilename}>
            {subject.first_failed_doc.filename}
          </span>
          <span className={styles.errorDetail}>
            {subject.first_failed_doc.error}
          </span>
        </div>
      )}

      <dl className={styles.stats}>
        <div className={styles.statRow}>
          <dt>Last Studied</dt>
          <dd className={styles.statMeta}>{lastStudied}</dd>
        </div>
        <div className={styles.statRow}>
          <dt>Flashcards</dt>
          <dd className={styles.statAccent}>{subject.flashcard_count}</dd>
        </div>
        <div className={styles.statRow}>
          <dt>Sources</dt>
          <dd className={styles.statMeta}>
            <Icon name="doc" size={12} /> {subject.source_count}{" "}
            {subject.source_count === 1 ? "document" : "documents"}
            {subject.failed_count > 0 ? ` (${subject.failed_count} failed)` : ""}
          </dd>
        </div>
      </dl>
    </button>
  );
}

/**
 * Short relative timestamp for the subject card "Last Studied" stat.
 * Delegates to `lib/time.formatRelativeTime`, which handles the naive-
 * UTC parsing bug uniformly across the app. Kept as a local wrapper so
 * callers keep the old name without churn.
 */
function formatLastStudied(iso: string | null): string {
  if (!iso) {
    return "Never";
  }
  return formatRelativeTime(iso);
}

/** Re-export the Button primitive so feature callers can use it without
 *  pulling @/design-system directly in this barrel. Keeps import graphs
 *  narrower and makes the file boundaries obvious. */
export { Button };
