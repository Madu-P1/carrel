import { useEffect, useRef, useState } from "preact/hooks";

import { Button, Icon } from "@/design-system";

import type { SrsSubjectSummary } from "@/services/api/endpoints";
import styles from "./SrsSubjectScopePill.module.css";

export interface SrsSubjectScopePillProps {
  /**
   * The currently-selected subject. `null` means "all subjects" — the
   * unfiltered review queue.
   */
  value: string | null;
  /**
   * Subjects available for scoping. Comes from `/api/srs/subjects` and
   * includes per-subject card + due counts so the menu can show
   * "Biology · 12 due" without a separate fetch.
   */
  subjects: SrsSubjectSummary[];
  onChange: (value: string | null) => void;
  /** Aggregate "all subjects" due count. Rendered in the All option. */
  allDueCount: number;
}

/**
 * Subject scope picker for the SRS review session (S-1).
 *
 * Mirrors the disclosure-button pattern of Ask's `ScopePill` so the
 * Study + Ask surfaces share a mental model. A single button shows
 * the current scope ("All subjects (24 due)" / "Biology (12 due)"); a
 * popover lets the user switch.
 *
 * Closes on outside-click, on Escape, and on selection. Keyboard
 * navigation is rudimentary (Tab/Shift-Tab through options); the
 * selection model is small enough that a roving tabindex isn't
 * justified yet.
 */
export function SrsSubjectScopePill({
  value,
  subjects,
  onChange,
  allDueCount,
}: SrsSubjectScopePillProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onClickAway = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (target && wrapRef.current && !wrapRef.current.contains(target)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", onClickAway);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("mousedown", onClickAway);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const activeLabel = value
    ? `${value} (${
        subjects.find((s) => s.subject_name === value)?.due_count ?? 0
      } due)`
    : `All subjects (${allDueCount} due)`;

  const select = (next: string | null) => {
    onChange(next);
    setOpen(false);
  };

  return (
    <div ref={wrapRef} className={styles.wrap}>
      <Button
        variant="secondary"
        leadingIcon={<Icon name="library" size={14} />}
        onClick={() => setOpen((current) => !current)}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {activeLabel}
      </Button>

      {open ? (
        <div role="menu" className={styles.menu} aria-label="Choose review scope">
          <button
            type="button"
            role="menuitem"
            className={`${styles.item} ${value === null ? styles.itemActive : ""}`}
            onClick={() => select(null)}
          >
            <span className={styles.itemLabel}>All subjects</span>
            <span className={styles.itemCount}>{allDueCount} due</span>
          </button>
          {subjects.length === 0 ? (
            <div className={styles.empty}>No subjects yet.</div>
          ) : null}
          {subjects.map((subject) => (
            <button
              type="button"
              role="menuitem"
              key={subject.subject_name}
              className={`${styles.item} ${
                value === subject.subject_name ? styles.itemActive : ""
              }`}
              onClick={() => select(subject.subject_name)}
              disabled={subject.due_count === 0 && subject.card_count > 0}
              title={
                subject.due_count === 0 && subject.card_count > 0
                  ? "No cards due in this subject right now"
                  : undefined
              }
            >
              <span className={styles.itemLabel}>{subject.subject_name}</span>
              <span className={styles.itemCount}>
                {subject.due_count} due
                {subject.card_count > subject.due_count
                  ? ` · ${subject.card_count} total`
                  : ""}
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
