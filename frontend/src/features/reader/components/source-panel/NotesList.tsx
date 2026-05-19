import { notePreviewText } from "@/features/notes/noteContent";

import { EmptyState } from "./EmptyState";
import styles from "./SourcePanel.module.css";

interface NoteLike {
  content?: string;
  title?: string;
}

export function NotesList({ notes }: { notes: NoteLike[] }) {
  if (notes.length === 0) {
    return (
      <EmptyState
        icon="study"
        title="No notes on this source yet."
        description="Write one above. Notes you save here stay with this source."
      />
    );
  }

  return (
    <ul className={styles.rowList}>
      {notes.map((note, index) => (
        <li className={styles.noteRow} key={`${note.title ?? "note"}-${index}`}>
          <div className={styles.rowHeader}>
            <span className={styles.rowTitle}>
              {note.title || "Untitled note"}
            </span>
          </div>
          {note.content ? (
            <p className={styles.rowPreview}>
              {notePreviewText(note.content, "Empty note.")}
            </p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
